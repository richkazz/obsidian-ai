import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models import Schema, SchemaVersion
from auth import get_current_user, TokenData
from schemas import SchemaCreate, SchemaResponse, SchemaVersionResponse, SchemaValidationRequest, SchemaValidationResponse
from services.schema_validation_service import validate_json_schema
router = APIRouter(prefix="/api/v1/schemas", tags=["schemas"])

def version_response(v):
    return SchemaVersionResponse(id=str(v.id), schema_id=str(v.schema_id), version_number=v.version_number, canonical_schema=json.loads(v.canonical_schema_json), source_format=v.source_format, source_definition=v.source_definition, compatibility_mode=v.compatibility_mode, created_at=v.created_at)
def schema_response(db, s):
    v = db.query(SchemaVersion).filter(SchemaVersion.schema_id == s.id).order_by(SchemaVersion.version_number.desc()).first()
    return SchemaResponse(id=str(s.id), name=s.name, direction=s.direction, created_at=s.created_at, latest_version=version_response(v) if v else None)
def owned_schema(db, schema_id, user_id):
    s = db.query(Schema).filter(Schema.id == schema_id, Schema.user_id == int(user_id)).first()
    if not s: raise HTTPException(404, "Schema not found")
    return s

@router.post("", response_model=SchemaResponse, status_code=status.HTTP_201_CREATED)
def create_schema(body: SchemaCreate, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    if body.direction not in {"input", "output"}: raise HTTPException(422, "direction must be input or output")
    problems = validate_json_schema({"type": "object"}, body.canonical_schema)
    if problems: raise HTTPException(422, detail={"code": "INVALID_JSON_SCHEMA", "details": problems})
    s = Schema(user_id=int(user.user_id), name=body.name, direction=body.direction); db.add(s); db.flush()
    v = SchemaVersion(schema_id=s.id, version_number=1, canonical_schema_json=json.dumps(body.canonical_schema), source_format=body.source_format, source_definition=body.source_definition, compatibility_mode=body.compatibility_mode); db.add(v); db.commit(); db.refresh(s); return schema_response(db, s)

@router.post("/{schema_id}/versions", response_model=SchemaVersionResponse, status_code=status.HTTP_201_CREATED)
def create_version(schema_id: int, body: SchemaCreate, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    s = owned_schema(db, schema_id, user.user_id)
    if body.direction != s.direction: raise HTTPException(422, "Schema direction cannot change")
    version = (db.query(func.max(SchemaVersion.version_number)).filter(SchemaVersion.schema_id == s.id).scalar() or 0) + 1
    v = SchemaVersion(schema_id=s.id, version_number=version, canonical_schema_json=json.dumps(body.canonical_schema), source_format=body.source_format, source_definition=body.source_definition, compatibility_mode=body.compatibility_mode); db.add(v); db.commit(); db.refresh(v); return version_response(v)

@router.get("", response_model=list[SchemaResponse])
def list_schemas(db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    return [schema_response(db, s) for s in db.query(Schema).filter(Schema.user_id == int(user.user_id)).all()]

@router.post("/{schema_id}/versions/{version_id}/validate", response_model=SchemaValidationResponse)
def validate_schema(schema_id: int, version_id: int, body: SchemaValidationRequest, db: Session = Depends(get_db), user: TokenData = Depends(get_current_user)):
    s = owned_schema(db, schema_id, user.user_id); v = db.query(SchemaVersion).filter(SchemaVersion.id == version_id, SchemaVersion.schema_id == s.id).first()
    if not v: raise HTTPException(404, "Schema version not found")
    errors = validate_json_schema(json.loads(v.canonical_schema_json), body.payload); return SchemaValidationResponse(valid=not errors, errors=errors)
