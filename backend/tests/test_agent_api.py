import os
os.environ["DATABASE_TYPE"] = "sqlite"

import pytest
import config
config.DATABASE_TYPE = "sqlite"

from fastapi.testclient import TestClient
from main import app
from database import get_db, Base, engine
from models import User, Application, APIKey, Agent, Schema, SchemaVersion, AgentAPIConfig
from auth import create_access_token
from services.api_key_service import generate_api_key

client = TestClient(app)

@pytest.fixture
def setup_data():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        # Create test user
        user = User(username="testuser", email="test@example.com", hashed_password="pw", role="admin")
        db.add(user)
        db.flush()

        # Create user token
        token = create_access_token({"user_id": str(user.id), "username": user.username, "role": user.role, "token_type": "user"})

        # Create application
        app_obj = Application(user_id=user.id, name="Test App", status="active", default_scopes_json='["agent:invoke", "agent:read"]')
        db.add(app_obj)
        db.flush()

        # Create API key
        import json
        from services.api_key_service import hash_api_key
        prefix, secret, full_key = generate_api_key()
        key_record = APIKey(
            application_id=app_obj.id,
            name="Test Key",
            key_prefix=prefix,
            secret_hash=hash_api_key(secret),
            scopes_json=json.dumps(["agent:invoke", "agent:read"])
        )
        db.add(key_record)
        db.flush()

        # Create Schemas
        input_schema = Schema(user_id=user.id, name="Input Schema", direction="input")
        db.add(input_schema)
        db.flush()
        in_ver = SchemaVersion(
            schema_id=input_schema.id,
            version_number=1,
            canonical_schema_json='{"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}',
            source_format="json_schema"
        )
        db.add(in_ver)

        output_schema = Schema(user_id=user.id, name="Output Schema", direction="output")
        db.add(output_schema)
        db.flush()
        out_ver = SchemaVersion(
            schema_id=output_schema.id,
            version_number=1,
            canonical_schema_json='{"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}',
            source_format="json_schema"
        )
        db.add(out_ver)
        db.flush()

        # Create Agent
        agent = Agent(user_id=user.id, name="Test Agent", is_active=True)
        db.add(agent)
        db.flush()

        # Expose and publish agent
        api_config = AgentAPIConfig(
            agent_id=agent.id,
            owner_application_id=app_obj.id,
            publication_state="published",
            input_schema_version_id=in_ver.id,
            output_schema_version_id=out_ver.id,
            required_scopes_json='["agent:invoke"]'
        )
        db.add(api_config)
        db.commit()

        yield {
            "user": user,
            "user_token": token,
            "app": app_obj,
            "api_key": full_key,
            "agent": agent,
            "input_schema": input_schema,
            "output_schema": output_schema,
            "in_ver": in_ver,
            "out_ver": out_ver
        }
    finally:
        db.close()

def test_get_agent_api_config(setup_data):
    token = setup_data["user_token"]
    agent_id = setup_data["agent"].id

    # GET via agent-api-configs route
    res = client.get(f"/api/v1/agent-api-configs/{agent_id}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["agent_id"] == str(agent_id)
    assert data["publication_state"] == "published"

    # GET via agents/{id}/api-config route
    res2 = client.get(f"/api/v1/agents/{agent_id}/api-config", headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 200
    assert res2.json()["agent_id"] == str(agent_id)

def test_auth_header_flexibility(setup_data):
    agent_id = setup_data["agent"].id
    key = setup_data["api_key"]

    # Test Bearer header
    payload = {"input": {"query": "hello"}, "output": {"answer": "world"}}
    res = client.post(
        f"/api/v1/agent-invocations/{agent_id}",
        headers={"Authorization": f"Bearer {key}"},
        json=payload
    )
    assert res.status_code == 200
    assert res.json()["status"] == "completed"
    assert res.json()["output"] == {"answer": "world"}

    # Test X-API-Key header
    res2 = client.post(
        f"/api/v1/agent-invocations/{agent_id}",
        headers={"X-API-Key": key},
        json=payload
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "completed"

def test_application_key_preferred_over_user_bearer(setup_data):
    agent_id = setup_data["agent"].id
    payload = {"input": {"query": "hello"}, "output": {"answer": "world"}}
    res = client.post(
        f"/api/v1/agent-invocations/{agent_id}",
        headers={
            "Authorization": f"Bearer {setup_data['user_token']}",
            "X-API-Key": setup_data["api_key"],
        },
        json=payload,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "completed"

def test_presupplied_output_validation_failure(setup_data):
    agent_id = setup_data["agent"].id
    key = setup_data["api_key"]

    # Invalid output supplied (missing required 'answer' property)
    payload = {"input": {"query": "hello"}, "output": {"invalid_field": 123}}
    res = client.post(
        f"/api/v1/agent-invocations/{agent_id}",
        headers={"Authorization": f"Bearer {key}"},
        json=payload
    )
    assert res.status_code == 502
    data = res.json()
    assert data["detail"]["error"]["code"] == "OUTPUT_SCHEMA_VALIDATION_FAILED"

def test_external_session_is_application_bound(setup_data):
    from models import Session, Message, Application, APIKey
    from services.api_key_service import hash_api_key
    import json
    db = next(get_db())
    try:
        session = Session(
            user_id=setup_data["user"].id,
            application_id=setup_data["app"].id,
            title="Bug report",
            entity_type="agent",
            entity_id=setup_data["agent"].id,
        )
        db.add(session)
        db.flush()
        db.add(Message(session_id=session.id, role="user", content="checkout screenshot"))
        db.commit()
        response = client.get(
            f"/api/v1/agent-sessions/{session.id}/messages",
            headers={"Authorization": f"Bearer {setup_data['api_key']}"},
        )
        assert response.status_code == 200
        assert response.json()["messages"][0]["content"] == "checkout screenshot"

        other_app = Application(user_id=setup_data["user"].id, name="Other", status="active")
        db.add(other_app)
        db.flush()
        other_prefix, other_secret, other_full_key = generate_api_key()
        db.add(APIKey(
            application_id=other_app.id,
            name="Other Key",
            key_prefix=other_prefix,
            secret_hash=hash_api_key(other_secret),
            scopes_json=json.dumps(["agent:read"]),
        ))
        db.commit()
        response = client.get(
            f"/api/v1/agent-sessions/{session.id}/messages",
            headers={"Authorization": f"Bearer {other_full_key}"},
        )
        assert response.status_code == 404
    finally:
        db.close()

def test_meta_schema_validation(setup_data):
    token = setup_data["user_token"]

    # Invalid JSON schema
    invalid_schema = {
        "name": "Bad Schema",
        "direction": "input",
        "canonical_schema": {"type": "unsupported_type_xyz"}
    }
    res = client.post(
        "/api/v1/schemas",
        headers={"Authorization": f"Bearer {token}"},
        json=invalid_schema
    )
    assert res.status_code == 422
    assert "INVALID_JSON_SCHEMA" in res.text

def test_external_attachment_requires_data_or_url():
    from pydantic import ValidationError
    from schemas import ExternalInvokeRequest

    with pytest.raises(ValidationError):
        ExternalInvokeRequest(input={"query": "hello"}, attachments=[{
            "filename": "empty.png",
            "media_type": "image/png",
            "file_type": "image",
        }])


def test_external_invoke_supports_session_context():
    from schemas import ExternalInvokeRequest

    request = ExternalInvokeRequest(
        input={"query": "hello"},
        system_instruction="Answer in bullets.",
        knowledge_base_ids=["1", "2", "3"],
    )

    assert request.system_instruction == "Answer in bullets."
    assert request.knowledge_base_ids == ["1", "2", "3"]
