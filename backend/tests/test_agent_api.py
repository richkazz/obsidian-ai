import os
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import config
import auth

# Setup in-memory SQLite database with StaticPool so all sessions share the same database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

from database import Base, get_db
import models
from models import User, Agent, Application, APIKey, AgentAPIConfig, ApplicationAgentAccess, Schema, SchemaVersion
from main import app, _run_sqlite_migrations
from services.api_key_service import generate_api_key, hash_api_key, verify_api_key
from services.schema_validation_service import validate_json_schema
from auth import create_access_token

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module", autouse=True)
def setup_database_tables():
    orig_config_db = config.DATABASE_TYPE
    orig_auth_db = auth.DATABASE_TYPE
    config.DATABASE_TYPE = "sqlite"
    auth.DATABASE_TYPE = "sqlite"

    Base.metadata.create_all(bind=engine)
    _run_sqlite_migrations(engine)
    yield
    Base.metadata.drop_all(bind=engine)

    config.DATABASE_TYPE = orig_config_db
    auth.DATABASE_TYPE = orig_auth_db

@pytest.fixture(autouse=True)
def setup_test_user():
    db = TestingSessionLocal()
    user = db.query(User).filter(User.id == 1).first()
    if not user:
        user = User(id=1, email="developer@example.com", username="developer", role="user", hashed_password="hashed_pass")
        db.add(user)
        db.commit()
    db.close()
    yield

@pytest.fixture
def auth_headers():
    token = create_access_token({"sub": "1", "user_id": "1", "username": "developer", "token_type": "user"})
    return {"Authorization": f"Bearer {token}"}

client = TestClient(app)

def test_api_key_generation_and_hashing():
    prefix, secret, full_key = generate_api_key()
    assert prefix.startswith("oba_")
    assert full_key == f"{prefix}.{secret}"
    hashed = hash_api_key(secret)
    assert verify_api_key(secret, hashed) is True
    assert verify_api_key("wrong_secret", hashed) is False

def test_json_schema_validation_service():
    schema = {
        "type": "object",
        "required": ["name", "age"],
        "properties": {
            "name": {"type": "string", "minLength": 2},
            "age": {"type": "integer", "minimum": 0},
            "role": {"type": "string", "enum": ["admin", "user"]},
            "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1}
        }
    }

    # Valid payload
    valid_data = {"name": "Alice", "age": 30, "role": "user", "tags": ["tag1"]}
    assert validate_json_schema(schema, valid_data) == []

    # Invalid payload - missing required field and bad type
    invalid_data = {"name": "A", "role": "invalid_role", "tags": []}
    errors = validate_json_schema(schema, invalid_data)
    assert len(errors) >= 3

def test_applications_crud(auth_headers):
    # 1. Create application
    res = client.post("/api/v1/applications", json={
        "name": "Integration App",
        "description": "External integration service",
        "default_scopes": ["agent:invoke", "agent:read"]
    }, headers=auth_headers)
    assert res.status_code == 201
    app_data = res.json()
    app_id = app_data["id"]
    assert app_data["name"] == "Integration App"

    # 2. List applications
    res = client.get("/api/v1/applications", headers=auth_headers)
    assert res.status_code == 200
    apps = res.json()
    assert any(a["id"] == app_id for a in apps)

    # 3. Create API key for application
    res = client.post(f"/api/v1/applications/{app_id}/keys", json={
        "name": "Production Key",
        "scopes": ["agent:invoke"]
    }, headers=auth_headers)
    assert res.status_code == 201
    key_data = res.json()
    key_id = key_data["id"]
    api_key_plaintext = key_data["api_key"]
    assert api_key_plaintext.startswith("oba_")

    # 4. List API keys
    res = client.get(f"/api/v1/applications/{app_id}/keys", headers=auth_headers)
    assert res.status_code == 200
    keys = res.json()
    assert len(keys) == 1
    assert keys[0]["id"] == key_id

    # 5. Revoke key
    res = client.post(f"/api/v1/applications/{app_id}/keys/{key_id}/revoke", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["revoked_at"] is not None

def test_schema_management(auth_headers):
    # Create input schema
    res = client.post("/api/v1/schemas", json={
        "name": "Customer Request Schema",
        "direction": "input",
        "canonical_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"}
            }
        }
    }, headers=auth_headers)
    assert res.status_code == 201
    schema_data = res.json()
    schema_id = schema_data["id"]

    # Validate payload against schema version
    version_id = schema_data["latest_version"]["id"]
    res = client.post(f"/api/v1/schemas/{schema_id}/versions/{version_id}/validate", json={
        "payload": {"query": "Hello world"}
    }, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["valid"] is True

    # Create new version
    res = client.post(f"/api/v1/schemas/{schema_id}/versions", json={
        "name": "Customer Request Schema v2",
        "direction": "input",
        "canonical_schema": {
            "type": "object",
            "required": ["query", "user_id"],
            "properties": {
                "query": {"type": "string"},
                "user_id": {"type": "string"}
            }
        }
    }, headers=auth_headers)
    assert res.status_code == 201
    assert res.json()["version_number"] == 2

def test_agent_api_configuration_and_lifecycle(auth_headers):
    db = TestingSessionLocal()
    agent = Agent(id=10, user_id=1, name="Test Support Agent", system_prompt="You are support agent")
    db.add(agent)
    db.commit()
    db.close()

    # Create input and output schemas
    in_schema_res = client.post("/api/v1/schemas", json={
        "name": "Input Schema", "direction": "input",
        "canonical_schema": {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}
    }, headers=auth_headers).json()
    out_schema_res = client.post("/api/v1/schemas", json={
        "name": "Output Schema", "direction": "output",
        "canonical_schema": {"type": "object", "required": ["reply"], "properties": {"reply": {"type": "string"}}}
    }, headers=auth_headers).json()

    in_ver_id = in_schema_res["latest_version"]["id"]
    out_ver_id = out_schema_res["latest_version"]["id"]

    # Configure API Exposure
    res = client.put("/api/v1/agents/10/api-config", json={
        "input_schema_version_id": in_ver_id,
        "output_schema_version_id": out_ver_id,
        "required_scopes": ["agent:invoke"],
        "rate_limit": "100"
    }, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["publication_state"] == "draft"

    # Publish agent
    res = client.post("/api/v1/agents/10/publish", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["publication_state"] == "published"
    assert res.json()["agent_version"] == 1

    # Transition to testing / deprecate / retire
    res = client.post("/api/v1/agents/10/deprecate", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["publication_state"] == "deprecated"

def test_external_agent_invocation(auth_headers, monkeypatch):
    db = TestingSessionLocal()
    agent = Agent(id=20, user_id=1, name="API Agent", system_prompt="Answer JSON")
    db.add(agent)
    db.commit()
    db.close()

    # Create app and API key
    app_res = client.post("/api/v1/applications", json={"name": "Caller App"}, headers=auth_headers).json()
    app_id = app_res["id"]
    key_res = client.post(f"/api/v1/applications/{app_id}/keys", json={"name": "Caller Key", "scopes": ["agent:invoke"]}, headers=auth_headers).json()
    api_key = key_res["api_key"]

    # Share agent with app
    share_res = client.post(f"/api/v1/applications/agents/20/shares", json={
        "application_id": app_id,
        "permissions": ["agent:invoke"]
    }, headers=auth_headers)
    assert share_res.status_code == 201

    # Create schemas and configure agent API
    in_schema = client.post("/api/v1/schemas", json={
        "name": "Input", "direction": "input",
        "canonical_schema": {"type": "object", "required": ["prompt"], "properties": {"prompt": {"type": "string"}}}
    }, headers=auth_headers).json()
    out_schema = client.post("/api/v1/schemas", json={
        "name": "Output", "direction": "output",
        "canonical_schema": {"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string"}}}
    }, headers=auth_headers).json()

    client.put("/api/v1/agents/20/api-config", json={
        "owner_application_id": app_id,
        "input_schema_version_id": in_schema["latest_version"]["id"],
        "output_schema_version_id": out_schema["latest_version"]["id"],
        "required_scopes": ["agent:invoke"]
    }, headers=auth_headers)
    client.post("/api/v1/agents/20/publish", headers=auth_headers)

    # Mock headless agent runner execution
    async def mock_run_agent_headless(session_id, agent_id, db):
        return json.dumps({"answer": "Structured response text"})

    monkeypatch.setattr("services.agent_runner.run_agent_headless", mock_run_agent_headless)

    # 1. Successful Invocation with X-API-Key
    res = client.post("/api/v1/agent-invocations/20", json={
        "input": {"prompt": "Hello world"}
    }, headers={"X-API-Key": api_key})
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] == "completed"
    assert res_data["output"] == {"answer": "Structured response text"}

    # 2. Invocation failure due to input schema mismatch
    res = client.post("/api/v1/agent-invocations/20", json={
        "input": {"wrong_field": 123}
    }, headers={"X-API-Key": api_key})
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "INPUT_SCHEMA_VALIDATION_FAILED"
