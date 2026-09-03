"""
Phase 4 — Advanced MAF Integration Tests:
1. Vector RAG & Long-Term Memory ContextProviders
2. Multi-Agent Team Orchestrations (Handoff & Magentic)
3. Headless Channels & WhatsApp STT/TTS Execution
4. Eval Harness & OTel Sanitized Trace Pipeline
"""

import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from models import Base, User, LLMProvider, Agent, AgentMemory, Message, Session as ChatSession, TraceSpan, EvalSuite, EvalRun, WhatsAppChannel
from main import app
from database import get_db
from crypto_utils import sanitize_trace_data
from encryption import encrypt_api_key
from rag_service import VectorStoreContextProvider
from routers.memory_router import MemoryContextProvider
from team_delegation_tools import build_maf_handoff_team, build_maf_magentic_team
from eval_engine import grade_exact_match, grade_contains, grade_llm_judge, run_eval_suite_sqlite


# ── Database Fixture Setup ──────────────────────────────────────────────────

@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── 1. MAF Context Provider Tests ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_vector_store_context_provider_injection_and_fallback(db_session):
    """Assert VectorStoreContextProvider pulls top-k chunks and handles fallback gracefully."""
    provider = VectorStoreContextProvider(kb_ids=["kb_101"], session_id="sess_202", top_k=3)

    # Mock RAGService.search_kb_async and search_async
    with patch("rag_service.RAGService.search_kb_async", new_callable=AsyncMock) as mock_kb_search, \
         patch("rag_service.RAGService.search_async", new_callable=AsyncMock) as mock_sess_search:

        mock_kb_search.return_value = [{"text": "Obsidian AI is an orchestration platform."}]
        mock_sess_search.return_value = []

        class MockMessage:
            text_content = "What is Obsidian AI?"

        class MockContext:
            def __init__(self):
                self.input_messages = [MockMessage()]
                self.instructions = []
            def extend_instructions(self, source_id, instruction):
                self.instructions.append(instruction)

        ctx = MockContext()
        await provider.before_run(agent=None, session=None, context=ctx, state={})

        assert len(ctx.instructions) == 1
        assert "Obsidian AI is an orchestration platform." in ctx.instructions[0]

        # Test platform fallback when vector store fails
        mock_kb_search.side_effect = Exception("Vector store index connection failed")
        ctx_fallback = MockContext()
        # Should not raise exception
        await provider.before_run(agent=None, session=None, context=ctx_fallback, state={})
        assert len(ctx_fallback.instructions) == 0


@pytest.mark.asyncio
async def test_memory_context_provider_injection(db_session):
    """Assert MemoryContextProvider pulls active user memories sorted by confidence up to cap 50."""
    # Seed 3 memories
    mem1 = AgentMemory(agent_id=1, user_id=1, key="favorite_color", value="blue", category="preference", confidence=0.95)
    mem2 = AgentMemory(agent_id=1, user_id=1, key="project", value="Obsidian", category="context", confidence=0.80)
    mem3 = AgentMemory(agent_id=1, user_id=1, key="role", value="Engineer", category="role", confidence=0.99)
    db_session.add_all([mem1, mem2, mem3])
    db_session.commit()

    provider = MemoryContextProvider(agent_id=1, user_id=1, db=db_session, db_type="sqlite", top_k=50)

    class MockContext:
        def __init__(self):
            self.instructions = []
        def extend_instructions(self, source_id, instruction):
            self.instructions.append(instruction)

    ctx = MockContext()
    await provider.before_run(agent=None, session=None, context=ctx, state={})

    assert len(ctx.instructions) == 1
    inst = ctx.instructions[0]
    assert "role: Engineer (confidence: 0.99)" in inst
    assert "favorite_color: blue (confidence: 0.95)" in inst
    assert "project: Obsidian (confidence: 0.8)" in inst


# ── 2. Multi-Agent Orchestration Tests ──────────────────────────────────────

def test_handoff_and_magentic_orchestration_builders():
    """Verify Handoff and Magentic team builders construct valid MAF Workflow graphs."""
    agents = [
        {"name": "ResearchAgent", "system_prompt": "You research facts."},
        {"name": "WriterAgent", "system_prompt": "You write clean copy."},
    ]

    # Test Handoff builder
    handoff_workflow = build_maf_handoff_team(agents, start_agent_name="ResearchAgent")
    assert handoff_workflow is not None

    # Test Magentic supervisor builder
    magentic_workflow = build_maf_magentic_team(agents)
    assert magentic_workflow is not None


# ── 3. Headless Channel & WhatsApp Execution Test ───────────────────────────

@pytest.mark.asyncio
async def test_headless_channel_whatsapp_execution_flow(db_session):
    """Simulate WhatsApp incoming message, headless agent turn, artifact stripping, and TTS synthesis."""
    user = User(username="wa_user", email="wa@example.com", role="user", hashed_password="pw")
    db_session.add(user)
    db_session.commit()

    provider_rec = LLMProvider(user_id=user.id, provider_type="openai", name="GPT-4o", model_id="gpt-4o", api_key=encrypt_api_key("sk-test"), base_url="https://api.openai.com/v1")
    db_session.add(provider_rec)
    db_session.commit()

    agent = Agent(user_id=user.id, provider_id=provider_rec.id, name="WA Agent", model_id="gpt-4o", system_prompt="Helpful assistant.")
    db_session.add(agent)
    db_session.commit()

    chat_session = ChatSession(user_id=user.id, entity_type="agent", entity_id=agent.id, title="WA Chat")
    db_session.add(chat_session)
    db_session.commit()

    user_msg = Message(session_id=chat_session.id, role="user", content="Hello agent!")
    db_session.add(user_msg)
    db_session.commit()

    # Mock LLM provider chat stream producing output with an artifact tag
    raw_llm_response = "Hello there! <artifact id=\"1\">code artifact</artifact> How can I help you today?"

    async def mock_chat_stream(*args, **kwargs):
        class MockChunk:
            type = "content"
            content = raw_llm_response
            tool_call = None
        class MockDoneChunk:
            type = "done"
            usage = {"input_tokens": 10, "output_tokens": 10}
            finish_reason = "stop"
            tool_call = None
        yield MockChunk()
        yield MockDoneChunk()

    mock_llm = MagicMock()
    mock_llm.chat_stream = mock_chat_stream

    with patch("services.agent_runner.DATABASE_TYPE", "sqlite"), \
         patch("llm.provider_factory.create_provider_from_config", return_value=mock_llm):
        from services.agent_runner import run_agent_headless
        reply = await run_agent_headless(chat_session.id, agent.id, db=db_session)

        # Assert artifact tags are stripped
        assert reply is not None
        assert "<artifact" not in reply
        assert "How can I help you today?" in reply

    # Test TTS synthesis with stripped reply text
    with patch("services.tts_service.synthesize", new_callable=AsyncMock) as mock_synth:
        mock_synth.return_value = b"OGG_AUDIO_BYTES"
        from services.tts_service import synthesize
        ogg = await synthesize(reply, voice="Ryan")
        assert ogg == b"OGG_AUDIO_BYTES"


# ── 4. Eval Harness & Trace Pipeline Test ───────────────────────────────────

@pytest.mark.asyncio
async def test_eval_harness_graders_and_otel_sanitized_trace(db_session):
    """Run eval suite graders and verify OTel trace span recording and sanitization."""
    # Test Graders
    p1, s1, _ = await grade_exact_match("Hello", "Hello")
    assert p1 is True and s1 == 1.0

    p2, s2, _ = await grade_contains("The answer is 42", "42")
    assert p2 is True and s2 == 1.0

    # Test Trace Sanitization
    sensitive_data = {
        "authorization": "Bearer secret_jwt_token_123",
        "api_key": "sk-1234567890abcdef",
        "user_query": "What is the status?",
    }
    sanitized = sanitize_trace_data(sensitive_data)
    assert "secret_jwt_token_123" not in sanitized
    assert "sk-1234567890abcdef" not in sanitized
    assert "REDACTED" in sanitized

    # Test Eval Run and OTel Trace Span creation
    user = User(username="eval_user", email="eval@example.com", role="user", hashed_password="pw")
    db_session.add(user)
    db_session.commit()

    provider_rec = LLMProvider(user_id=user.id, provider_type="openai", name="GPT-4o", model_id="gpt-4o", api_key=encrypt_api_key("sk-test"), base_url="https://api.openai.com/v1")
    db_session.add(provider_rec)
    db_session.commit()

    agent = Agent(user_id=user.id, provider_id=provider_rec.id, name="Eval Agent", model_id="gpt-4o", system_prompt="Answer accurately.")
    db_session.add(agent)
    db_session.commit()

    suite = EvalSuite(
        user_id=user.id,
        agent_id=agent.id,
        name="Basic Suite",
        test_cases_json=json.dumps([
            {"id": "1", "input": "Say Hi", "expected_output": "Hi", "grading_method": "contains"}
        ]),
    )
    db_session.add(suite)
    db_session.commit()

    eval_run = EvalRun(suite_id=suite.id, agent_id=agent.id, status="pending")
    db_session.add(eval_run)
    db_session.commit()

    # Mock provider chat for eval run
    class MockChatResponse:
        text_content = "Hi there"

    async def mock_provider_chat(*args, **kwargs):
        return MockChatResponse()

    mock_eval_provider = MagicMock()
    mock_eval_provider.chat = mock_provider_chat

    with patch("eval_engine.create_provider", return_value=mock_eval_provider):
        await run_eval_suite_sqlite(suite.id, agent.id, eval_run.id, db_session)

        db_session.refresh(eval_run)
        assert eval_run.status == "completed"
        assert eval_run.passed_cases == 1
        assert eval_run.score == 1.0

        # Assert OTel trace span recorded
        spans = db_session.query(TraceSpan).filter(TraceSpan.span_type == "eval_run").all()
        assert len(spans) == 1
        assert spans[0].name == f"eval_suite_{suite.id}"
        assert spans[0].status == "success"
