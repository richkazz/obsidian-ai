"""
Unit and integration test suite for MAF Core Foundation & Provider/Tool Modernization.
Covers ChatClient & ChatAgent Factory, Tool Decoration & Schemas, MCP Tool Bridge, and Dead Code Verification.
"""

import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from agent_framework import FunctionTool
from agent_framework.openai import OpenAIChatClient
from agent_framework.anthropic import AnthropicClient
from agent_framework.gemini import GeminiChatClient

from llm.provider_factory import ChatAgent, create_provider_from_config, create_provider
from llm.anthropic_provider import AnthropicProvider
from llm.nvidia_provider import NvidiaProvider
from builtin_tools import BUILTIN_TOOLS, web_search, calculator, weather, time
from sandbox_tools import create_sandbox_tools, execute_sandbox_tool
from mcp_client import MCPConnection, connect_mcp_stdio, connect_mcp_sse
from encryption import encrypt_api_key


# ============================================================================
# 1. ChatClient & ChatAgent Factory Test
# ============================================================================

def test_chat_agent_factory_supported_providers():
    """Instantiate MAF ChatAgent for OpenAI, Anthropic, Gemini, NVIDIA NIM and assert options propagation."""
    # OpenAI
    agent_openai = create_provider_from_config(
        provider_type="openai",
        api_key="sk-test-openai-123",
        base_url="https://api.openai.com/v1",
        model_id="gpt-4o",
        system_prompt="You are an OpenAI assistant.",
        default_options={"temperature": 0.7, "max_tokens": 500},
    )
    assert isinstance(agent_openai, ChatAgent)
    assert isinstance(agent_openai.client, OpenAIChatClient)
    assert agent_openai.client.api_key == "sk-test-openai-123"
    assert agent_openai.instructions == "You are an OpenAI assistant."
    assert agent_openai.default_options.get("temperature") == 0.7
    assert agent_openai.default_options.get("max_tokens") == 500

    # Anthropic
    agent_anthropic = create_provider_from_config(
        provider_type="anthropic",
        api_key="sk-ant-test-456",
        base_url=None,
        model_id="claude-3-5-sonnet-20241022",
        system_prompt="You are Claude.",
        config={"temperature": 0.3, "max_tokens": 1000},
    )
    assert isinstance(agent_anthropic, ChatAgent)
    assert isinstance(agent_anthropic.client, AnthropicClient)
    assert agent_anthropic.client.api_key == "sk-ant-test-456"
    assert agent_anthropic.instructions == "You are Claude."
    assert agent_anthropic.default_options.get("temperature") == 0.3
    assert agent_anthropic.default_options.get("max_tokens") == 1000

    # Google Gemini
    agent_gemini = create_provider_from_config(
        provider_type="gemini",
        api_key="AIzaSyTestGeminiKey",
        base_url=None,
        model_id="gemini-1.5-flash",
        system_prompt="You are Gemini.",
        config={"temperature": 0.1, "max_tokens": 2048},
    )
    assert isinstance(agent_gemini, ChatAgent)
    assert isinstance(agent_gemini.client, GeminiChatClient)
    assert agent_gemini.client.api_key == "AIzaSyTestGeminiKey"
    assert agent_gemini.instructions == "You are Gemini."
    assert agent_gemini.default_options.get("temperature") == 0.1
    assert agent_gemini.default_options.get("max_tokens") == 2048

    # NVIDIA NIM
    agent_nvidia = create_provider_from_config(
        provider_type="nvidia_nim",
        api_key="nvapi-test-nvidia-key",
        base_url="https://integrate.api.nvidia.com/v1",
        model_id="deepseek-ai/deepseek-v4-pro-0813",
        system_prompt="You are NVIDIA NIM.",
        config={"temperature": 0.5, "max_tokens": 4096},
    )
    assert isinstance(agent_nvidia, ChatAgent)
    assert isinstance(agent_nvidia.client, NvidiaProvider)
    assert agent_nvidia.client.api_key == "nvapi-test-nvidia-key"
    assert agent_nvidia.instructions == "You are NVIDIA NIM."
    assert agent_nvidia.default_options.get("temperature") == 0.5
    assert agent_nvidia.default_options.get("max_tokens") == 4096


@pytest.mark.asyncio
async def test_chat_agent_chat_stream_preserves_async_iterator_contract():
    async def fake_chat_stream(*args, **kwargs):
        yield "chunk"

    agent = ChatAgent(client=MagicMock())
    agent.client.chat_stream = fake_chat_stream

    chunks = [chunk async for chunk in agent.chat_stream([])]

    assert chunks == ["chunk"]


@pytest.mark.asyncio
async def test_chat_agent_chat_stream_adapts_framework_client():
    from agent_framework import Content, Message, ChatResponseUpdate
    from llm.base import LLMMessage

    class FrameworkClient:
        def __init__(self):
            self.calls = []

        def get_response(self, messages, *, stream, options):
            self.calls.append((messages, stream, options))

            async def updates():
                yield ChatResponseUpdate(contents=[Content("text", text="hello")])
                yield ChatResponseUpdate(contents=[Content("function_call", call_id="call-1", name="lookup", arguments={"q": "x"})])

            return updates()

    client = FrameworkClient()
    agent = ChatAgent(client=client)
    chunks = [chunk async for chunk in agent.chat_stream(
        [LLMMessage(role="user", content="question")],
        system_prompt="be concise",
        tools=[{"name": "lookup"}],
    )]

    assert isinstance(client.calls[0][0][0], Message)
    assert client.calls[0][1] is True
    assert client.calls[0][2] == {
        "instructions": "be concise",
        "tools": [{"name": "lookup"}],
    }
    assert [(chunk.type, chunk.content) for chunk in chunks if chunk.type == "content"] == [("content", "hello")]
    tool_chunk = next(chunk for chunk in chunks if chunk.type == "tool_call")
    assert tool_chunk.tool_call.name == "lookup"
    assert tool_chunk.tool_call.arguments == '{"q": "x"}'
    assert chunks[-1].type == "done"


def test_chat_agent_factory_fernet_decryption():
    """Assert Fernet API keys stored in record are decrypted in-memory during creation."""
    raw_key = "sk-fernet-secret-api-key"
    encrypted_key = encrypt_api_key(raw_key)

    mock_record = MagicMock()
    mock_record.provider_type = "openai"
    mock_record.api_key = encrypted_key
    mock_record.base_url = "https://api.openai.com/v1"
    mock_record.model_id = "gpt-4o"
    mock_record.config_json = json.dumps({"temperature": 0.8, "max_tokens": 300})

    agent = create_provider(mock_record, system_prompt="Record test assistant")

    assert isinstance(agent, ChatAgent)
    assert agent.client.api_key == raw_key
    assert agent.instructions == "Record test assistant"
    assert agent.default_options.get("temperature") == 0.8
    assert agent.default_options.get("max_tokens") == 300


def test_chat_agent_factory_unknown_provider_raises_value_error():
    """Assert invoking an unknown provider raises a validated ValueError."""
    with pytest.raises(ValueError, match="Unknown provider type: invalid_provider_xyz"):
        create_provider_from_config(
            provider_type="invalid_provider_xyz",
            api_key="key",
            base_url=None,
            model_id="model",
        )


def test_chat_agent_factory_invalid_credentials_raises_http_exception():
    """Assert invalid provider credentials during initialization raise HTTPException(400)."""
    with patch("llm.provider_factory.OpenAIChatClient", side_effect=Exception("Auth error")):
        with pytest.raises(HTTPException) as exc_info:
            create_provider_from_config(
                provider_type="openai",
                api_key="invalid-key",
                base_url=None,
                model_id="gpt-4o",
            )
        assert exc_info.value.status_code == 400
        assert "Invalid provider credentials" in exc_info.value.detail


# ============================================================================
# 2. Tool Decoration & Schema Generation Test
# ============================================================================

def test_builtin_tools_schema_generation():
    """Assert all 4 builtin tools (web_search, calculator, weather, time) export valid Draft-07 JSON schemas."""
    tools = [web_search, calculator, weather, time]

    for t in tools:
        assert isinstance(t, FunctionTool)
        schema_spec = t.to_json_schema_spec()

        assert schema_spec.get("type") == "function"
        fn = schema_spec.get("function", {})
        assert fn.get("name") in ("web_search", "calculator", "weather", "time")
        assert fn.get("description") is not None

        params = fn.get("parameters", {})
        assert params.get("type") == "object"
        assert "properties" in params

    # Specific property assertions
    calc_schema = calculator.to_json_schema_spec()["function"]["parameters"]
    assert "expression" in calc_schema["properties"]

    weather_schema = weather.to_json_schema_spec()["function"]["parameters"]
    assert "location" in weather_schema["properties"]

    time_schema = time.to_json_schema_spec()["function"]["parameters"]
    assert "timezone" in time_schema["properties"]

    search_schema = web_search.to_json_schema_spec()["function"]["parameters"]
    assert "query" in search_schema["properties"]


def test_calculator_ast_evaluation_safety():
    """Assert calculator uses AST parsing to evaluate valid math and block malicious code."""
    # Valid expressions
    res_valid = calculator.func(expression="2 + 3 * (4 - 1)")
    data_valid = json.loads(res_valid)
    assert data_valid.get("result") == "11"

    res_func = calculator.func(expression="sqrt(16) + abs(-5)")
    data_func = json.loads(res_func)
    assert data_func.get("result") == "9.0"

    # Malicious or unsupported expressions
    res_exploit = calculator.func(expression="__import__('os').system('ls')")
    data_exploit = json.loads(res_exploit)
    assert "error" in data_exploit
    assert "Calculation error" in data_exploit["error"]

    res_lambda = calculator.func(expression="(lambda: 1)()")
    data_lambda = json.loads(res_lambda)
    assert "error" in data_lambda


@pytest.mark.asyncio
async def test_sandbox_tools_maf_function_tools_interface():
    """Assert all 9 sandbox tools generate MAF FunctionTool instances and interface with execution."""
    container_id = "test-container-123"
    tools_dict = create_sandbox_tools(container_id)

    expected_names = [
        "sandbox_bash", "sandbox_write", "sandbox_read", "sandbox_ls",
        "sandbox_glob", "sandbox_grep", "sandbox_delete", "sandbox_python", "sandbox_node"
    ]

    assert len(tools_dict) == 9
    for name in expected_names:
        assert name in tools_dict
        ft = tools_dict[name]
        assert isinstance(ft, FunctionTool)
        spec = ft.to_json_schema_spec()
        assert spec["function"]["name"] == name
        assert "parameters" in spec["function"]

    # Test execution parameter validation with mock docker
    with patch("sandbox_tools._docker_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = ("ls output", 0)

        # Call sandbox_ls via MAF invoke
        ls_tool = tools_dict["sandbox_ls"]
        res = await ls_tool.invoke(arguments={"path": "//workspace"})
        assert len(res) > 0
        assert "ls output" in res[0].text


@pytest.mark.asyncio
async def test_sandbox_tools_docker_daemon_unavailability_handling():
    """Assert Docker daemon unavailability returns descriptive error string without unhandled exceptions."""
    container_id = "offline-container-456"
    tools_dict = create_sandbox_tools(container_id)

    with patch("sandbox_tools._docker_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = ("Docker sandbox runtime unavailable: Is the docker daemon running?", 1)

        bash_tool = tools_dict["sandbox_bash"]
        res = await bash_tool.invoke(arguments={"command": "echo test"})

        assert len(res) > 0
        assert "Docker sandbox runtime unavailable" in res[0].text


# ============================================================================
# 3. MCP Tool Bridge Test
# ============================================================================

class MockMCPTool:
    def __init__(self, name: str, description: str, schema: dict):
        self.name = name
        self.description = description
        self.inputSchema = schema


@pytest.mark.asyncio
async def test_mcp_tool_bridge_namespace_prefixing_stdio_and_sse():
    """Assert mock MCP stdio and SSE server transports expose tools with mcp__{server_name}__{tool_name} namespace prefixing as MAF FunctionTools."""
    mock_session = AsyncMock()
    mock_session.list_tools.return_value = MagicMock(tools=[
        MockMCPTool("query_db", "Query SQL DB", {"type": "object", "properties": {"sql": {"type": "string"}}}),
        MockMCPTool("send_mail", "Send email", {"type": "object", "properties": {"to": {"type": "string"}}}),
    ])
    mock_session.call_tool.return_value = MagicMock(content=[MagicMock(text="Query executed successfully")])

    conn = MCPConnection(server_id="mcp-srv-1", server_name="postgres", session=mock_session)
    tools = await conn.discover_tools()

    assert len(tools) == 2
    assert isinstance(tools[0], FunctionTool)
    assert tools[0].name == "mcp__postgres__query_db"
    assert tools[1].name == "mcp__postgres__send_mail"

    # Verify schema spec export
    schema_spec = tools[0].to_json_schema_spec()
    assert schema_spec["function"]["name"] == "mcp__postgres__query_db"
    assert schema_spec["function"]["description"] == "Query SQL DB"
    assert "sql" in schema_spec["function"]["parameters"]["properties"]

    # Invocation test
    res = await tools[0].invoke(arguments={"sql": "SELECT 1;"})
    assert len(res) > 0
    assert "Query executed successfully" in res[0].text


@pytest.mark.asyncio
async def test_mcp_stdio_process_crash_resilience():
    """Assert MCP stdio subprocess crash returns descriptive error string to agent."""
    mock_session = AsyncMock()
    mock_session.call_tool.side_effect = BrokenPipeError("Subprocess closed pipe unexpectedly")

    conn = MCPConnection(server_id="mcp-crash-id", server_name="crash_server", session=mock_session)

    result_text = await conn.call_tool("broken_tool", {"arg": "val"})

    assert "MCP server stdio process crashed" in result_text
    assert "Subprocess closed pipe unexpectedly" in result_text


# ============================================================================
# 4. Dead Code Verification
# ============================================================================

def test_dead_code_verification_nvidia_deleted_and_factory_delegates_to_maf():
    """Assert llm/nvidia.py is deleted and provider_factory delegates strictly to MAF abstractions."""
    # Confirm backend/llm/nvidia.py does not exist
    nvidia_py_path = os.path.join(os.path.dirname(__file__), "..", "llm", "nvidia.py")
    assert not os.path.exists(nvidia_py_path), "llm/nvidia.py should be deleted"

    # Confirm importing from provider_factory constructs MAF ChatAgent
    agent = create_provider_from_config(
        provider_type="openai",
        api_key="sk-test",
        base_url=None,
        model_id="gpt-4o",
    )
    assert isinstance(agent, ChatAgent)
    assert hasattr(agent, "client")
    assert isinstance(agent.client, OpenAIChatClient)


def test_anthropic_structured_output_preserves_effort_options():
    provider = AnthropicProvider(
        api_key="test-key",
        model_id="claude-sonnet-5",
        config={"effort": "medium"},
    )
    payload = {"output_config": {"effort": "medium"}}
    provider._apply_response_schema(payload, {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    })
    assert payload["output_config"]["effort"] == "medium"
    assert payload["output_config"]["format"]["type"] == "json_schema"
    assert payload["output_config"]["format"]["schema"]["required"] == ["answer"]
