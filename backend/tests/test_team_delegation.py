"""
Pure-logic tests for the call_teammate delegation tool (team_delegation_tools.py).
No DB, no network, no LLM calls — these exercise teammate resolution, the
depth-limit guard, and argument validation using lightweight fake agent
objects, mirroring both the SQLAlchemy-object and Mongo-dict agent shapes
used throughout the app.
"""
import json

import pytest

from team_delegation_tools import (
    CALL_TEAMMATE_TOOL_SCHEMA,
    MAX_DELEGATION_DEPTH,
    execute_call_teammate,
    is_call_teammate_tool,
)


class FakeAgentSQLite:
    """Mimics the attribute-access shape of a SQLAlchemy Agent row."""
    def __init__(self, id_, name):
        self.id = id_
        self.name = name


def make_mongo_agent(id_, name):
    """Mimics the dict shape of a Mongo agent document."""
    return {"_id": id_, "name": name}


def test_is_call_teammate_tool():
    assert is_call_teammate_tool("call_teammate") is True
    assert is_call_teammate_tool("call_teammate_x") is False
    assert is_call_teammate_tool("web_search") is False


def test_schema_has_required_fields():
    fn = CALL_TEAMMATE_TOOL_SCHEMA["function"]
    assert fn["name"] == "call_teammate"
    params = fn["parameters"]
    assert set(params["required"]) == {"teammate_name", "message"}
    assert "teammate_name" in params["properties"]
    assert "message" in params["properties"]


async def test_invalid_json_arguments_returns_error():
    result = await execute_call_teammate(
        "not valid json{{", agents_with_providers=[], current_agent_id=1, db_type="sqlite", db=None,
    )
    data = json.loads(result)
    assert "error" in data


async def test_missing_teammate_name_returns_error():
    result = await execute_call_teammate(
        json.dumps({"message": "hello"}),
        agents_with_providers=[], current_agent_id=1, db_type="sqlite", db=None,
    )
    data = json.loads(result)
    assert "error" in data
    assert "required" in data["error"]


async def test_missing_message_returns_error():
    result = await execute_call_teammate(
        json.dumps({"teammate_name": "Researcher"}),
        agents_with_providers=[], current_agent_id=1, db_type="sqlite", db=None,
    )
    data = json.loads(result)
    assert "error" in data


async def test_depth_limit_blocks_further_delegation():
    roster = [(FakeAgentSQLite(2, "Researcher"), None)]
    result = await execute_call_teammate(
        json.dumps({"teammate_name": "Researcher", "message": "hi"}),
        agents_with_providers=roster, current_agent_id=1, db_type="sqlite", db=None,
        depth=MAX_DELEGATION_DEPTH,
    )
    data = json.loads(result)
    assert "error" in data
    assert "depth" in data["error"].lower()


async def test_unknown_teammate_lists_available_names_sqlite():
    roster = [
        (FakeAgentSQLite(1, "Coder"), None),
        (FakeAgentSQLite(2, "Researcher"), None),
    ]
    result = await execute_call_teammate(
        json.dumps({"teammate_name": "GhostAgent", "message": "hi"}),
        agents_with_providers=roster, current_agent_id=1, db_type="sqlite", db=None,
    )
    data = json.loads(result)
    assert "error" in data
    assert "Coder" in data["error"]
    assert "Researcher" in data["error"]


async def test_unknown_teammate_lists_available_names_mongo():
    roster = [
        (make_mongo_agent("a1", "Coder"), None),
        (make_mongo_agent("a2", "Researcher"), None),
    ]
    result = await execute_call_teammate(
        json.dumps({"teammate_name": "GhostAgent", "message": "hi"}),
        agents_with_providers=roster, current_agent_id="a1", db_type="mongo", db=None,
    )
    data = json.loads(result)
    assert "error" in data
    assert "Coder" in data["error"]
    assert "Researcher" in data["error"]


async def test_cannot_delegate_to_self_sqlite():
    # Only "self" in the roster and no one else — should resolve to "not found",
    # since the current agent is excluded from its own candidate pool.
    roster = [(FakeAgentSQLite(1, "SoloAgent"), None)]
    result = await execute_call_teammate(
        json.dumps({"teammate_name": "SoloAgent", "message": "hi"}),
        agents_with_providers=roster, current_agent_id=1, db_type="sqlite", db=None,
    )
    data = json.loads(result)
    assert "error" in data


async def test_teammate_name_matching_is_case_insensitive():
    # Case-insensitive matching is resolved BEFORE any LLM/provider setup, so
    # a match means execute_call_teammate proceeds past name-resolution into
    # building a real LLM call — which our minimal fake agent can't support
    # (it's missing model_id/system_prompt/etc). Any error past that point is
    # caught and returned as a clean JSON error (see the try/except wrapping
    # LLM setup + call), never an unhandled exception — and critically, it's
    # NOT the "no teammate found" error, proving the case-insensitive match
    # itself succeeded.
    roster = [(FakeAgentSQLite(2, "Researcher"), None)]
    result = await execute_call_teammate(
        json.dumps({"teammate_name": "RESEARCHER", "message": "hi"}),
        agents_with_providers=roster, current_agent_id=1, db_type="sqlite", db=None,
    )
    data = json.loads(result)
    assert "error" in data
    assert "No teammate named" not in data["error"]
    assert "failed to respond" in data["error"]
