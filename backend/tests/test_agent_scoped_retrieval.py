import os
os.environ["DATABASE_TYPE"] = "sqlite"

import pytest
import json
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

import config
config.DATABASE_TYPE = "sqlite"

from main import app
from database import get_db, Base, engine
from models import User, Agent, KnowledgeBase, KnowledgeBaseDocument, UserSecret
from auth import create_access_token

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_embedding_client():
    mock_client = AsyncMock()
    mock_client.embed = AsyncMock(return_value=[0.1] * 768)
    with patch("rag_service.get_embedding_client", return_value=mock_client) as p:
        yield p


@pytest.fixture
def setup_agent_retrieval_data():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        user = User(
            username="retrieval_user",
            email="retrieval_user@example.com",
            hashed_password="hashed_pw",
            role="user"
        )
        db.add(user)
        db.flush()

        from encryption import encrypt_api_key
        secret = UserSecret(
            user_id=user.id,
            name="OpenAI Scoped Key",
            encrypted_value=encrypt_api_key("sk-scoped-test-key-12345"),
        )
        db.add(secret)
        db.commit()

        user_id_val = user.id
        secret_id_val = secret.id

        jwt_token = create_access_token({
            "user_id": str(user_id_val),
            "username": user.username,
            "role": user.role,
            "token_type": "user"
        })
    finally:
        db.close()

    headers = {"Authorization": f"Bearer {jwt_token}"}
    upsert_res = client.put(
        "/knowledge/apps/upsert",
        headers=headers,
        json={
            "app_id": "bug-tracker",
            "external_id": "proj-99",
            "name": "Project Bug Tracker KB",
            "description": "Scoped bug data for Project 99",
            "secret_id": str(secret_id_val),
            "embedding_provider": "openai",
        }
    )
    assert upsert_res.status_code in (200, 201)
    kb_id = str(upsert_res.json()["kb_id"])

    ingest_res = client.post(
        "/knowledge/apps/ingest",
        headers=headers,
        json={
            "app_id": "bug-tracker",
            "external_id": "proj-99",
            "document_external_id": "bug-404",
            "doc_type": "bug_report",
            "title": "Bug #404: High CPU usage in background worker",
            "content": "Background worker CPU usage spikes to 100% when processing large batch payloads.",
            "metadata": {"severity": "critical"}
        }
    )
    assert ingest_res.status_code in (200, 201)

    db = next(get_db())
    try:
        agent = Agent(
            user_id=user_id_val,
            name="Bug Solver Agent",
            model_id="gpt-4o",
            knowledge_base_ids_json=json.dumps([kb_id]),
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        yield {
            "user_id": str(user_id_val),
            "jwt_token": jwt_token,
            "kb_id": kb_id,
            "agent_id": str(agent.id),
        }
    finally:
        db.close()


@pytest.mark.asyncio
async def test_agent_scoped_retrieval_and_dynamic_credentials(setup_agent_retrieval_data):
    """
    Configure an agent with a scoped KB attachment, execute a chat turn,
    assert vector search retrieves the bug details and injects context into the prompt turn
    using resolved dynamic credentials.
    """
    token = setup_agent_retrieval_data["jwt_token"]
    agent_id = setup_agent_retrieval_data["agent_id"]
    kb_id = setup_agent_retrieval_data["kb_id"]

    # Search endpoint check directly
    with patch("services.key_resolution_service.decrypt_api_key", return_value="sk-scoped-test-key-12345"):
        mock_embed = AsyncMock(return_value=[0.1] * 768)
        mock_client = AsyncMock()
        mock_client.embed = mock_embed

        with patch("rag_service.get_embedding_client", return_value=mock_client) as mock_get_client:
            search_res = client.post(
                f"/knowledge-bases/{kb_id}/search",
                headers={"Authorization": f"Bearer {token}"},
                json={"query": "CPU usage spikes"}
            )
            assert search_res.status_code == 200
            assert mock_get_client.called
            call_kwargs = mock_get_client.call_args.kwargs
            assert call_kwargs.get("provider") == "openai"
            assert call_kwargs.get("api_key") == "sk-scoped-test-key-12345"

    # Chat session test
    headers = {"Authorization": f"Bearer {token}"}
    create_sess_res = client.post(
        "/sessions",
        headers=headers,
        json={"entity_type": "agent", "entity_id": str(agent_id), "title": "Bug Chat"}
    )
    assert create_sess_res.status_code in (200, 201)
    session_id = create_sess_res.json()["id"]

    # Execute chat turn and verify context loading
    from routers.chat_router import _build_user_llm_message
    db = next(get_db())
    try:
        kb_record = db.query(KnowledgeBase).filter(KnowledgeBase.id == int(kb_id)).first()
        kb_names = {kb_id: kb_record.name}

        with patch("services.key_resolution_service.decrypt_api_key", return_value="sk-scoped-test-key-12345"):
            mock_embed = AsyncMock(return_value=[0.1] * 768)
            mock_client = AsyncMock()
            mock_client.embed = mock_embed

            with patch("rag_service.get_embedding_client", return_value=mock_client) as mock_get_client:
                user_msg, kb_meta = await _build_user_llm_message(
                    message_text="How can we fix the CPU spike issue in background workers?",
                    session_id=str(session_id),
                    image_parts=[],
                    kb_ids=[kb_id],
                    kb_names=kb_names,
                    owner_id=str(setup_agent_retrieval_data["user_id"]),
                    db=db,
                )

                assert kb_id in [k["id"] for k in kb_meta.get("used_kbs", [])]
                assert "CPU usage spikes" in user_msg.text_content or "Background worker" in user_msg.text_content
                assert mock_get_client.called
                call_kwargs = mock_get_client.call_args.kwargs
                assert call_kwargs.get("provider") == "openai"
                assert call_kwargs.get("api_key") == "sk-scoped-test-key-12345"
    finally:
        db.close()
