"""
MCP Client module for connecting to MCP servers.

Provides on-demand connection management for stdio, SSE, and Streamable HTTP transports.
Discovered MCP tools are exposed as MAF FunctionTool objects with namespace isolation.
"""
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Any

from agent_framework import FunctionTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)


class MCPConnection:
    """Represents an active connection to an MCP server, exposing tools as MAF FunctionTool instances."""

    def __init__(self, server_id: str, server_name: str, session: ClientSession):
        self.server_id = server_id
        self.server_name = server_name
        self.session = session
        self.tools: list[dict] = []
        self.function_tools: list[FunctionTool] = []
        self.tool_names: set[str] = set()

    async def discover_tools(self) -> list[FunctionTool]:
        """List tools from the MCP server and format as MAF FunctionTool instances."""
        result = await self.session.list_tools()
        self.tools = []
        self.function_tools = []
        self.tool_names = set()

        for mcp_tool in result.tools:
            prefixed_name = f"mcp__{self.server_name}__{mcp_tool.name}"
            self.tool_names.add(prefixed_name)

            schema = mcp_tool.inputSchema or {"type": "object", "properties": {}}

            # Legacy OpenAI spec dict
            self.tools.append({
                "type": "function",
                "function": {
                    "name": prefixed_name,
                    "description": mcp_tool.description or "",
                    "parameters": schema,
                },
            })

            orig_name = mcp_tool.name

            # Handler closure capturing orig_name and prefixed_name
            async def _make_handler(orig_n: str, pref_n: str):
                async def handler(**kwargs) -> str:
                    try:
                        return await self.call_tool(orig_n, kwargs)
                    except Exception as e:
                        logger.error(f"Error executing MCP tool {pref_n}: {e}")
                        return f"MCP tool execution failed ({self.server_name}/{orig_n}): {e}"
                return handler

            handler_fn = await _make_handler(orig_name, prefixed_name)

            ft = FunctionTool(
                func=handler_fn,
                name=prefixed_name,
                description=mcp_tool.description or f"MCP tool {prefixed_name}",
                input_model=schema,
            )
            self.function_tools.append(ft)

        return self.function_tools

    async def call_tool(self, original_tool_name: str, arguments: dict) -> str:
        """Call a tool on the MCP server. Accepts the unprefixed original name."""
        try:
            result = await self.session.call_tool(original_tool_name, arguments)
            parts = []
            for content_item in getattr(result, "content", []):
                if hasattr(content_item, "text"):
                    parts.append(content_item.text)
                else:
                    parts.append(str(content_item))
            return "\n".join(parts) if parts else ""
        except (ConnectionResetError, BrokenPipeError, Exception) as e:
            logger.error(f"MCP server process error during call to {original_tool_name}: {e}")
            return f"MCP server stdio process crashed during tool invocation: {e}"


def parse_mcp_tool_name(prefixed_name: str) -> tuple[str, str] | None:
    """Parse 'mcp__<server_name>__<tool_name>' into (server_name, tool_name).
    Returns None if the name doesn't match the MCP prefix pattern."""
    if not prefixed_name.startswith("mcp__"):
        return None
    parts = prefixed_name.split("__", 2)
    if len(parts) != 3:
        return None
    return parts[1], parts[2]


@asynccontextmanager
async def connect_mcp_stdio(
    server_id: str,
    server_name: str,
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> AsyncIterator[MCPConnection]:
    """Connect to an MCP server via stdio transport."""
    server_params = StdioServerParameters(
        command=command,
        args=args or [],
        env=env,
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            conn = MCPConnection(server_id, server_name, session)
            await conn.discover_tools()
            yield conn


@asynccontextmanager
async def connect_mcp_sse(
    server_id: str,
    server_name: str,
    url: str,
    headers: dict[str, str] | None = None,
) -> AsyncIterator[MCPConnection]:
    """Connect to an MCP server via SSE transport."""
    async with sse_client(url, headers=headers or {}) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            conn = MCPConnection(server_id, server_name, session)
            await conn.discover_tools()
            yield conn


@asynccontextmanager
async def connect_mcp_streamable_http(
    server_id: str,
    server_name: str,
    url: str,
    headers: dict[str, str] | None = None,
) -> AsyncIterator[MCPConnection]:
    """Connect to an MCP server via Streamable HTTP transport."""
    async with streamablehttp_client(url, headers=headers or {}) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            conn = MCPConnection(server_id, server_name, session)
            await conn.discover_tools()
            yield conn


@asynccontextmanager
async def connect_mcp_server(server_config: dict) -> AsyncIterator[MCPConnection]:
    """Connect to an MCP server using its stored config.

    server_config should contain:
        - id or _id (str)
        - name (str)
        - transport_type ("stdio" | "sse" | "streamable_http")
        - command, args_json, env_json (for stdio)
        - url, headers_json (for sse / streamable_http)
    """
    server_id = str(server_config.get("id") or server_config.get("_id"))
    server_name = server_config["name"]
    transport = server_config["transport_type"]

    if transport == "stdio":
        command = server_config.get("command", "")
        args_raw = server_config.get("args_json") or server_config.get("args")
        if isinstance(args_raw, str):
            args = json.loads(args_raw)
        elif isinstance(args_raw, list):
            args = args_raw
        else:
            args = []
        env_raw = server_config.get("env_json") or server_config.get("env")
        if isinstance(env_raw, str):
            env = json.loads(env_raw)
        elif isinstance(env_raw, dict):
            env = env_raw
        else:
            env = None

        async with connect_mcp_stdio(server_id, server_name, command, args, env) as conn:
            yield conn

    elif transport == "sse":
        url = server_config.get("url", "")
        headers_raw = server_config.get("headers_json") or server_config.get("headers")
        if isinstance(headers_raw, str):
            headers = json.loads(headers_raw)
        elif isinstance(headers_raw, dict):
            headers = headers_raw
        else:
            headers = None

        async with connect_mcp_sse(server_id, server_name, url, headers) as conn:
            yield conn

    elif transport in ("streamable_http", "http", "streamable-http"):
        url = server_config.get("url", "")
        headers_raw = server_config.get("headers_json") or server_config.get("headers")
        if isinstance(headers_raw, str):
            headers = json.loads(headers_raw)
        elif isinstance(headers_raw, dict):
            headers = headers_raw
        else:
            headers = None

        async with connect_mcp_streamable_http(server_id, server_name, url, headers) as conn:
            yield conn

    else:
        raise ValueError(f"Unsupported MCP transport: {transport}")
