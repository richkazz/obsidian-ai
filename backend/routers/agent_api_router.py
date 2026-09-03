import json
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import Agent, AgentVersion, AgentAPIConfig, Application, ApplicationAgentAccess, SchemaVersion, APIRequest
from auth import get_current_user, get_application_api_key, TokenData, ApplicationKeyData
from schemas import AgentAPIConfigCreate, ExternalInvokeRequest
from services.schema_validation_service import validate_json_schema

router = APIRouter(prefix="/api/v1", tags=["agent-api"])
STATES = {"draft", "testing", "published", "deprecated", "retired"}

def require_owner_agent(db, agent_id, user_id):
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.user_id == int(user_id)).first()
    if not agent: raise HTTPException(404, "Agent not found")
    return agent

def config_for(db, agent_id):
    config = db.query(AgentAPIConfig).filter(AgentAPIConfig.agent_id == agent_id).first()
    if not config: raise HTTPException(404, "Agent is not exposed through the API")
    return config

def parse(value, fallback):
    try: return json.loads(value) if value else fallback
    except json.JSONDecodeError: return fallback

def assert_scope(key, required):
    if not set(required).issubset(set(key.scopes)):
        raise HTTPException(403, detail={"code": "INSUFFICIENT_SCOPE", "message": "API key lacks a required scope"})

def authorize_agent(db, key, agent_id, permission):
    config = config_for(db, agent_id)
    assert_scope(key, parse(config.required_scopes_json, [permission]))
    # Owning applications and explicit, non-revoked allowlist entries can use
    # the agent. Knowing an agent ID alone is never sufficient.
    if config.owner_application_id == int(key.application_id): return config
    grant = db.query(ApplicationAgentAccess).filter(ApplicationAgentAccess.application_id == int(key.application_id), ApplicationAgentAccess.agent_id == agent_id, ApplicationAgentAccess.revoked_at.is_(None)).first()
    if not grant or permission not in parse(grant.permissions_json, []):
        raise HTTPException(403, detail={"code": "AGENT_ACCESS_DENIED", "message": "Application is not allowed to access this agent"})
    return config

@router.get("/agent-api-configs/{agent_id}")
@router.get("/agents/{agent_id}/api-config")
def get_agent_api_config(agent_id: int, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    require_owner_agent(db, agent_id, user.user_id)
    config = db.query(AgentAPIConfig).filter(AgentAPIConfig.agent_id == agent_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Agent API configuration not found")
    return {
        "agent_id": str(agent_id),
        "owner_application_id": str(config.owner_application_id) if config.owner_application_id else None,
        "publication_state": config.publication_state,
        "input_schema_version_id": str(config.input_schema_version_id) if config.input_schema_version_id else None,
        "output_schema_version_id": str(config.output_schema_version_id) if config.output_schema_version_id else None,
        "required_scopes": parse(config.required_scopes_json, []),
        "rate_limit": config.rate_limit,
    }

@router.put("/agents/{agent_id}/api-config")
def configure_agent_api(agent_id: int, body: AgentAPIConfigCreate, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    require_owner_agent(db, agent_id, user.user_id)
    for version_id in (body.input_schema_version_id, body.output_schema_version_id):
        if version_id:
            version = db.query(SchemaVersion).filter(SchemaVersion.id == int(version_id)).first()
            if not version: raise HTTPException(422, "Schema version not found")
    if body.owner_application_id:
        app = db.query(Application).filter(Application.id == int(body.owner_application_id), Application.user_id == int(user.user_id)).first()
        if not app: raise HTTPException(422, "Application must belong to the agent owner")
    config = db.query(AgentAPIConfig).filter(AgentAPIConfig.agent_id == agent_id).first()
    fields = dict(owner_application_id=int(body.owner_application_id) if body.owner_application_id else None, input_schema_version_id=int(body.input_schema_version_id) if body.input_schema_version_id else None, output_schema_version_id=int(body.output_schema_version_id) if body.output_schema_version_id else None, required_scopes_json=json.dumps(body.required_scopes), rate_limit=body.rate_limit)
    if config:
        for k, v in fields.items(): setattr(config, k, v)
    else: config = AgentAPIConfig(agent_id=agent_id, **fields); db.add(config)
    db.commit(); db.refresh(config)
    return {"agent_id": str(agent_id), "publication_state": config.publication_state, "input_schema_version_id": str(config.input_schema_version_id) if config.input_schema_version_id else None, "output_schema_version_id": str(config.output_schema_version_id) if config.output_schema_version_id else None}

@router.post("/agents/{agent_id}/publish")
def publish_agent(agent_id: int, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    agent = require_owner_agent(db, agent_id, user.user_id); config = config_for(db, agent_id)
    if not config.input_schema_version_id or not config.output_schema_version_id: raise HTTPException(422, "Published API agents require input and output schemas")
    latest = db.query(AgentVersion).filter(AgentVersion.agent_id == agent_id).order_by(AgentVersion.version_number.desc()).first()
    if not latest:
        from routers.agents_router import _snapshot_agent_sqlite
        latest = _snapshot_agent_sqlite(db, agent, "Published API version")
    # Pin contract versions onto the immutable agent-version record; later schema
    # edits create new schema versions and cannot silently alter this deployment.
    latest.input_schema_version_id = config.input_schema_version_id
    latest.output_schema_version_id = config.output_schema_version_id
    config.publication_state = "published"; config.published_version_id = latest.id; db.commit()
    return {"agent_id": str(agent_id), "agent_version": latest.version_number, "publication_state": "published"}

@router.post("/agents/{agent_id}/{action}")
def transition_agent(agent_id: int, action: str, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    if action not in {"deprecate", "retire", "testing"}: raise HTTPException(404, "Unknown lifecycle action")
    require_owner_agent(db, agent_id, user.user_id); config = config_for(db, agent_id)
    config.publication_state = {"deprecate": "deprecated", "retire": "retired", "testing": "testing"}[action]; db.commit()
    return {"agent_id": str(agent_id), "publication_state": config.publication_state}

@router.post("/agent-invocations/{agent_id}")
async def invoke_agent(agent_id: int, body: ExternalInvokeRequest, db: Session = Depends(get_db), key: ApplicationKeyData = Depends(get_application_api_key)):
    """Invoke through the existing runner and enforce JSON contracts at both boundaries."""
    started = time.monotonic(); request_id = str(uuid.uuid4()); config = authorize_agent(db, key, agent_id, "agent:invoke")
    if config.publication_state not in {"published", "testing"}: raise HTTPException(409, detail={"code": "AGENT_NOT_AVAILABLE", "request_id": request_id})
    if config.publication_state == "published" and body.version is not None:
        published = db.query(AgentVersion).filter(AgentVersion.id == config.published_version_id).first()
        if not published or published.version_number != body.version: raise HTTPException(404, detail={"code": "PUBLISHED_VERSION_NOT_FOUND", "request_id": request_id})
    input_schema = db.get(SchemaVersion, config.input_schema_version_id); output_schema = db.get(SchemaVersion, config.output_schema_version_id)
    if not input_schema or not output_schema:
        raise HTTPException(422, detail={"code": "SCHEMA_VERSION_NOT_FOUND", "message": "Configured schema version is missing", "request_id": request_id})
    input_errors = validate_json_schema(json.loads(input_schema.canonical_schema_json), body.input)
    if input_errors: raise HTTPException(422, detail={"code": "INPUT_SCHEMA_VALIDATION_FAILED", "request_id": request_id, "details": input_errors})

    output_schema_dict = json.loads(output_schema.canonical_schema_json)

    # Pre-supplied output path for non-LLM/testing integrations
    if body.output is not None:
        output = body.output
        errors = validate_json_schema(output_schema_dict, output)
        if errors:
            db.add(APIRequest(request_id=request_id, application_id=int(key.application_id), api_key_id=int(key.api_key_id), agent_id=agent_id, agent_version_id=config.published_version_id, status="failed", error_code="OUTPUT_SCHEMA_VALIDATION_FAILED", duration_ms=int((time.monotonic()-started)*1000))); db.commit()
            raise HTTPException(status_code=502, detail={"error": {"code": "OUTPUT_SCHEMA_VALIDATION_FAILED", "message": "Supplied output failed schema validation", "request_id": request_id, "details": errors}})
        db.add(APIRequest(request_id=request_id, application_id=int(key.application_id), api_key_id=int(key.api_key_id), agent_id=agent_id, agent_version_id=config.published_version_id, status="completed", duration_ms=int((time.monotonic()-started)*1000))); db.commit()
        version = db.get(AgentVersion, config.published_version_id)
        return {"request_id": request_id, "agent_id": str(agent_id), "agent_version": version.version_number if version else None, "input_schema_version": input_schema.version_number, "output_schema_version": output_schema.version_number, "status": "completed", "output": output}

    # Output validation & single bounded repair attempt
    from models import Session as ChatSession, Message
    from services.agent_runner import run_agent_headless
    agent = db.get(Agent, agent_id)
    session = ChatSession(user_id=agent.user_id, title="API invocation", entity_type="agent", entity_id=agent_id)
    db.add(session); db.flush(); db.add(Message(session_id=session.id, role="user", content=json.dumps(body.input))); db.commit()

    output = None

    try:
        raw = await run_agent_headless(session.id, agent_id, db)
        output = json.loads(raw or "")
        errors = validate_json_schema(output_schema_dict, output)
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        errors = [f"Output is not valid JSON: {str(e)}"]

    # If validation failed on initial attempt, execute bounded repair attempt (exactly 1 retry)
    if errors:
        try:
            repair_prompt = f"The previous output failed schema validation with errors: {errors}. Please return a corrected valid JSON object matching the required schema."
            db.add(Message(session_id=session.id, role="user", content=repair_prompt))
            db.commit()
            raw_repair = await run_agent_headless(session.id, agent_id, db)
            output = json.loads(raw_repair or "")
            errors = validate_json_schema(output_schema_dict, output)
        except Exception as e:
            errors = [f"Repair attempt failed: {str(e)}"]

    if errors:
        db.add(APIRequest(request_id=request_id, application_id=int(key.application_id), api_key_id=int(key.api_key_id), agent_id=agent_id, agent_version_id=config.published_version_id, status="failed", error_code="OUTPUT_SCHEMA_VALIDATION_FAILED", duration_ms=int((time.monotonic()-started)*1000))); db.commit()
        raise HTTPException(status_code=502, detail={"error": {"code": "OUTPUT_SCHEMA_VALIDATION_FAILED", "message": "Agent output failed schema validation", "request_id": request_id, "details": errors}})
    db.add(APIRequest(request_id=request_id, application_id=int(key.application_id), api_key_id=int(key.api_key_id), agent_id=agent_id, agent_version_id=config.published_version_id, status="completed", duration_ms=int((time.monotonic()-started)*1000))); db.commit()
    version = db.get(AgentVersion, config.published_version_id)
    return {"request_id": request_id, "agent_id": str(agent_id), "agent_version": version.version_number if version else None, "input_schema_version": input_schema.version_number, "output_schema_version": output_schema.version_number, "status": "completed", "output": output}
