import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from models import Application, APIKey, Agent, ApplicationAgentAccess
from database import get_db
from auth import get_current_user, TokenData
from schemas import ApplicationCreate, ApplicationResponse, APIKeyCreate, APIKeyResponse, APIKeyCreateResponse, AgentShareCreate
from services.api_key_service import generate_api_key, hash_api_key

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])

def app_response(app):
    return ApplicationResponse(id=str(app.id), name=app.name, description=app.description, status=app.status,
        default_scopes=json.loads(app.default_scopes_json or "[]"), metadata=json.loads(app.metadata_json or "null"), created_at=app.created_at)
def key_response(key):
    return APIKeyResponse(id=str(key.id), name=key.name, key_prefix=key.key_prefix, scopes=json.loads(key.scopes_json), expires_at=key.expires_at, revoked_at=key.revoked_at, last_used_at=key.last_used_at, created_at=key.created_at)
def owned(db, app_id, user_id):
    app = db.query(Application).filter(Application.id == app_id, Application.user_id == int(user_id)).first()
    if not app: raise HTTPException(404, "Application not found")
    return app

@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
def create_application(body: ApplicationCreate, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    app = Application(user_id=int(user.user_id), name=body.name, description=body.description, default_scopes_json=json.dumps(body.default_scopes), metadata_json=json.dumps(body.metadata) if body.metadata is not None else None)
    db.add(app); db.commit(); db.refresh(app); return app_response(app)

@router.get("", response_model=list[ApplicationResponse])
def list_applications(db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    return [app_response(a) for a in db.query(Application).filter(Application.user_id == int(user.user_id)).all()]

@router.post("/{application_id}/keys", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
def create_key(application_id: int, body: APIKeyCreate, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    owned(db, application_id, user.user_id)
    prefix, secret, plaintext = generate_api_key()
    key = APIKey(application_id=application_id, name=body.name, key_prefix=prefix, secret_hash=hash_api_key(secret), scopes_json=json.dumps(body.scopes), expires_at=body.expires_at)
    db.add(key); db.commit(); db.refresh(key)
    return APIKeyCreateResponse(**key_response(key).model_dump(), api_key=plaintext)

@router.get("/{application_id}/keys", response_model=list[APIKeyResponse])
def list_keys(application_id: int, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    owned(db, application_id, user.user_id)
    return [key_response(k) for k in db.query(APIKey).filter(APIKey.application_id == application_id).all()]

@router.post("/{application_id}/keys/{key_id}/revoke", response_model=APIKeyResponse)
def revoke_key(application_id: int, key_id: int, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    owned(db, application_id, user.user_id)
    key = db.query(APIKey).filter(APIKey.id == key_id, APIKey.application_id == application_id).first()
    if not key: raise HTTPException(404, "API key not found")
    if not key.revoked_at: key.revoked_at = datetime.now(timezone.utc); db.commit(); db.refresh(key)
    return key_response(key)

@router.post("/agents/{agent_id}/shares", status_code=status.HTTP_201_CREATED)
def share_agent(agent_id: int, body: AgentShareCreate, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.user_id == int(user.user_id)).first()
    if not agent: raise HTTPException(404, "Agent not found")
    target = db.query(Application).filter(Application.id == int(body.application_id)).first()
    if not target: raise HTTPException(404, "Application not found")
    access = db.query(ApplicationAgentAccess).filter(ApplicationAgentAccess.application_id == target.id, ApplicationAgentAccess.agent_id == agent_id).first()
    if access: access.permissions_json = json.dumps(body.permissions); access.revoked_at = None
    else: db.add(ApplicationAgentAccess(application_id=target.id, agent_id=agent_id, permissions_json=json.dumps(body.permissions), granted_by=int(user.user_id)))
    db.commit(); return {"application_id": str(target.id), "agent_id": str(agent_id), "permissions": body.permissions}
