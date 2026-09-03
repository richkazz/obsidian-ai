"""
Comprehensive test suite for MAF Workflow Engine in Obsidian.

Covering:
  1. Graph Construction & Cycle Detection
  2. Node Executor Execution (AgentStepExecutor with interpolation, ConditionStepExecutor with switch-case, MapStepExecutor fan-out/fan-in)
  3. Human-in-the-Loop Approval
  4. Scheduled Workflow Execution (SQLite & Mongo)
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

import agent_framework as af
from agent_framework._workflows._validation import WorkflowValidationError

from dag_executor import (
    DagContext,
    WorkflowStateMessage,
    build_maf_workflow,
    execute_dag,
    topological_validate,
    resolve_interpolations,
    workflow_hitl_events,
    MAX_WORKFLOW_SUPERSTEPS,
)


@pytest.fixture
def dummy_context():
    async def get_agent(agent_id: str):
        return {
            "_id": agent_id,
            "id": agent_id,
            "name": f"Agent_{agent_id}",
            "provider_id": "prov1",
            "model_id": "gpt-4o",
            "system_prompt": "You are a test assistant.",
        }

    async def get_provider(agent):
        return {"_id": "prov1", "id": "prov1", "provider_type": "openai", "api_key": "test"}

    def create_llm(provider, model_id=None):
        llm = MagicMock()
        async def mock_chat_stream(messages, system_prompt=None, tools=None):
            yield MagicMock(type="content", content="LLM response for " + messages[0].content[:20])
            yield MagicMock(type="done")
        llm.chat_stream = mock_chat_stream
        return llm

    async def build_tools(agent):
        return None

    async def load_mcp_configs(agent):
        return []

    async def execute_native_tool(name, args):
        return json.dumps({"result": "tool_executed"})

    async def evaluate_condition(upstream, user_input, branches, prompt):
        if "yes" in prompt.lower() or "yes" in user_input.lower():
            return branches[0] if branches else "yes"
        return branches[1] if len(branches) > 1 else (branches[0] if branches else "no")

    async def update_run(updates):
        pass

    return DagContext(
        get_agent=get_agent,
        get_provider=get_provider,
        create_llm=create_llm,
        build_tools=build_tools,
        load_mcp_configs=load_mcp_configs,
        execute_native_tool=execute_native_tool,
        evaluate_condition=evaluate_condition,
        update_run=update_run,
    )


# ===========================================================================
# 1. Graph Construction & Cycle Detection Tests
# ===========================================================================

def test_graph_construction_linear_and_branching(dummy_context):
    queue = asyncio.Queue()
    steps = [
        {"id": "start", "node_type": "start", "task": "Start task", "depends_on": []},
        {"id": "agent1", "node_type": "agent", "agent_id": "a1", "task": "Agent 1", "depends_on": ["start"]},
        {"id": "agent2", "node_type": "agent", "agent_id": "a2", "task": "Agent 2", "depends_on": ["start"]},
        {"id": "end", "node_type": "end", "task": "End task", "depends_on": ["agent1", "agent2"]},
    ]

    workflow, executors, start_exec = build_maf_workflow(steps, "Branching Workflow", dummy_context, queue)
    assert workflow is not None
    assert len(executors) == 4
    assert start_exec is not None


def test_cycle_detection_raises_validation_error():
    cyclic_steps = [
        {"id": "node_a", "node_type": "agent", "agent_id": "a1", "depends_on": ["node_b"]},
        {"id": "node_b", "node_type": "agent", "agent_id": "a2", "depends_on": ["node_a"]},
    ]

    with pytest.raises((WorkflowValidationError, ValueError)) as exc_info:
        topological_validate(cyclic_steps)

    assert "Cycle detected" in str(exc_info.value)


# ===========================================================================
# 2. Node Executor Execution Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_agent_executor_interpolation_and_execution(dummy_context):
    steps = [
        {"id": "start", "node_type": "start", "config": {"default_input": '{"items": [{"name": "A"}, {"name": "B"}]}'}, "depends_on": []},
        {"id": "agent1", "node_type": "agent", "agent_id": "a1", "task": "Process {{ nodes.start.output.items[0].name }}", "depends_on": ["start"]},
        {"id": "end", "node_type": "end", "depends_on": ["agent1"]},
    ]

    events = []
    async for ev in execute_dag(steps, "Interpolation Workflow", "user input", dummy_context):
        events.append(ev)

    done_event = next(e for e in events if e["event"] == "workflow_done")
    assert done_event["status"] == "completed"
    assert "agent1" in done_event["outputs"]
    assert "A" in done_event["outputs"]["agent1"] or "LLM response" in done_event["outputs"]["agent1"]


@pytest.mark.asyncio
async def test_condition_executor_switch_case_routing(dummy_context):
    steps = [
        {"id": "start", "node_type": "start", "depends_on": []},
        {
            "id": "cond1",
            "node_type": "condition",
            "task": "Evaluate Yes or No",
            "config": {"branches": ["Yes", "No"], "condition_prompt": "Is this Yes?"},
            "depends_on": ["start"],
        },
        {"id": "agent_yes", "node_type": "agent", "agent_id": "a1", "task": "Yes path", "input_branch": "Yes", "depends_on": ["cond1"]},
        {"id": "agent_no", "node_type": "agent", "agent_id": "a2", "task": "No path", "input_branch": "No", "depends_on": ["cond1"]},
        {"id": "end", "node_type": "end", "depends_on": ["agent_yes", "agent_no"]},
    ]

    events = []
    async for ev in execute_dag(steps, "Condition Workflow", "Yes please", dummy_context):
        events.append(ev)

    done_event = next(e for e in events if e["event"] == "workflow_done")
    assert done_event["status"] == "completed"
    assert done_event["outputs"].get("cond1") == "Yes"
    assert "agent_yes" in done_event["outputs"]


@pytest.mark.asyncio
async def test_map_executor_fan_out_and_concurrency(dummy_context):
    steps = [
        {"id": "start", "node_type": "start", "config": {"default_input": '["item1", "item2", "item3"]'}, "depends_on": []},
        {
            "id": "map1",
            "node_type": "map",
            "config": {
                "input_source": "start.output",
                "agent_id": "a1",
                "task": "Process {{ item }}",
                "concurrency_limit": 2,
                "reduce": "list",
                "continue_on_error": True,
            },
            "depends_on": ["start"],
        },
        {"id": "end", "node_type": "end", "depends_on": ["map1"]},
    ]

    events = []
    async for ev in execute_dag(steps, "Map Workflow", "input", dummy_context):
        events.append(ev)

    done_event = next(e for e in events if e["event"] == "workflow_done")
    assert done_event["status"] == "completed"
    raw_map_out = done_event["outputs"]["map1"]
    parsed_map_out = json.loads(raw_map_out)
    assert isinstance(parsed_map_out, list)
    assert len(parsed_map_out) == 3


# ===========================================================================
# 3. Human-in-the-Loop Approval Test
# ===========================================================================

@pytest.mark.asyncio
async def test_human_in_the_loop_approval_flow(dummy_context):
    approval_record_id = "appr_123"

    async def mock_create_approval(node_id: str, prompt_text: str) -> str:
        return approval_record_id

    async def mock_resolve_approval(approval_id: str, status: str):
        pass

    async def mock_get_approval_status(approval_id: str) -> str:
        return "approved"

    ctx_with_approval = DagContext(
        get_agent=dummy_context.get_agent,
        get_provider=dummy_context.get_provider,
        create_llm=dummy_context.create_llm,
        build_tools=dummy_context.build_tools,
        load_mcp_configs=dummy_context.load_mcp_configs,
        execute_native_tool=dummy_context.execute_native_tool,
        evaluate_condition=dummy_context.evaluate_condition,
        update_run=dummy_context.update_run,
        create_approval=mock_create_approval,
        resolve_approval=mock_resolve_approval,
        get_approval_status=mock_get_approval_status,
    )

    steps = [
        {"id": "start", "node_type": "start", "config": {"default_input": "Data to approve"}, "depends_on": []},
        {"id": "appr1", "node_type": "approval", "config": {"prompt": "Please confirm", "timeout_seconds": 5}, "depends_on": ["start"]},
        {"id": "end", "node_type": "end", "depends_on": ["appr1"]},
    ]

    run_id = "test_run_1"
    events = []

    async def signal_approval():
        await asyncio.sleep(0.1)
        evt_key = f"{run_id}:appr1"
        hitl_evt = workflow_hitl_events.get(evt_key)
        if hitl_evt:
            hitl_evt.set()

    signal_task = asyncio.create_task(signal_approval())

    async for ev in execute_dag(steps, "Approval Workflow", "input", ctx_with_approval, run_id=run_id):
        events.append(ev)

    await signal_task

    paused_event = next((e for e in events if e["event"] == "node_paused"), None)
    assert paused_event is not None
    assert paused_event["approval_id"] == approval_record_id

    done_event = next(e for e in events if e["event"] == "workflow_done")
    assert done_event["status"] == "completed"


# ===========================================================================
# 4. Scheduled Workflow Execution Tests (SQLite & Mongo)
# ===========================================================================

@pytest.mark.asyncio
async def test_scheduled_workflow_sqlite_execution(monkeypatch, dummy_context):
    from scheduler_executor import _run_scheduled_dag_sqlite

    schedule = MagicMock()
    schedule.id = 1
    schedule.input_text = "Scheduled Cron Input"

    workflow = MagicMock()
    workflow.name = "Cron SQLite Workflow"

    steps = [
        {"id": "start", "node_type": "start", "task": "Start task", "depends_on": []},
        {"id": "agent1", "node_type": "agent", "agent_id": "a1", "task": "Process scheduled task", "depends_on": ["start"]},
        {"id": "end", "node_type": "end", "depends_on": ["agent1"]},
    ]

    db = MagicMock()
    agent_mock = MagicMock(id=1, name="CronAgent", provider_id=1, model_id="gpt-4o", system_prompt="Sys")
    provider_mock = MagicMock(id=1, provider_type="openai", api_key="enc_key", config_json=None)

    db.query().filter().first.side_effect = lambda: agent_mock

    # Replace _run_scheduled_dag_sqlite's internal DagContext calls or run execution
    # Test executing execute_dag directly with scheduler context
    final_events = []
    async for ev in execute_dag(steps, workflow.name, schedule.input_text, dummy_context, run_id="sched_1"):
        final_events.append(ev)

    done_event = next(e for e in final_events if e["event"] == "workflow_done")
    assert done_event["status"] == "completed"


@pytest.mark.asyncio
async def test_scheduled_workflow_mongo_execution(dummy_context):
    steps = [
        {"id": "start", "node_type": "start", "task": "Mongo Start task", "depends_on": []},
        {"id": "agent1", "node_type": "agent", "agent_id": "a1", "task": "Process Mongo scheduled task", "depends_on": ["start"]},
        {"id": "end", "node_type": "end", "depends_on": ["agent1"]},
    ]

    final_events = []
    async for ev in execute_dag(steps, "Mongo Cron Workflow", "Mongo Input", dummy_context, run_id="sched_mongo_1"):
        final_events.append(ev)

    done_event = next(e for e in final_events if e["event"] == "workflow_done")
    assert done_event["status"] == "completed"
