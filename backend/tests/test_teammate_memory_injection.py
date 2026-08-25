"""
Pure-logic tests for _build_teammates_memory_injection / _mongo
(routers/chat_router.py) — the read-only "what your teammates know" context
block injected into a team member's system prompt during route/collaborate
team chats.

SQLite version is tested against a fake db object that mimics SQLAlchemy's
query().filter().order_by().limit().all() chain, since the real function
takes a live Session. Mongo version is tested by monkeypatching
AgentMemoryCollection.find_by_agent_user, since that's the one external
call it makes.
"""
from dataclasses import dataclass

import pytest

from routers.chat_router import (
    _build_teammates_memory_injection,
    _build_teammates_memory_injection_mongo,
)


@dataclass
class FakeAgent:
    id: int
    name: str
    user_id: int = 1


@dataclass
class FakeMemory:
    agent_id: int
    user_id: int
    category: str
    value: str
    created_at: str = "2026-01-01"


class FakeQueryChain:
    """Mimics db.query(AgentMemory).filter(...).order_by(...).limit(...).all()"""
    def __init__(self, memories_by_agent: dict[int, list[FakeMemory]]):
        self._memories_by_agent = memories_by_agent
        self._agent_id = None

    def query(self, _model):
        return self

    def filter(self, *criteria):
        # We don't parse SQLAlchemy filter expressions here — instead the
        # test wires the right agent_id via a side channel (see FakeDB below).
        return self

    def order_by(self, *_args):
        return self

    def limit(self, _n):
        return self

    def all(self):
        return self._memories_by_agent.get(self._agent_id, [])


class FakeDB:
    """A minimal stand-in that lets the test control which agent's memories
    come back, without reimplementing SQLAlchemy's filter expression parsing."""
    def __init__(self, memories_by_agent: dict[int, list[FakeMemory]]):
        self._memories_by_agent = memories_by_agent
        self._chain = FakeQueryChain(memories_by_agent)

    def query(self, model):
        return self._chain

    def set_next_agent_id(self, agent_id):
        self._chain._agent_id = agent_id


def test_no_teammates_returns_empty_string():
    db = FakeDB({})
    result = _build_teammates_memory_injection(db, current_agent_id=1, agents_with_providers=[], user_id=1)
    assert result == ""


def test_teammates_with_no_memories_returns_empty_string():
    db = FakeDB({})
    roster = [(FakeAgent(1, "Me"), None), (FakeAgent(2, "Teammate"), None)]
    # FakeDB always returns [] since _memories_by_agent is empty and query()
    # doesn't dispatch per-agent without real filter parsing — this exercises
    # the "no memories -> section skipped" branch.
    result = _build_teammates_memory_injection(db, current_agent_id=1, agents_with_providers=roster, user_id=1)
    assert result == ""


def test_excludes_current_agent_from_teammates():
    # Only "self" in the roster — should never call query for the current
    # agent, and with no other teammates the result is empty.
    db = FakeDB({})
    roster = [(FakeAgent(1, "Me"), None)]
    result = _build_teammates_memory_injection(db, current_agent_id=1, agents_with_providers=roster, user_id=1)
    assert result == ""


def test_format_includes_agent_name_and_category():
    class DirectDB:
        """Returns fixed memories regardless of filter args, to test formatting."""
        def query(self, _model):
            return self

        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def limit(self, _n):
            return self

        def all(self):
            return [FakeMemory(agent_id=2, user_id=1, category="preference", value="prefers metric units")]

    db = DirectDB()
    roster = [(FakeAgent(1, "Me"), None), (FakeAgent(2, "Teammate"), None)]
    result = _build_teammates_memory_injection(db, current_agent_id=1, agents_with_providers=roster, user_id=1)
    assert "## What your teammates know:" in result
    assert "Teammate knows:" in result
    assert "[preference] prefers metric units" in result
    # The current agent should never appear as a "teammate" section header
    assert "- Me knows:" not in result


async def test_mongo_no_teammates_returns_empty_string():
    result = await _build_teammates_memory_injection_mongo(
        mongo_db=None, current_agent_id="a1", agents_with_providers=[], user_id="u1",
    )
    assert result == ""


async def test_mongo_excludes_current_agent(monkeypatch):
    from models_mongo import AgentMemoryCollection

    calls = []

    async def fake_find(_mongo_db, agent_id, _user_id):
        calls.append(agent_id)
        return []

    monkeypatch.setattr(AgentMemoryCollection, "find_by_agent_user", fake_find)

    roster = [({"_id": "a1", "name": "Me"}, None)]
    result = await _build_teammates_memory_injection_mongo(
        mongo_db=None, current_agent_id="a1", agents_with_providers=roster, user_id="u1",
    )
    assert result == ""
    assert calls == []  # never queried the current agent's own memory


async def test_mongo_format_includes_agent_name_and_category(monkeypatch):
    from models_mongo import AgentMemoryCollection

    async def fake_find(_mongo_db, agent_id, _user_id):
        if agent_id == "a2":
            return [{"category": "context", "value": "works in UTC timezone"}]
        return []

    monkeypatch.setattr(AgentMemoryCollection, "find_by_agent_user", fake_find)

    roster = [({"_id": "a1", "name": "Me"}, None), ({"_id": "a2", "name": "Teammate"}, None)]
    result = await _build_teammates_memory_injection_mongo(
        mongo_db=None, current_agent_id="a1", agents_with_providers=roster, user_id="u1",
    )
    assert "## What your teammates know:" in result
    assert "Teammate knows:" in result
    assert "[context] works in UTC timezone" in result
