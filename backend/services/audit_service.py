import os
import json
from datetime import datetime, timezone

def log_audit_event(
    db,
    actor: str,
    event_type: str,
    resource_type: str,
    resource_id: str,
    application_id: str | None = None,
    details: dict | None = None,
):
    """Write an append-only audit event record, ensuring sensitive fields are redacted."""
    db_type = os.getenv("DATABASE_TYPE", "sqlite")
    safe_details = {}
    if details:
        for k, v in details.items():
            if "secret" in k.lower() or "key" in k.lower() or "password" in k.lower():
                safe_details[k] = "[REDACTED]"
            else:
                safe_details[k] = v

    details_json = json.dumps(safe_details) if safe_details else None

    if db_type == "mongo":
        import asyncio
        from database_mongo import get_database
        from models_mongo import AuditEventCollection
        mongo_db = get_database()
        if mongo_db is not None:
            doc = {
                "actor": str(actor),
                "application_id": str(application_id) if application_id else None,
                "resource_type": str(resource_type),
                "resource_id": str(resource_id),
                "event_type": str(event_type),
                "details_json": details_json,
                "created_at": datetime.now(timezone.utc),
            }
            try:
                asyncio.create_task(AuditEventCollection.create(mongo_db, doc))
            except Exception:
                pass
    else:
        from models import AuditEvent
        try:
            app_id_int = int(application_id) if (application_id and str(application_id).isdigit()) else None
            event = AuditEvent(
                actor=str(actor),
                application_id=app_id_int,
                resource_type=str(resource_type),
                resource_id=str(resource_id),
                event_type=str(event_type),
                details_json=details_json,
            )
            db.add(event)
            db.commit()
        except Exception as e:
            print("AUDIT LOG ERROR:", e)
            db.rollback()
