import json
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from config import DATABASE_TYPE

if DATABASE_TYPE == "mongo":
    from database_mongo import get_database
    from models_mongo import AuditEventCollection
else:
    from models import AuditEvent

SECRET_KEYS = {"secret", "password", "api_key", "token", "secret_hash", "encrypted_value", "key_secret"}


def _redact_dict(data: Any) -> Any:
    """Recursively redacts secret fields from a dictionary/list."""
    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            if any(s in k.lower() for s in SECRET_KEYS):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = _redact_dict(v)
        return redacted
    elif isinstance(data, list):
        return [_redact_dict(item) for item in data]
    return data


async def record_audit_event(
    event_type: str,
    actor_user_id: Optional[str] = None,
    application_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
):
    """
    Writes an append-only audit event record with all sensitive secret fields redacted.
    """
    redacted_details = _redact_dict(details) if details else {}
    details_str = json.dumps(redacted_details)

    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        if mongo_db is not None:
            await AuditEventCollection.create(mongo_db, {
                "actor_user_id": str(actor_user_id) if actor_user_id else None,
                "application_id": str(application_id) if application_id else None,
                "resource_id": str(resource_id) if resource_id else None,
                "event_type": event_type,
                "details_json": details_str,
            })
    else:
        if db is not None:
            evt = AuditEvent(
                actor_user_id=int(actor_user_id) if actor_user_id and str(actor_user_id).isdigit() else None,
                application_id=int(application_id) if application_id and str(application_id).isdigit() else None,
                resource_id=str(resource_id) if resource_id else None,
                event_type=event_type,
                details_json=details_str,
            )
            db.add(evt)
            db.commit()
