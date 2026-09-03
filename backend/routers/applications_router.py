import os
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import Application, APIKey, Agent, ApplicationAgentAccess
from auth import get_current_user, TokenData
from schemas import ApplicationCreate, ApplicationResponse, APIKeyCreate, APIKeyResponse, APIKeyCreateResponse, AgentShareCreate
from services.api_key_service import generate_api_key, hash_api_key
from services.audit_service import log_audit_event

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])

def is_mongo():
    return os.getenv("DATABASE_TYPE", "sqlite") == "mongo"

def app_response(app, is_mongo_doc=False):
    if is_mongo_doc:
        default_scopes = json.loads(app.get("default_scopes_json", "[]")) if isinstance(app.get("default_scopes_json"), str) else (app.get("default_scopes_json") or [])
        metadata = json.loads(app.get("metadata_json", "null")) if isinstance(app.get("metadata_json"), str) else app.get("metadata")
        return ApplicationResponse(
            id=str(app["_id"]),
            name=app["name"],
            description=app.get("description"),
            status=app.get("status", "active"),
            default_scopes=default_scopes,
            metadata=metadata,
            created_at=app.get("created_at")
        )
    default_scopes = json.loads(app.default_scopes_json or "[]") if isinstance(app.default_scopes_json, str) else (app.default_scopes_json or [])
    metadata = json.loads(app.metadata_json or "null") if isinstance(app.metadata_json, str) else app.metadata_json
    return ApplicationResponse(
        id=str(app.id),
        name=app.name,
        description=app.description,
        status=app.status,
        default_scopes=default_scopes,
        metadata=metadata,
        created_at=app.created_at
    )

def key_response(key, is_mongo_doc=False):
    if is_mongo_doc:
        scopes = json.loads(key.get("scopes_json", "[]")) if isinstance(key.get("scopes_json"), str) else (key.get("scopes") or [])
        return APIKeyResponse(
            id=str(key["_id"]),
            name=key["name"],
            key_prefix=key["key_prefix"],
            scopes=scopes,
            expires_at=key.get("expires_at"),
            revoked_at=key.get("revoked_at"),
            last_used_at=key.get("last_used_at"),
            created_at=key.get("created_at")
        )
    scopes = json.loads(key.scopes_json) if isinstance(key.scopes_json, str) else key.scopes_json
    return APIKeyResponse(
        id=str(key.id),
        name=key.name,
        key_prefix=key.key_prefix,
        scopes=scopes,
        expires_at=key.expires_at,
        revoked_at=key.revoked_at,
        last_used_at=key.last_used_at,
        created_at=key.created_at
    )

async def owned_app(application_id: str, user_id: str, db: Session):
    if is_mongo():
        from database_mongo import get_database
        from models_mongo import ApplicationCollection
        mongo_db = get_database()
        app = await ApplicationCollection.find_by_id(mongo_db, str(application_id))
        if not app or str(app.get("user_id")) != str(user_id):
            raise HTTPException(404, "Application not found")
        return app
    else:
        app = db.query(Application).filter(Application.id == int(application_id), Application.user_id == int(user_id)).first()
        if not app:
            raise HTTPException(404, "Application not found")
        return app

@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(body: ApplicationCreate, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    if is_mongo():
        from database_mongo import get_database
        from models_mongo import ApplicationCollection
        mongo_db = get_database()
        doc = {
            "user_id": str(user.user_id),
            "name": body.name,
            "description": body.description,
            "default_scopes_json": json.dumps(body.default_scopes),
            "metadata_json": json.dumps(body.metadata) if body.metadata is not None else None,
            "status": "active"
        }
        app = await ApplicationCollection.create(mongo_db, doc)
        log_audit_event(db, actor=user.user_id, event_type="application.created", resource_type="application", resource_id=str(app["_id"]), details={"name": body.name})
        return app_response(app, is_mongo_doc=True)

    app = Application(
        user_id=int(user.user_id),
        name=body.name,
        description=body.description,
        default_scopes_json=json.dumps(body.default_scopes),
        metadata_json=json.dumps(body.metadata) if body.metadata is not None else None
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    log_audit_event(db, actor=user.user_id, event_type="application.created", resource_type="application", resource_id=str(app.id), details={"name": body.name})
    return app_response(app)

@router.get("", response_model=list[ApplicationResponse])
async def list_applications(db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    if is_mongo():
        from database_mongo import get_database
        from models_mongo import ApplicationCollection
        mongo_db = get_database()
        apps = await ApplicationCollection.find_by_user(mongo_db, str(user.user_id))
        return [app_response(a, is_mongo_doc=True) for a in apps]

    return [app_response(a) for a in db.query(Application).filter(Application.user_id == int(user.user_id)).all()]

@router.post("/{application_id}/keys", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_key(application_id: str, body: APIKeyCreate, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    app = await owned_app(application_id, user.user_id, db)
    prefix, secret, plaintext = generate_api_key()

    if is_mongo():
        from database_mongo import get_database
        from models_mongo import APIKeyCollection
        mongo_db = get_database()
        doc = {
            "application_id": str(application_id),
            "name": body.name,
            "key_prefix": prefix,
            "secret_hash": hash_api_key(secret),
            "scopes_json": json.dumps(body.scopes),
            "expires_at": body.expires_at,
            "revoked_at": None,
            "last_used_at": None
        }
        key = await APIKeyCollection.create(mongo_db, doc)
        log_audit_event(db, actor=user.user_id, event_type="api_key.created", resource_type="api_key", resource_id=str(key["_id"]), application_id=str(application_id), details={"name": body.name, "prefix": prefix})
        return APIKeyCreateResponse(**key_response(key, is_mongo_doc=True).model_dump(), api_key=plaintext)

    key = APIKey(
        application_id=int(application_id),
        name=body.name,
        key_prefix=prefix,
        secret_hash=hash_api_key(secret),
        scopes_json=json.dumps(body.scopes),
        expires_at=body.expires_at
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    log_audit_event(db, actor=user.user_id, event_type="api_key.created", resource_type="api_key", resource_id=str(key.id), application_id=str(application_id), details={"name": body.name, "prefix": prefix})
    return APIKeyCreateResponse(**key_response(key).model_dump(), api_key=plaintext)

@router.get("/{application_id}/keys", response_model=list[APIKeyResponse])
async def list_keys(application_id: str, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    await owned_app(application_id, user.user_id, db)
    if is_mongo():
        from database_mongo import get_database
        from models_mongo import APIKeyCollection
        mongo_db = get_database()
        keys = await APIKeyCollection.find_by_application(mongo_db, str(application_id))
        return [key_response(k, is_mongo_doc=True) for k in keys]

    return [key_response(k) for k in db.query(APIKey).filter(APIKey.application_id == int(application_id)).all()]

@router.post("/{application_id}/keys/{key_id}/revoke", response_model=APIKeyResponse)
async def revoke_key(application_id: str, key_id: str, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    await owned_app(application_id, user.user_id, db)
    if is_mongo():
        from database_mongo import get_database
        from models_mongo import APIKeyCollection
        mongo_db = get_database()
        key = await APIKeyCollection.find_by_id(mongo_db, key_id)
        if not key or str(key.get("application_id")) != str(application_id):
            raise HTTPException(404, "API key not found")
        if not key.get("revoked_at"):
            key = await APIKeyCollection.revoke(mongo_db, key_id, application_id)
        log_audit_event(db, actor=user.user_id, event_type="api_key.revoked", resource_type="api_key", resource_id=str(key_id), application_id=str(application_id))
        return key_response(key, is_mongo_doc=True)

    key = db.query(APIKey).filter(APIKey.id == int(key_id), APIKey.application_id == int(application_id)).first()
    if not key:
        raise HTTPException(404, "API key not found")
    if not key.revoked_at:
        key.revoked_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(key)
    log_audit_event(db, actor=user.user_id, event_type="api_key.revoked", resource_type="api_key", resource_id=str(key_id), application_id=str(application_id))
    return key_response(key)

@router.post("/agents/{agent_id}/shares", status_code=status.HTTP_201_CREATED)
async def share_agent(agent_id: str, body: AgentShareCreate, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    if is_mongo():
        from database_mongo import get_database
        from models_mongo import AgentCollection, ApplicationCollection, ApplicationAgentAccessCollection
        mongo_db = get_database()
        agent = await AgentCollection.find_by_id(mongo_db, agent_id)
        if not agent or str(agent.get("user_id")) != str(user.user_id):
            raise HTTPException(404, "Agent not found")
        target = await ApplicationCollection.find_by_id(mongo_db, str(body.application_id))
        if not target:
            raise HTTPException(404, "Application not found")
        await ApplicationAgentAccessCollection.upsert(
            mongo_db,
            application_id=str(target["_id"]),
            agent_id=str(agent_id),
            permissions_json=json.dumps(body.permissions),
            granted_by=str(user.user_id)
        )
        log_audit_event(db, actor=user.user_id, event_type="agent.shared", resource_type="agent", resource_id=str(agent_id), application_id=str(target["_id"]), details={"permissions": body.permissions})
        return {"application_id": str(target["_id"]), "agent_id": str(agent_id), "permissions": body.permissions}

    agent = db.query(Agent).filter(Agent.id == int(agent_id), Agent.user_id == int(user.user_id)).first()
    if not agent:
        raise HTTPException(404, "Agent not found")
    target = db.query(Application).filter(Application.id == int(body.application_id)).first()
    if not target:
        raise HTTPException(404, "Application not found")
    access = db.query(ApplicationAgentAccess).filter(
        ApplicationAgentAccess.application_id == target.id,
        ApplicationAgentAccess.agent_id == int(agent_id)
    ).first()
    if access:
        access.permissions_json = json.dumps(body.permissions)
        access.revoked_at = None
    else:
        db.add(ApplicationAgentAccess(
            application_id=target.id,
            agent_id=int(agent_id),
            permissions_json=json.dumps(body.permissions),
            granted_by=int(user.user_id)
        ))
    db.commit()
    log_audit_event(db, actor=user.user_id, event_type="agent.shared", resource_type="agent", resource_id=str(agent_id), application_id=str(target.id), details={"permissions": body.permissions})
    return {"application_id": str(target.id), "agent_id": str(agent_id), "permissions": body.permissions}
