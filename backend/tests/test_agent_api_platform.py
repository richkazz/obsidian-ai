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
                user = User(id=1, username="testuser", email="testuser@example.com", role="admin", hashed_password="pw")
                db.add(user)
                db.commit()
        finally:
            db.close()
    yield

def get_auth_headers(username="testuser", user_id="1", role="admin"):
    token = create_access_token({"user_id": user_id, "username": username, "role": role, "token_type": "user"})
    return {"Authorization": f"Bearer {token}"}

def test_application_and_api_key_lifecycle():
    if DATABASE_TYPE == "mongo":
        pytest.skip("Test relies on SQLite test DB session")
    with TestClient(app) as client:
        headers = get_auth_headers()
        # 1. Create Application
        res = client.post("/api/v1/applications", json={
            "name": "Test App",
            "description": "App for testing",
            "default_scopes": ["agent:invoke"]
        }, headers=headers)
        assert res.status_code == 201
        app_data = res.json()
        app_id = app_data["id"]
        assert app_data["name"] == "Test App"

        # 2. List Applications
        res = client.get("/api/v1/applications", headers=headers)
        assert res.status_code == 200
        apps = res.json()
        assert len(apps) >= 1

        # 3. Create API Key
        res = client.post(f"/api/v1/applications/{app_id}/keys", json={
            "name": "Default Key",
            "scopes": ["agent:invoke", "agent:read"]
        }, headers=headers)
        assert res.status_code == 201
        key_data = res.json()
        assert "api_key" in key_data
        key_id = key_data["id"]

        # 4. List Keys
        res = client.get(f"/api/v1/applications/{app_id}/keys", headers=headers)
        assert res.status_code == 200
        keys = res.json()
        assert len(keys) == 1

        # 5. Revoke Key
        res = client.post(f"/api/v1/applications/{app_id}/keys/{key_id}/revoke", headers=headers)
        assert res.status_code == 200
        assert res.json()["revoked_at"] is not None

def test_schema_lifecycle():
    if DATABASE_TYPE == "mongo":
        pytest.skip("Test relies on SQLite test DB session")
    with TestClient(app) as client:
        headers = get_auth_headers()
        # 1. Create Schema
        res = client.post("/api/v1/schemas", json={
            "name": "Input Schema",
            "direction": "input",
            "canonical_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        }, headers=headers)
        assert res.status_code == 201
        schema_data = res.json()
        schema_id = schema_data["id"]

        # 2. Add Schema Version
        res = client.post(f"/api/v1/schemas/{schema_id}/versions", json={
            "name": "Input Schema",
            "direction": "input",
            "canonical_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "context": {"type": "string"}},
                "required": ["query"]
            }
        }, headers=headers)
        assert res.status_code == 201
        assert res.json()["version_number"] == 2

        # 3. Validate Schema Payload
        ver_id = res.json()["id"]
        res = client.post(f"/api/v1/schemas/{schema_id}/versions/{ver_id}/validate", json={
            "payload": {"query": "hello"}
        }, headers=headers)
        assert res.status_code == 200
        assert res.json()["valid"] is True

def test_agent_api_configuration_and_publication():
    if DATABASE_TYPE == "mongo":
        pytest.skip("Test relies on SQLite test DB session")
    headers = get_auth_headers()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == 1).first()
        agent = Agent(user_id=user.id, name="Publication Test Agent", system_prompt="Test")
        db.add(agent)
        db.commit()
        db.refresh(agent)
        agent_id = str(agent.id)

        in_s = Schema(user_id=user.id, name="In", direction="input")
        out_s = Schema(user_id=user.id, name="Out", direction="output")
        db.add_all([in_s, out_s])
        db.commit()

        in_v = SchemaVersion(schema_id=in_s.id, version_number=1, canonical_schema_json='{"type":"object"}')
        out_v = SchemaVersion(schema_id=out_s.id, version_number=1, canonical_schema_json='{"type":"object"}')
        db.add_all([in_v, out_v])
        db.commit()

        in_v_id, out_v_id = str(in_v.id), str(out_v.id)
    finally:
        db.close()

    with TestClient(app) as client:
        # 1. Configure Agent API
        res = client.put(f"/api/v1/agents/{agent_id}/api-config", json={
            "input_schema_version_id": in_v_id,
            "output_schema_version_id": out_v_id,
            "required_scopes": ["agent:invoke"],
            "rate_limit": "60/minute"
        }, headers=headers)
        assert res.status_code == 200
        assert res.json()["publication_state"] == "draft"

        # 2. Publish Agent
        res = client.post(f"/api/v1/agents/{agent_id}/publish", headers=headers)
        assert res.status_code == 200
        assert res.json()["publication_state"] == "published"
        assert res.json()["agent_version"] == 1

        # 3. Transition Lifecycle Actions
        for action, expected in [("deprecate", "deprecated"), ("testing", "testing"), ("retire", "retired")]:
            res = client.post(f"/api/v1/agents/{agent_id}/{action}", headers=headers)
            assert res.status_code == 200
            assert res.json()["publication_state"] == expected
