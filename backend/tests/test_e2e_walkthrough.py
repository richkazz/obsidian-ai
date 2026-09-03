import json
import pytest
from fastapi.testclient import TestClient
from main import app
from config import DATABASE_TYPE
from database import get_db, SessionLocal, engine, Base
from models import User, LLMProvider, Agent, Application, APIKey, Schema, SchemaVersion, AgentAPIConfig, AuditEvent
from auth import create_access_token

@pytest.fixture(autouse=True)
def setup_db():
    if DATABASE_TYPE == "sqlite":
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == 1).first()
            if not user:
                user = User(id=1, username="adminuser", email="admin@example.com", role="admin", hashed_password="pw")
                db.add(user)
                db.commit()
        finally:
            db.close()
    yield

def get_auth_headers(username="adminuser", user_id="1", role="admin"):
    token = create_access_token({"user_id": user_id, "username": username, "role": role, "token_type": "user"})
    return {"Authorization": f"Bearer {token}"}

def test_full_20_step_e2e_journey():
    if DATABASE_TYPE == "mongo":
        pytest.skip("E2E walkthrough test relies on SQLite test session")

    with TestClient(app) as client:
        headers = get_auth_headers()

        # Step 1: Register Application 1
        res = client.post("/api/v1/applications", json={"name": "Owner App 1", "default_scopes": ["agent:invoke"]}, headers=headers)
        assert res.status_code == 201
        app1_id = res.json()["id"]

        # Step 2: Create API Key for App 1
        res = client.post(f"/api/v1/applications/{app1_id}/keys", json={"name": "App 1 Key", "scopes": ["agent:invoke"]}, headers=headers)
        assert res.status_code == 201
        key1_plaintext = res.json()["api_key"]

        # Step 3: Register Application 2 & Key 2
        res = client.post("/api/v1/applications", json={"name": "Caller App 2", "default_scopes": ["agent:invoke"]}, headers=headers)
        assert res.status_code == 201
        app2_id = res.json()["id"]

        res = client.post(f"/api/v1/applications/{app2_id}/keys", json={"name": "App 2 Key", "scopes": ["agent:invoke"]}, headers=headers)
        assert res.status_code == 201
        key2_plaintext = res.json()["api_key"]

        # Step 4: Create Input Schema
        res = client.post("/api/v1/schemas", json={
            "name": "E2E Input Schema",
            "direction": "input",
            "canonical_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
        }, headers=headers)
        assert res.status_code == 201
        in_schema_id = res.json()["id"]
        in_version_id = res.json()["latest_version"]["id"]

        # Step 5: Create Output Schema
        res = client.post("/api/v1/schemas", json={
            "name": "E2E Output Schema",
            "direction": "output",
            "canonical_schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}
        }, headers=headers)
        assert res.status_code == 201
        out_schema_id = res.json()["id"]
        out_version_id = res.json()["latest_version"]["id"]

        # Step 6: Create Agent
        res = client.post("/agents", json={"name": "E2E Agent", "system_prompt": "You respond in JSON"}, headers=headers)
        assert res.status_code == 200
        agent_id = res.json()["id"]

        # Step 7: Configure Agent API (owned by App 1)
        res = client.put(f"/api/v1/agents/{agent_id}/api-config", json={
            "owner_application_id": app1_id,
            "input_schema_version_id": in_version_id,
            "output_schema_version_id": out_version_id,
            "required_scopes": ["agent:invoke"],
            "rate_limit": "60/minute"
        }, headers=headers)
        assert res.status_code == 200
        assert res.json()["publication_state"] == "draft"

        # Step 8: Publish Agent Version
        res = client.post(f"/api/v1/agents/{agent_id}/publish", headers=headers)
        assert res.status_code == 200
        assert res.json()["publication_state"] == "published"

        # Step 9: Grant App 2 Access (Share Agent)
        res = client.post(f"/api/v1/applications/agents/{agent_id}/shares", json={
            "application_id": app2_id,
            "permissions": ["agent:invoke"]
        }, headers=headers)
        assert res.status_code == 201

        # Step 10: Verify App 2 Key can invoke Agent with Idempotency Key
        idemp_key = "idemp_walkthrough_001"
        res = client.post(f"/api/v1/agent-invocations/{agent_id}", json={
            "input": {"query": "Summarize status"}
        }, headers={"X-API-Key": key2_plaintext, "Idempotency-Key": idemp_key})
        # Note: Unless an LLM provider is connected in test, raw headless runner returns 502 Output Schema Validation or 200.
        # Check that auth and access grant passed (not 401 or 403)
        assert res.status_code in (200, 502)

        # Step 11: Re-send with same Idempotency-Key returns cached response
        res_dup = client.post(f"/api/v1/agent-invocations/{agent_id}", json={
            "input": {"query": "Summarize status"}
        }, headers={"X-API-Key": key2_plaintext, "Idempotency-Key": idemp_key})
        assert res_dup.status_code == res.status_code

        # Step 12: Revoke App 2 access and verify 403 AGENT_ACCESS_DENIED
        db = SessionLocal()
        try:
            from models import ApplicationAgentAccess
            access = db.query(ApplicationAgentAccess).filter(
                ApplicationAgentAccess.application_id == int(app2_id),
                ApplicationAgentAccess.agent_id == int(agent_id)
            ).first()
            if access:
                from datetime import datetime, timezone
                access.revoked_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()

        res_denied = client.post(f"/api/v1/agent-invocations/{agent_id}", json={
            "input": {"query": "Summarize status"}
        }, headers={"X-API-Key": key2_plaintext})
        assert res_denied.status_code == 403
        assert res_denied.json()["detail"]["code"] == "AGENT_ACCESS_DENIED"

        # Step 13: Verify Audit Log Events recorded
        db = SessionLocal()
        try:
            events = db.query(AuditEvent).all()
            assert len(events) >= 3
        finally:
            db.close()
