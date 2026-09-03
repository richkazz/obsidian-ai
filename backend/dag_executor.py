"""
Shared MAF DAG execution core, built on Microsoft Agent Framework Workflows.

This module uses MAF WorkflowBuilder, Executor, AgentExecutor, FunctionExecutor,
and WorkflowContext to execute visual workflow graphs with support for:
  - Agent nodes with interpolation and retries
  - Condition nodes with switch-case edge routing
  - Approval nodes with human-in-the-loop pauses
  - Map nodes with parallel fan-out concurrency control
  - Graph validation & cycle detection
  - Superstep limits (MAX_WORKFLOW_SUPERSTEPS = 50)
"""
import asyncio
import json
import logging
import re
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

import agent_framework as af
from agent_framework._workflows._validation import WorkflowValidationError, ValidationTypeEnum
from llm.base import LLMMessage
from mcp_client import connect_mcp_server, parse_mcp_tool_name

logger = logging.getLogger(__name__)

MAX_WORKFLOW_SUPERSTEPS = 50
MAX_TOOL_ROUNDS = 10
TOOL_RESULT_PROMPT = "Use this information to answer the user's question."
DEFAULT_APPROVAL_TIMEOUT_SECONDS = 600

# Module-level dictionary for paused approval nodes: "{run_id}:{node_id}" -> asyncio.Event
workflow_hitl_events: dict[str, asyncio.Event] = {}


@dataclass
class DagContext:
    """DB-specific callables the generic executor needs. All async, even where
    the underlying store (SQLite) is sync — wrap sync calls in a trivial async
    function at the call site."""
    get_agent: Callable[[str], Awaitable[Optional[Any]]]
    get_provider: Callable[[Any], Awaitable[Optional[Any]]]
    create_llm: Callable[[Any, Optional[str]], Any]
    build_tools: Callable[[Any], Awaitable[Optional[list]]]
    load_mcp_configs: Callable[[Any], Awaitable[list]]
    execute_native_tool: Callable[[str, str], Awaitable[str]]
    evaluate_condition: Callable[[dict, str, list, str], Awaitable[str]]
    update_run: Callable[[dict], Awaitable[None]]
    create_approval: Optional[Callable[[str, str], Awaitable[str]]] = None
    resolve_approval: Optional[Callable[[str, str], Awaitable[None]]] = None
    get_approval_status: Optional[Callable[[str], Awaitable[str]]] = None
    agent_name: Callable[[Any], str] = lambda agent: getattr(agent, "name", None) or (agent.get("name") if isinstance(agent, dict) else "Unknown")
    agent_id_str: Callable[[Any], str] = lambda agent: str(getattr(agent, "id", None) or (agent.get("_id") if isinstance(agent, dict) else ""))
    agent_provider_id: Callable[[Any], Optional[str]] = lambda agent: getattr(agent, "provider_id", None) or (agent.get("provider_id") if isinstance(agent, dict) else None)
    agent_model_id: Callable[[Any], Optional[str]] = lambda agent: getattr(agent, "model_id", None) or (agent.get("model_id") if isinstance(agent, dict) else None)
    agent_system_prompt: Callable[[Any], Optional[str]] = lambda agent: getattr(agent, "system_prompt", None) or (agent.get("system_prompt") if isinstance(agent, dict) else None)


@dataclass
class WorkflowStateMessage:
    outputs: dict[str, str] = field(default_factory=dict)
    condition_outputs: dict[str, str] = field(default_factory=dict)
    skipped: set[str] = field(default_factory=set)
    user_input: str = ""
    workflow_run_id: Optional[str] = None
    step_results_by_id: dict[str, dict] = field(default_factory=dict)
    failed_nodes: set[str] = field(default_factory=set)
    completed_nodes: set[str] = field(default_factory=set)


def is_dag_workflow(steps: list[dict]) -> bool:
    """True if any step has a stable 'id' field — DAG mode vs legacy linear."""
    return any(s.get("id") for s in steps)


def topological_validate(steps: list[dict]):
    """Raise WorkflowValidationError if the step graph contains an unhandled cycle.
    Iterative-DFS, three-colour marking (white/grey/black)."""
    node_ids = {s["id"] for s in steps if s.get("id")}
    adj: dict[str, list[str]] = {s["id"]: (s.get("depends_on") or []) for s in steps if s.get("id")}

    WHITE, GREY, BLACK = 0, 1, 2
    colour = {n: WHITE for n in node_ids}

    def dfs(node):
        colour[node] = GREY
        for dep in adj.get(node, []):
            if dep not in colour:
                continue
            if colour[dep] == GREY:
                raise WorkflowValidationError(
                    f"Cycle detected in workflow graph involving node '{dep}'",
                    ValidationTypeEnum.GRAPH_CONNECTIVITY
                )
            if colour[dep] == WHITE:
                dfs(dep)
        colour[node] = BLACK

    for node in node_ids:
        if colour[node] == WHITE:
            dfs(node)


def format_dag_input(task: str, upstream_outputs: dict[str, str], user_input: str) -> str:
    if not upstream_outputs:
        return f"Task: {task}\n\nInput:\n{user_input}"
    sections = "\n\n".join(f"Output from step '{nid}':\n{out}" for nid, out in upstream_outputs.items())
    return f"Task: {task}\n\nUpstream context:\n{sections}"


_INTERPOLATION_RE = re.compile(r"\{\{\s*nodes\.([\w-]+)\.output(?:\.([\w.\[\]0-9]+))?\s*\}\}")


def _resolve_path(value, path: str):
    """Walk a dot/bracket path ('items[0].name') into a JSON-decoded value."""
    current = value
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", path):
        if part.startswith("["):
            idx = int(part[1:-1])
            if not isinstance(current, list) or idx >= len(current):
                return None
            current = current[idx]
        else:
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
    return current


def resolve_interpolations(text: str, all_outputs: dict[str, str]) -> str:
    """Replace every `{{ nodes.<node_id>.output }}` or `{{ nodes.<node_id>.output.<path> }}`
    reference in `text` with the referenced node's output."""
    def _replace(m: re.Match) -> str:
        node_id, path = m.group(1), m.group(2)
        if node_id not in all_outputs:
            return ""
        raw = all_outputs[node_id]
        if not path:
            return raw
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return ""
        resolved = _resolve_path(parsed, path)
        if resolved is None:
            return ""
        return resolved if isinstance(resolved, str) else json.dumps(resolved)

    return _INTERPOLATION_RE.sub(_replace, text)


# ---------------------------------------------------------------------------
# Dedicated MAF Executor Subclasses
# ---------------------------------------------------------------------------

class StartNodeExecutor(af.Executor):
    def __init__(self, step_def: dict, ctx_dag: DagContext, sse_queue: asyncio.Queue, **kwargs):
        super().__init__(id=step_def["id"], **kwargs)
        self.step_def = step_def
        self.ctx_dag = ctx_dag
        self.sse_queue = sse_queue

    async def _process(self, msg: WorkflowStateMessage) -> WorkflowStateMessage:
        task = self.step_def.get("task", "")
        cfg = self.step_def.get("config") or {}
        default_input = cfg.get("default_input", "") or task
        start_out = default_input if default_input else msg.user_input

        msg.outputs[self.id] = start_out
        msg.completed_nodes.add(self.id)
        if self.id in msg.step_results_by_id:
            msg.step_results_by_id[self.id].update(
                status="completed", output=start_out,
                started_at=datetime.now(timezone.utc).isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
        await self.sse_queue.put({"event": "node_complete", "node_id": self.id, "agent_name": "Start", "output": start_out})
        return msg

    @af.handler
    async def handle_single(self, msg: WorkflowStateMessage, ctx: af.WorkflowContext[WorkflowStateMessage]) -> None:
        updated = await self._process(msg)
        await ctx.send_message(updated)

    @af.handler
    async def handle_list(self, msgs: list[WorkflowStateMessage], ctx: af.WorkflowContext[WorkflowStateMessage]) -> None:
        merged = _merge_messages(msgs)
        updated = await self._process(merged)
        await ctx.send_message(updated)


class AgentStepExecutor(af.Executor):
    def __init__(self, step_def: dict, ctx_dag: DagContext, sse_queue: asyncio.Queue, **kwargs):
        super().__init__(id=step_def["id"], **kwargs)
        self.step_def = step_def
        self.ctx_dag = ctx_dag
        self.sse_queue = sse_queue

    async def _process(self, msg: WorkflowStateMessage) -> WorkflowStateMessage:
        task = self.step_def.get("task", "")
        agent_id = str(self.step_def.get("agent_id") or "")

        if not agent_id:
            await self._mark_failed(msg, "No agent assigned")
            return msg

        agent = await self.ctx_dag.get_agent(agent_id)
        if not agent:
            await self._mark_failed(msg, "Agent not found")
            return msg

        if not self.ctx_dag.agent_provider_id(agent):
            await self._mark_failed(msg, "Agent has no provider")
            return msg

        provider = await self.ctx_dag.get_provider(agent)
        if not provider:
            await self._mark_failed(msg, "Provider not found")
            return msg

        upstream = {dep: msg.outputs[dep] for dep in (self.step_def.get("depends_on") or []) if dep in msg.outputs}
        resolved_task = resolve_interpolations(task, msg.outputs) if "{{" in task else task
        node_input = format_dag_input(resolved_task, upstream, msg.user_input)

        if self.id in msg.step_results_by_id:
            msg.step_results_by_id[self.id]["status"] = "running"
            msg.step_results_by_id[self.id]["started_at"] = datetime.now(timezone.utc).isoformat()

        await self.sse_queue.put({
            "event": "node_start", "node_id": self.id,
            "agent_id": self.ctx_dag.agent_id_str(agent),
            "agent_name": self.ctx_dag.agent_name(agent),
            "task": task,
        })

        llm = self.ctx_dag.create_llm(provider, self.ctx_dag.agent_model_id(agent))
        native_tools = await self.ctx_dag.build_tools(agent)
        mcp_configs = await self.ctx_dag.load_mcp_configs(agent)
        system_prompt = self.ctx_dag.agent_system_prompt(agent)

        node_config = self.step_def.get("config") or {}
        retry_cfg = node_config.get("retry_config") or {}
        max_attempts = max(int(retry_cfg.get("max_attempts") or 1), 1)
        backoff_mode = retry_cfg.get("backoff", "fixed")
        backoff_seconds = float(retry_cfg.get("backoff_seconds") or 0)
        max_backoff_seconds = float(retry_cfg.get("max_backoff_seconds") or backoff_seconds or 0)
        retryable_errors = retry_cfg.get("retryable_errors")
        timeout_seconds = node_config.get("timeout_seconds")

        async def _attempt() -> str:
            messages = [LLMMessage(role="user", content=node_input)]
            full_content = ""
            mcp_connections: dict = {}

            async def _round_trip(tools):
                nonlocal full_content
                tool_calls_collected = []
                async for chunk in llm.chat_stream(messages, system_prompt=system_prompt, tools=tools):
                    if chunk.type == "content":
                        full_content += chunk.content
                        await self.sse_queue.put({"event": "node_content_delta", "node_id": self.id, "content": chunk.content})
                    elif chunk.type == "tool_call" and chunk.tool_call:
                        tool_calls_collected.append(chunk.tool_call)
                    elif chunk.type == "done":
                        break
                    elif chunk.type == "error":
                        raise Exception(chunk.error)
                return tool_calls_collected

            if mcp_configs:
                async with AsyncExitStack() as stack:
                    all_mcp_tools = []
                    for config in mcp_configs:
                        try:
                            conn = await stack.enter_async_context(connect_mcp_server(config))
                            mcp_connections[conn.server_name] = conn
                            all_mcp_tools.extend(conn.tools)
                        except Exception as e:
                            logger.warning(f"Failed to connect to MCP server {config.get('name')}: {e}")
                    merged_tools = list(native_tools or []) + all_mcp_tools or None

                    for _round in range(MAX_TOOL_ROUNDS + 1):
                        tool_calls_collected = await _round_trip(merged_tools)
                        if not tool_calls_collected:
                            break
                        messages.append(LLMMessage(role="assistant", content=""))
                        for tc in tool_calls_collected:
                            result = await _execute_mcp_or_native(tc.name, tc.arguments, mcp_connections, self.ctx_dag)
                            messages.append(LLMMessage(role="user", content=f"[Tool '{tc.name}' returned: {result}]\n\n{TOOL_RESULT_PROMPT}"))
                        full_content = ""
            else:
                for _round in range(MAX_TOOL_ROUNDS + 1):
                    tool_calls_collected = await _round_trip(native_tools)
                    if not tool_calls_collected:
                        break
                    messages.append(LLMMessage(role="assistant", content=""))
                    for tc in tool_calls_collected:
                        result = await self.ctx_dag.execute_native_tool(tc.name, tc.arguments)
                        messages.append(LLMMessage(role="user", content=f"[Tool '{tc.name}' returned: {result}]\n\n{TOOL_RESULT_PROMPT}"))
                    full_content = ""

            return full_content

        last_error: Exception | None = None
        for attempt_num in range(1, max_attempts + 1):
            try:
                if timeout_seconds:
                    full_content = await asyncio.wait_for(_attempt(), timeout=float(timeout_seconds))
                else:
                    full_content = await _attempt()

                msg.outputs[self.id] = full_content
                msg.completed_nodes.add(self.id)
                if self.id in msg.step_results_by_id:
                    msg.step_results_by_id[self.id].update(
                        status="completed", output=full_content,
                        completed_at=datetime.now(timezone.utc).isoformat(),
                        attempts=attempt_num,
                    )
                await self.sse_queue.put({"event": "node_complete", "node_id": self.id, "agent_name": self.ctx_dag.agent_name(agent), "output": full_content})
                return msg

            except Exception as e:
                last_error = e
                error_name = type(e).__name__
                is_timeout = isinstance(e, asyncio.TimeoutError)
                error_label = "Timed out" if is_timeout else str(e)

                is_retryable = retryable_errors is None or error_name in retryable_errors or (is_timeout and "TimeoutError" in (retryable_errors or []))
                if attempt_num >= max_attempts or not is_retryable:
                    break

                await self.sse_queue.put({
                    "event": "node_retry", "node_id": self.id,
                    "attempt": attempt_num, "max_attempts": max_attempts, "error": error_label,
                })
                if backoff_seconds:
                    delay = backoff_seconds if backoff_mode == "fixed" else backoff_seconds * (2 ** (attempt_num - 1))
                    if max_backoff_seconds:
                        delay = min(delay, max_backoff_seconds)
                    await asyncio.sleep(delay)

        error_label = "Timed out" if isinstance(last_error, asyncio.TimeoutError) else str(last_error)
        await self._mark_failed(msg, error_label)
        return msg

    async def _mark_failed(self, msg: WorkflowStateMessage, error_msg: str):
        msg.failed_nodes.add(self.id)
        if self.id in msg.step_results_by_id:
            msg.step_results_by_id[self.id].update(
                status="failed", error=error_msg,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
        await self.sse_queue.put({"event": "node_error", "node_id": self.id, "error": error_msg})

    @af.handler
    async def handle_single(self, msg: WorkflowStateMessage, ctx: af.WorkflowContext[WorkflowStateMessage]) -> None:
        updated = await self._process(msg)
        await ctx.send_message(updated)

    @af.handler
    async def handle_list(self, msgs: list[WorkflowStateMessage], ctx: af.WorkflowContext[WorkflowStateMessage]) -> None:
        merged = _merge_messages(msgs)
        updated = await self._process(merged)
        await ctx.send_message(updated)


class ConditionStepExecutor(af.Executor):
    def __init__(self, step_def: dict, ctx_dag: DagContext, sse_queue: asyncio.Queue, all_steps: list[dict], **kwargs):
        super().__init__(id=step_def["id"], **kwargs)
        self.step_def = step_def
        self.ctx_dag = ctx_dag
        self.sse_queue = sse_queue
        self.all_steps = all_steps

    async def _process(self, msg: WorkflowStateMessage) -> WorkflowStateMessage:
        task = self.step_def.get("task", "")
        upstream = {dep: msg.outputs[dep] for dep in (self.step_def.get("depends_on") or []) if dep in msg.outputs}
        cfg = self.step_def.get("config") or {}
        branches = cfg.get("branches") or []
        condition_prompt = cfg.get("condition_prompt") or task or ""
        if "{{" in condition_prompt:
            condition_prompt = resolve_interpolations(condition_prompt, msg.outputs)

        try:
            chosen = await self.ctx_dag.evaluate_condition(upstream, msg.user_input, branches, condition_prompt)
        except Exception as e:
            logger.warning(f"Condition evaluation failed for node {self.id}: {e}. Defaulting to first branch.")
            chosen = branches[0] if branches else ""

        msg.condition_outputs[self.id] = chosen
        msg.outputs[self.id] = chosen
        msg.completed_nodes.add(self.id)

        for other in self.all_steps:
            other_id = other.get("id")
            if not other_id or other_id in msg.completed_nodes or other_id in msg.skipped:
                continue
            dep_branch = other.get("input_branch")
            if dep_branch and self.id in (other.get("depends_on") or []) and dep_branch != chosen:
                msg.skipped.add(other_id)
                if other_id in msg.step_results_by_id:
                    msg.step_results_by_id[other_id]["status"] = "skipped"

        if self.id in msg.step_results_by_id:
            msg.step_results_by_id[self.id].update(
                status="completed", output=chosen,
                started_at=datetime.now(timezone.utc).isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
        await self.sse_queue.put({"event": "node_complete", "node_id": self.id, "agent_name": "Condition", "output": chosen})
        return msg

    @af.handler
    async def handle_single(self, msg: WorkflowStateMessage, ctx: af.WorkflowContext[WorkflowStateMessage]) -> None:
        updated = await self._process(msg)
        await ctx.send_message(updated)

    @af.handler
    async def handle_list(self, msgs: list[WorkflowStateMessage], ctx: af.WorkflowContext[WorkflowStateMessage]) -> None:
        merged = _merge_messages(msgs)
        updated = await self._process(merged)
        await ctx.send_message(updated)


class ApprovalStepExecutor(af.Executor):
    def __init__(self, step_def: dict, ctx_dag: DagContext, sse_queue: asyncio.Queue, **kwargs):
        super().__init__(id=step_def["id"], **kwargs)
        self.step_def = step_def
        self.ctx_dag = ctx_dag
        self.sse_queue = sse_queue

    async def _process(self, msg: WorkflowStateMessage) -> WorkflowStateMessage:
        task = self.step_def.get("task", "")
        if not self.ctx_dag.create_approval or not self.ctx_dag.resolve_approval:
            await self._mark_failed(msg, "This run doesn't support approval nodes")
            return msg
        if not msg.workflow_run_id:
            await self._mark_failed(msg, "Approval nodes require a run_id")
            return msg

        upstream = {dep: msg.outputs[dep] for dep in (self.step_def.get("depends_on") or []) if dep in msg.outputs}
        cfg = self.step_def.get("config") or {}
        prompt_text = cfg.get("prompt") or task or "Approval required to continue."
        if "{{" in prompt_text:
            prompt_text = resolve_interpolations(prompt_text, msg.outputs)

        timeout = float(cfg.get("timeout_seconds") or DEFAULT_APPROVAL_TIMEOUT_SECONDS)
        on_timeout = cfg.get("on_timeout", "fail")

        approval_id = await self.ctx_dag.create_approval(self.id, prompt_text)
        event_key = f"{msg.workflow_run_id}:{self.id}"
        hitl_event = asyncio.Event()
        workflow_hitl_events[event_key] = hitl_event

        if self.id in msg.step_results_by_id:
            msg.step_results_by_id[self.id].update(
                status="paused", output=None,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
        await self.sse_queue.put({
            "event": "node_paused", "node_id": self.id,
            "approval_id": approval_id, "prompt": prompt_text,
        })

        try:
            await asyncio.wait_for(hitl_event.wait(), timeout=timeout)
            decision = await self.ctx_dag.get_approval_status(approval_id) if self.ctx_dag.get_approval_status else "approved"
        except asyncio.TimeoutError:
            decision = "approved" if on_timeout == "auto_approve" else "timed_out"
            await self.ctx_dag.resolve_approval(approval_id, "expired")
        finally:
            workflow_hitl_events.pop(event_key, None)

        if decision != "approved":
            error_label = "Approval denied" if decision == "denied" else "Approval timed out"
            await self._mark_failed(msg, error_label)
            return msg

        approved_output = "\n\n".join(upstream.values()) if upstream else ""
        msg.outputs[self.id] = approved_output
        msg.completed_nodes.add(self.id)

        if self.id in msg.step_results_by_id:
            msg.step_results_by_id[self.id].update(
                status="completed", output=approved_output,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
        await self.sse_queue.put({"event": "node_complete", "node_id": self.id, "agent_name": "Approval", "output": approved_output})
        return msg

    async def _mark_failed(self, msg: WorkflowStateMessage, error_msg: str):
        msg.failed_nodes.add(self.id)
        if self.id in msg.step_results_by_id:
            msg.step_results_by_id[self.id].update(
                status="failed", error=error_msg,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
        await self.sse_queue.put({"event": "node_error", "node_id": self.id, "error": error_msg})

    @af.handler
    async def handle_single(self, msg: WorkflowStateMessage, ctx: af.WorkflowContext[WorkflowStateMessage]) -> None:
        updated = await self._process(msg)
        await ctx.send_message(updated)

    @af.handler
    async def handle_list(self, msgs: list[WorkflowStateMessage], ctx: af.WorkflowContext[WorkflowStateMessage]) -> None:
        merged = _merge_messages(msgs)
        updated = await self._process(merged)
        await ctx.send_message(updated)


class MapStepExecutor(af.Executor):
    def __init__(self, step_def: dict, ctx_dag: DagContext, sse_queue: asyncio.Queue, **kwargs):
        super().__init__(id=step_def["id"], **kwargs)
        self.step_def = step_def
        self.ctx_dag = ctx_dag
        self.sse_queue = sse_queue

    async def _process(self, msg: WorkflowStateMessage) -> WorkflowStateMessage:
        task = self.step_def.get("task", "")
        cfg = self.step_def.get("config") or {}
        input_source = cfg.get("input_source", "")
        agent_id = str(cfg.get("agent_id") or "")
        item_task_template = cfg.get("task") or task or "{{ item }}"
        concurrency_limit = max(int(cfg.get("concurrency_limit") or 5), 1)
        reduce_mode = cfg.get("reduce", "list")
        continue_on_error = cfg.get("continue_on_error", True)

        if not agent_id:
            await self._mark_failed(msg, "Map node has no agent configured")
            return msg

        m = re.match(r"^([\w-]+)\.output(?:\.(.+))?$", input_source)
        if not m:
            await self._mark_failed(msg, f"Invalid input_source '{input_source}'")
            return msg

        src_node_id, src_path = m.group(1), m.group(2)
        if src_node_id not in msg.outputs:
            await self._mark_failed(msg, f"Map input source node '{src_node_id}' has no output yet")
            return msg

        try:
            raw = msg.outputs[src_node_id]
            items = json.loads(raw) if not src_path else _resolve_path(json.loads(raw), src_path)
            if not isinstance(items, list):
                raise ValueError("resolved value is not a list")
        except Exception as e:
            await self._mark_failed(msg, f"Map input is not a JSON list: {e}")
            return msg

        agent = await self.ctx_dag.get_agent(agent_id)
        if not agent or not self.ctx_dag.agent_provider_id(agent):
            await self._mark_failed(msg, "Map agent not found or has no provider")
            return msg
        provider = await self.ctx_dag.get_provider(agent)
        if not provider:
            await self._mark_failed(msg, "Map agent's provider not found")
            return msg

        if self.id in msg.step_results_by_id:
            msg.step_results_by_id[self.id]["status"] = "running"
            msg.step_results_by_id[self.id]["started_at"] = datetime.now(timezone.utc).isoformat()

        await self.sse_queue.put({
            "event": "node_start", "node_id": self.id,
            "agent_id": self.ctx_dag.agent_id_str(agent),
            "agent_name": self.ctx_dag.agent_name(agent),
            "task": f"Map over {len(items)} item(s)",
        })

        semaphore = asyncio.Semaphore(concurrency_limit)
        llm = self.ctx_dag.create_llm(provider, self.ctx_dag.agent_model_id(agent))
        native_tools = await self.ctx_dag.build_tools(agent)
        system_prompt = self.ctx_dag.agent_system_prompt(agent)

        async def _run_one_item(index: int, item):
            item_json = item if isinstance(item, str) else json.dumps(item)
            item_task = item_task_template.replace("{{ item }}", item_json).replace("{{item}}", item_json)
            async with semaphore:
                try:
                    messages = [LLMMessage(role="user", content=item_task)]
                    full_content = ""
                    for _round in range(MAX_TOOL_ROUNDS + 1):
                        tool_calls_collected = []
                        async for chunk in llm.chat_stream(messages, system_prompt=system_prompt, tools=native_tools):
                            if chunk.type == "content":
                                full_content += chunk.content
                            elif chunk.type == "tool_call" and chunk.tool_call:
                                tool_calls_collected.append(chunk.tool_call)
                            elif chunk.type == "done":
                                break
                            elif chunk.type == "error":
                                raise Exception(chunk.error)
                        if not tool_calls_collected:
                            break
                        messages.append(LLMMessage(role="assistant", content=""))
                        for tc in tool_calls_collected:
                            result = await self.ctx_dag.execute_native_tool(tc.name, tc.arguments)
                            messages.append(LLMMessage(role="user", content=f"[Tool '{tc.name}' returned: {result}]\n\n{TOOL_RESULT_PROMPT}"))
                        full_content = ""
                    return index, full_content, None
                except Exception as e:
                    return index, None, str(e)

        results = await asyncio.gather(*[_run_one_item(i, item) for i, item in enumerate(items)])
        results.sort(key=lambda r: r[0])

        item_errors = [r for r in results if r[2] is not None]
        item_outputs = [r[1] for r in results if r[2] is None]

        if item_errors and not continue_on_error:
            await self._mark_failed(msg, f"Map execution failed: {item_errors[0][2]}")
            return msg

        if reduce_mode == "concat":
            map_output = "\n\n".join(item_outputs)
        else:
            map_output = json.dumps(item_outputs)

        msg.outputs[self.id] = map_output
        msg.completed_nodes.add(self.id)

        if self.id in msg.step_results_by_id:
            status_kwargs = {"status": "completed", "output": map_output, "completed_at": datetime.now(timezone.utc).isoformat()}
            if item_errors:
                status_kwargs["error"] = f"{len(item_errors)}/{len(items)} item(s) failed"
            msg.step_results_by_id[self.id].update(**status_kwargs)

        await self.sse_queue.put({"event": "node_complete", "node_id": self.id, "agent_name": self.ctx_dag.agent_name(agent), "output": map_output})
        return msg

    async def _mark_failed(self, msg: WorkflowStateMessage, error_msg: str):
        msg.failed_nodes.add(self.id)
        if self.id in msg.step_results_by_id:
            msg.step_results_by_id[self.id].update(
                status="failed", error=error_msg,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
        await self.sse_queue.put({"event": "node_error", "node_id": self.id, "error": error_msg})

    @af.handler
    async def handle_single(self, msg: WorkflowStateMessage, ctx: af.WorkflowContext[WorkflowStateMessage]) -> None:
        updated = await self._process(msg)
        await ctx.send_message(updated)

    @af.handler
    async def handle_list(self, msgs: list[WorkflowStateMessage], ctx: af.WorkflowContext[WorkflowStateMessage]) -> None:
        merged = _merge_messages(msgs)
        updated = await self._process(merged)
        await ctx.send_message(updated)


class EndNodeExecutor(af.Executor):
    def __init__(self, step_def: dict, ctx_dag: DagContext, sse_queue: asyncio.Queue, **kwargs):
        super().__init__(id=step_def["id"], **kwargs)
        self.step_def = step_def
        self.ctx_dag = ctx_dag
        self.sse_queue = sse_queue

    async def _process(self, msg: WorkflowStateMessage) -> WorkflowStateMessage:
        upstream = {dep: msg.outputs[dep] for dep in (self.step_def.get("depends_on") or []) if dep in msg.outputs}
        end_out = "\n\n".join(upstream.values()) if upstream else ""
        msg.outputs[self.id] = end_out
        msg.completed_nodes.add(self.id)

        if self.id in msg.step_results_by_id:
            msg.step_results_by_id[self.id].update(
                status="completed", output=end_out,
                started_at=datetime.now(timezone.utc).isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
        await self.sse_queue.put({"event": "node_complete", "node_id": self.id, "agent_name": "End", "output": end_out})
        return msg

    @af.handler
    async def handle_single(self, msg: WorkflowStateMessage, ctx: af.WorkflowContext[None, WorkflowStateMessage]) -> None:
        updated = await self._process(msg)
        await ctx.yield_output(updated)

    @af.handler
    async def handle_list(self, msgs: list[WorkflowStateMessage], ctx: af.WorkflowContext[None, WorkflowStateMessage]) -> None:
        merged = _merge_messages(msgs)
        updated = await self._process(merged)
        await ctx.yield_output(updated)


def _merge_messages(msgs: list[WorkflowStateMessage]) -> WorkflowStateMessage:
    merged = WorkflowStateMessage()
    for m in msgs:
        merged.outputs.update(m.outputs)
        merged.condition_outputs.update(m.condition_outputs)
        merged.skipped.update(m.skipped)
        merged.step_results_by_id.update(m.step_results_by_id)
        merged.failed_nodes.update(m.failed_nodes)
        merged.completed_nodes.update(m.completed_nodes)
        if m.user_input and not merged.user_input:
            merged.user_input = m.user_input
        if m.workflow_run_id and not merged.workflow_run_id:
            merged.workflow_run_id = m.workflow_run_id
    return merged


async def _execute_mcp_or_native(tc_name, tc_arguments, mcp_connections, ctx: DagContext) -> str:
    parsed = parse_mcp_tool_name(tc_name)
    if parsed:
        server_name, original_tool_name = parsed
        conn = mcp_connections.get(server_name)
        if conn:
            try:
                args = json.loads(tc_arguments) if tc_arguments else {}
            except json.JSONDecodeError:
                args = {}
            return await conn.call_tool(original_tool_name, args)
        return json.dumps({"error": f"MCP server '{server_name}' not connected"})
    return await ctx.execute_native_tool(tc_name, tc_arguments)


# ---------------------------------------------------------------------------
# Workflow Construction & Main Engine Entrypoint
# ---------------------------------------------------------------------------

def create_executor_for_step(step: dict, ctx_dag: DagContext, sse_queue: asyncio.Queue, all_steps: list[dict]) -> af.Executor:
    node_type = step.get("node_type", "agent")
    if node_type == "start":
        return StartNodeExecutor(step, ctx_dag, sse_queue)
    elif node_type == "agent":
        return AgentStepExecutor(step, ctx_dag, sse_queue)
    elif node_type == "condition":
        return ConditionStepExecutor(step, ctx_dag, sse_queue, all_steps)
    elif node_type == "approval":
        return ApprovalStepExecutor(step, ctx_dag, sse_queue)
    elif node_type == "map":
        return MapStepExecutor(step, ctx_dag, sse_queue)
    elif node_type == "end":
        return EndNodeExecutor(step, ctx_dag, sse_queue)
    else:
        return AgentStepExecutor(step, ctx_dag, sse_queue)


def build_maf_workflow(
    steps: list[dict],
    workflow_name: str,
    ctx_dag: DagContext,
    sse_queue: asyncio.Queue,
) -> tuple[af.Workflow, dict[str, af.Executor], af.Executor]:
    """Constructs MAF Workflow graph using WorkflowBuilder.
    Validates graph connectivity and cycle detection."""
    topological_validate(steps)

    executors: dict[str, af.Executor] = {}
    for s in steps:
        nid = s["id"]
        executors[nid] = create_executor_for_step(s, ctx_dag, sse_queue, steps)

    start_node = next((s for s in steps if s.get("node_type") == "start"), steps[0])
    start_executor = executors[start_node["id"]]

    end_nodes = [s for s in steps if s.get("node_type") == "end"]
    output_executors = [executors[e["id"]] for e in end_nodes] if end_nodes else [executors[steps[-1]["id"]]]

    builder = af.WorkflowBuilder(
        start_executor=start_executor,
        max_iterations=MAX_WORKFLOW_SUPERSTEPS,
        name=workflow_name,
        output_from=output_executors,
    )

    added_edges: set[tuple[str, str]] = set()

    # Fan-in edges for non-conditional steps with multiple dependencies
    for s in steps:
        deps = s.get("depends_on") or []
        if len(deps) > 1:
            target_exec = executors[s["id"]]
            source_steps = [next(st for st in steps if st["id"] == dep) for dep in deps if dep in executors]
            # Check if any source step is a conditional branch step
            has_conditional_branch = any(st.get("input_branch") for st in source_steps)
            if not has_conditional_branch:
                source_execs = [executors[st["id"]] for st in source_steps]
                if len(source_execs) > 1:
                    try:
                        builder.add_fan_in_edges(source_execs, target_exec)
                        for dep in deps:
                            added_edges.add((dep, s["id"]))
                    except Exception as e:
                        logger.debug(f"Fan-in group notice for node {s['id']}: {e}")

    # Condition & simple edges
    node_deps: dict[str, list[dict]] = {}
    for s in steps:
        deps = s.get("depends_on") or []
        for dep_id in deps:
            if dep_id in executors:
                node_deps.setdefault(dep_id, []).append(s)

    for source_id, downstream_steps in node_deps.items():
        source_exec = executors[source_id]
        source_step = next(s for s in steps if s["id"] == source_id)
        source_type = source_step.get("node_type", "agent")

        if source_type == "condition":
            cfg = source_step.get("config") or {}
            branches = cfg.get("branches") or []
            cases = []
            grouped_steps = set()
            for b in branches:
                branch_targets = [s for s in downstream_steps if s.get("input_branch") == b]
                for target_step in branch_targets:
                    tid = target_step["id"]
                    if (source_id, tid) in added_edges:
                        continue
                    grouped_steps.add(tid)
                    target_exec = executors[tid]
                    cases.append(af.Case(
                        lambda msg, b=b, sid=source_id: msg.condition_outputs.get(sid) == b,
                        target_exec
                    ))
                    added_edges.add((source_id, tid))

            fallback_targets = [s for s in downstream_steps if s["id"] not in grouped_steps]
            default_exec = output_executors[0]
            if fallback_targets:
                default_exec = executors[fallback_targets[0]["id"]]
                added_edges.add((source_id, fallback_targets[0]["id"]))
            cases.append(af.Default(default_exec))

            if len(cases) >= 1:
                builder.add_switch_case_edge_group(source_exec, cases)
        else:
            unconnected = [s for s in downstream_steps if (source_id, s["id"]) not in added_edges]
            if len(unconnected) > 1:
                target_execs = [executors[s["id"]] for s in unconnected]
                builder.add_fan_out_edges(source_exec, target_execs)
                for s in unconnected:
                    added_edges.add((source_id, s["id"]))
            elif len(unconnected) == 1:
                target_exec = executors[unconnected[0]["id"]]
                builder.add_edge(source_exec, target_exec)
                added_edges.add((source_id, unconnected[0]["id"]))

    workflow = builder.build()
    return workflow, executors, start_executor


async def execute_dag(
    steps: list[dict],
    workflow_name: str,
    user_input: str,
    ctx: DagContext,
    run_id: str | None = None,
) -> AsyncIterator[dict]:
    """The unified MAF DAG execution engine. Yields plain dict events:
      workflow_start, node_start, node_content_delta, node_retry, node_paused,
      node_complete, node_error, workflow_done
    Callers turn these into SSE frames (manual runs) or consume them for side effects.
    """
    sse_queue: asyncio.Queue = asyncio.Queue()

    step_results_by_id: dict[str, dict] = {}
    for i, s in enumerate(steps):
        node_type = s.get("node_type", "agent")
        agent_label = node_type.capitalize()
        if node_type == "agent" and s.get("agent_id"):
            agent = await ctx.get_agent(str(s["agent_id"]))
            agent_label = ctx.agent_name(agent) if agent else "Unknown"
        step_results_by_id[s["id"]] = {
            "node_id": s["id"],
            "order": i + 1,
            "node_type": node_type,
            "agent_id": s.get("agent_id"),
            "agent_name": agent_label,
            "task": s.get("task", ""),
            "status": "pending",
        }

    yield {
        "event": "workflow_start",
        "run_id": None,
        "workflow_name": workflow_name,
        "total_steps": len(steps),
    }

    try:
        workflow, executors, start_exec = build_maf_workflow(steps, workflow_name, ctx, sse_queue)
    except Exception as e:
        logger.exception(f"Workflow graph build failed: {e}")
        yield {
            "event": "workflow_done",
            "status": "failed",
            "completed": 0, "failed": 1, "skipped": 0, "total": len(steps),
            "outputs": {},
            "step_results": list(step_results_by_id.values()),
        }
        return

    init_msg = WorkflowStateMessage(
        outputs={},
        condition_outputs={},
        skipped=set(),
        user_input=user_input,
        workflow_run_id=run_id,
        step_results_by_id=step_results_by_id,
    )

    run_task = asyncio.create_task(workflow.run(init_msg))

    all_node_ids = set(s["id"] for s in steps)
    completed_ids: set[str] = set()
    failed_ids: set[str] = set()
    skipped_ids: set[str] = set()
    running_ids: set[str] = set()
    outputs: dict[str, str] = {}

    while not run_task.done() or not sse_queue.empty():
        while not sse_queue.empty():
            evt = await sse_queue.get()
            evt_type = evt.get("event")
            nid = evt.get("node_id")

            if evt_type == "node_start":
                if nid:
                    running_ids.add(nid)
                await ctx.update_run({
                    "running_nodes_json": json.dumps(list(running_ids)),
                    "steps_json": json.dumps(list(step_results_by_id.values())),
                })
            elif evt_type == "node_complete":
                if nid:
                    completed_ids.add(nid)
                    running_ids.discard(nid)
                    if nid in step_results_by_id:
                        outputs[nid] = step_results_by_id[nid].get("output", "")
                await ctx.update_run({
                    "running_nodes_json": json.dumps(list(running_ids)),
                    "steps_json": json.dumps(list(step_results_by_id.values())),
                })
            elif evt_type == "node_error":
                if nid:
                    failed_ids.add(nid)
                    running_ids.discard(nid)
                await ctx.update_run({
                    "running_nodes_json": json.dumps(list(running_ids)),
                    "steps_json": json.dumps(list(step_results_by_id.values())),
                    "status": "failed",
                    "error": evt.get("error", ""),
                })
            elif evt_type in ("node_paused", "node_retry"):
                if evt_type == "node_paused" and nid:
                    running_ids.discard(nid)
                await ctx.update_run({
                    "running_nodes_json": json.dumps(list(running_ids)),
                    "steps_json": json.dumps(list(step_results_by_id.values())),
                })

            yield evt

        if not run_task.done():
            await asyncio.sleep(0.01)

    try:
        run_res = await run_task
        maf_outputs = run_res.get_outputs() if hasattr(run_res, "get_outputs") else []
        if maf_outputs and isinstance(maf_outputs[0], WorkflowStateMessage):
            final_msg = maf_outputs[0]
            outputs.update(final_msg.outputs)
            skipped_ids.update(final_msg.skipped)
            failed_ids.update(final_msg.failed_nodes)
            completed_ids.update(final_msg.completed_nodes)
    except Exception as e:
        logger.exception(f"Workflow run task failed: {e}")
        failed_ids.add("workflow")

    all_ok = len(failed_ids) == 0 and (len(completed_ids | skipped_ids) >= len(all_node_ids) - len(failed_ids))

    yield {
        "event": "workflow_done",
        "status": "completed" if all_ok else "failed",
        "completed": len(completed_ids),
        "failed": len(failed_ids),
        "skipped": len(skipped_ids),
        "total": len(all_node_ids),
        "outputs": outputs,
        "step_results": list(step_results_by_id.values()),
    }
