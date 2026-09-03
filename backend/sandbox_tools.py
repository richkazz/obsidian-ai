"""
Sandbox tools — Docker-proxied file/shell tools wrapped as MAF FunctionTools.

All 9 Docker sandbox tools are generated as MAF FunctionTool instances bound
to the active container session context.
"""

import asyncio
import json
import subprocess
import sys
from typing import Any, Callable

from agent_framework import FunctionTool, tool


def _double_slash(path: str) -> str:
    """Convert /path to //path to prevent Git Bash MSYS path mangling on Windows."""
    if sys.platform == "win32" and path.startswith("/") and not path.startswith("//"):
        return "/" + path
    return path


async def _docker_exec(container_id: str, *args: str, stdin_data: bytes | None = None) -> tuple[str, int]:
    """
    Run: docker exec -i [-e TERM=xterm-256color] [-w //workspace] <container> <args...>
    Returns (stdout_text, exit_code).
    Handles Docker daemon errors gracefully.
    """
    loop = asyncio.get_event_loop()
    cmd = ["docker", "exec", "-i", "-e", "TERM=xterm-256color", "-w", "//workspace", container_id, *args]

    def _run():
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            out, _ = proc.communicate(input=stdin_data, timeout=30)
            return out.decode("utf-8", errors="replace"), proc.returncode
        except Exception as e:
            return f"Docker sandbox runtime unavailable: {e}", 1

    try:
        output, code = await loop.run_in_executor(None, _run)
        if code != 0 and any(err in output.lower() for err in ("is the docker daemon running", "cannot connect to the docker daemon", "error during connect", "no such container", "daemon is not running")):
            return f"Docker sandbox runtime unavailable: {output.strip()}", code
        return output, code
    except Exception as e:
        return f"Docker sandbox runtime unavailable: {e}", 1


# ---------------------------------------------------------------------------
# Factory to generate MAF FunctionTools bound to container_id
# ---------------------------------------------------------------------------

def create_sandbox_tools(container_id: str) -> dict[str, FunctionTool]:
    """Generate all 9 sandbox tools as MAF FunctionTool instances bound to active container session."""

    @tool(name="sandbox_bash", description="Run a shell command inside the Docker sandbox. Working directory is /workspace.")
    async def sandbox_bash(command: str) -> str:
        if not command:
            return json.dumps({"error": "No command provided"})
        out, code = await _docker_exec(container_id, "//bin/sh", "-c", command)
        if "Docker sandbox runtime unavailable" in out:
            return out
        return json.dumps({"output": out, "exit_code": code})

    @tool(name="sandbox_read", description="Read the contents of a file inside the Docker sandbox.")
    async def sandbox_read(path: str) -> str:
        p = _double_slash(path)
        if not p:
            return json.dumps({"error": "No path provided"})
        out, code = await _docker_exec(container_id, "cat", p)
        if "Docker sandbox runtime unavailable" in out:
            return out
        if code != 0:
            return json.dumps({"error": out.strip()})
        return out

    @tool(name="sandbox_write", description="Write content to a file inside the Docker sandbox. Creates parent dirs if needed.")
    async def sandbox_write(path: str, content: str) -> str:
        if not path:
            return json.dumps({"error": "No path provided"})
        dir_path = "/".join(path.split("/")[:-1])
        if dir_path:
            out_m, _ = await _docker_exec(container_id, "//bin/sh", "-c", f"mkdir -p {_double_slash(dir_path)}")
            if "Docker sandbox runtime unavailable" in out_m:
                return out_m
        out, code = await _docker_exec(
            container_id, "tee", _double_slash(path),
            stdin_data=content.encode("utf-8"),
        )
        if "Docker sandbox runtime unavailable" in out:
            return out
        return json.dumps({"success": code == 0, "path": path})

    @tool(name="sandbox_ls", description="List files and directories inside the Docker sandbox.")
    async def sandbox_ls(path: str = "//workspace") -> str:
        p = _double_slash(path or "//workspace")
        out, code = await _docker_exec(container_id, "ls", "-la", p)
        if "Docker sandbox runtime unavailable" in out:
            return out
        if code != 0:
            return json.dumps({"error": out.strip()})
        return out

    @tool(name="sandbox_glob", description="Find files matching a pattern inside the Docker sandbox.")
    async def sandbox_glob(pattern: str, directory: str = "//workspace") -> str:
        if not pattern:
            return json.dumps({"error": "No pattern provided"})
        d = _double_slash(directory or "//workspace")
        cmd = f"find {d} -name '{pattern}' 2>/dev/null | head -100"
        out, code = await _docker_exec(container_id, "//bin/sh", "-c", cmd)
        if "Docker sandbox runtime unavailable" in out:
            return out
        return out or "(no matches)"

    @tool(name="sandbox_grep", description="Search file contents for a pattern inside the Docker sandbox.")
    async def sandbox_grep(pattern: str, path: str = "//workspace", recursive: bool = True) -> str:
        if not pattern:
            return json.dumps({"error": "No pattern provided"})
        p = _double_slash(path or "//workspace")
        flags = "-rn" if recursive else "-n"
        cmd = f"grep {flags} '{pattern}' {p} 2>/dev/null | head -100"
        out, code = await _docker_exec(container_id, "//bin/sh", "-c", cmd)
        if "Docker sandbox runtime unavailable" in out:
            return out
        return out or "(no matches)"

    @tool(name="sandbox_delete", description="Delete a file or directory inside the Docker sandbox.")
    async def sandbox_delete(path: str, recursive: bool = False) -> str:
        p = _double_slash(path)
        if not p:
            return json.dumps({"error": "No path provided"})
        flag = "-rf" if recursive else "-f"
        out, code = await _docker_exec(container_id, "rm", flag, p)
        if "Docker sandbox runtime unavailable" in out:
            return out
        return json.dumps({"success": code == 0, "output": out.strip()})

    @tool(name="sandbox_python", description="Execute Python code inside the Docker sandbox and return stdout/stderr.")
    async def sandbox_python(code: str, timeout: int = 30) -> str:
        if not code:
            return json.dumps({"error": "No code provided"})
        t_out = min(int(timeout), 120)
        loop = asyncio.get_event_loop()

        def _run_python():
            try:
                proc = subprocess.Popen(
                    ["docker", "exec", "-i", "-w", "//workspace", container_id, "python3", "-c", code],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                out, _ = proc.communicate(timeout=t_out)
                return out.decode("utf-8", errors="replace"), proc.returncode
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                return f"Error: execution timed out after {t_out}s", 1
            except Exception as e:
                return f"Docker sandbox runtime unavailable: {e}", 1

        try:
            out, code_ = await loop.run_in_executor(None, _run_python)
            if code_ != 0 and any(err in out.lower() for err in ("is the docker daemon running", "cannot connect to the docker daemon", "error during connect", "no such container")):
                return f"Docker sandbox runtime unavailable: {out.strip()}"
            return json.dumps({"output": out, "exit_code": code_})
        except Exception as e:
            return f"Docker sandbox runtime unavailable: {e}"

    @tool(name="sandbox_node", description="Execute JavaScript/TypeScript code inside the Docker sandbox using Node.js.")
    async def sandbox_node(code: str, typescript: bool = False, timeout: int = 30) -> str:
        if not code:
            return json.dumps({"error": "No code provided"})
        t_out = min(int(timeout), 120)

        ext = ".ts" if typescript else ".js"
        tmp_file = f"/workspace/.sandbox_repl_tmp{ext}"
        out_w, _ = await _docker_exec(
            container_id, "//bin/sh", "-c",
            f"cat > {tmp_file}",
            stdin_data=code.encode("utf-8"),
        )
        if "Docker sandbox runtime unavailable" in out_w:
            return out_w

        runner = "ts-node" if typescript else "node"
        loop = asyncio.get_event_loop()

        def _run_node():
            try:
                proc = subprocess.Popen(
                    ["docker", "exec", "-i", "-w", "//workspace", container_id, runner, tmp_file],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                out, _ = proc.communicate(timeout=t_out)
                return out.decode("utf-8", errors="replace"), proc.returncode
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                return f"Error: execution timed out after {t_out}s", 1
            except Exception as e:
                return f"Docker sandbox runtime unavailable: {e}", 1

        try:
            out, code_ = await loop.run_in_executor(None, _run_node)
            await _docker_exec(container_id, "rm", "-f", tmp_file)
            if code_ != 0 and any(err in out.lower() for err in ("is the docker daemon running", "cannot connect to the docker daemon", "error during connect", "no such container")):
                return f"Docker sandbox runtime unavailable: {out.strip()}"
            return json.dumps({"output": out, "exit_code": code_})
        except Exception as e:
            return f"Docker sandbox runtime unavailable: {e}"

    tools = {
        "sandbox_bash": sandbox_bash,
        "sandbox_write": sandbox_write,
        "sandbox_read": sandbox_read,
        "sandbox_ls": sandbox_ls,
        "sandbox_glob": sandbox_glob,
        "sandbox_grep": sandbox_grep,
        "sandbox_delete": sandbox_delete,
        "sandbox_python": sandbox_python,
        "sandbox_node": sandbox_node,
    }
    return tools


# Static tool schema declarations avoiding import-time FunctionTool instantiation
SANDBOX_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "sandbox_bash",
            "description": "Run a shell command inside the Docker sandbox. Working directory is /workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "title": "Command"},
                },
                "required": ["command"],
                "title": "sandbox_bash_input",
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sandbox_write",
            "description": "Write content to a file inside the Docker sandbox. Creates parent dirs if needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "title": "Path"},
                    "content": {"type": "string", "title": "Content"},
                },
                "required": ["path", "content"],
                "title": "sandbox_write_input",
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sandbox_read",
            "description": "Read the contents of a file inside the Docker sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "title": "Path"},
                },
                "required": ["path"],
                "title": "sandbox_read_input",
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sandbox_ls",
            "description": "List files and directories inside the Docker sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "//workspace", "title": "Path"},
                },
                "title": "sandbox_ls_input",
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sandbox_glob",
            "description": "Find files matching a pattern inside the Docker sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "title": "Pattern"},
                    "directory": {"type": "string", "default": "//workspace", "title": "Directory"},
                },
                "required": ["pattern"],
                "title": "sandbox_glob_input",
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sandbox_grep",
            "description": "Search file contents for a pattern inside the Docker sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "title": "Pattern"},
                    "path": {"type": "string", "default": "//workspace", "title": "Path"},
                    "recursive": {"type": "boolean", "default": True, "title": "Recursive"},
                },
                "required": ["pattern"],
                "title": "sandbox_grep_input",
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sandbox_delete",
            "description": "Delete a file or directory inside the Docker sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "title": "Path"},
                    "recursive": {"type": "boolean", "default": False, "title": "Recursive"},
                },
                "required": ["path"],
                "title": "sandbox_delete_input",
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sandbox_python",
            "description": "Execute Python code inside the Docker sandbox and return stdout/stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "title": "Code"},
                    "timeout": {"type": "integer", "default": 30, "title": "Timeout"},
                },
                "required": ["code"],
                "title": "sandbox_python_input",
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sandbox_node",
            "description": "Execute JavaScript/TypeScript code inside the Docker sandbox using Node.js.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "title": "Code"},
                    "typescript": {"type": "boolean", "default": False, "title": "Typescript"},
                    "timeout": {"type": "integer", "default": 30, "title": "Timeout"},
                },
                "required": ["code"],
                "title": "sandbox_node_input",
            },
        },
    },
]


def get_sandbox_tool_schemas(container_id: str | None = None) -> list[dict]:
    """Get JSON schema specs for all 9 sandbox tools."""
    if container_id:
        return [t.to_json_schema_spec() for t in create_sandbox_tools(container_id).values()]
    return list(SANDBOX_TOOL_SCHEMAS)


def is_sandbox_tool(tool_name: str) -> bool:
    """Return True if the tool name is a sandbox tool."""
    return tool_name.startswith("sandbox_")


async def execute_sandbox_tool(tool_name: str, arguments_str: str, container_id: str) -> str:
    """Dispatch a sandbox_* tool call to the container via MAF FunctionTool."""
    tools = create_sandbox_tools(container_id)
    tool_obj = tools.get(tool_name)
    if not tool_obj:
        return json.dumps({"error": f"Unknown sandbox tool: {tool_name}"})

    try:
        args = json.loads(arguments_str) if arguments_str else {}
    except json.JSONDecodeError:
        args = {}

    res = await tool_obj.invoke(arguments=args)
    if isinstance(res, list) and len(res) > 0 and hasattr(res[0], "text"):
        return res[0].text
    return str(res)
