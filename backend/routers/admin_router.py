import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from config import DATABASE_TYPE
from database import get_db
from models import User
from schemas import (
    AdminUserResponse, AdminUserListResponse, AdminUserCreate,
    AdminUserUpdate, UserPermissions,
)
from auth import (
    get_admin_user, TokenData, DEFAULT_PERMISSIONS, get_user_permissions,
)
from rate_limiter import limiter

if DATABASE_TYPE == "mongo":
    from database_mongo import get_database
    from models_mongo import UserCollection

router = APIRouter(prefix="/admin", tags=["admin"])

_cached_admin_id: str | None = None


async def _get_admin_user_id(mongo_db) -> str | None:
    """Return the user_id of the first admin account (cached after first call)."""
    global _cached_admin_id
    if _cached_admin_id:
        return _cached_admin_id
    admin = await mongo_db["users"].find_one({"role": "admin"})
    if admin:
        _cached_admin_id = str(admin["_id"])
    return _cached_admin_id

def _user_to_admin_response(user, is_mongo=False) -> AdminUserResponse:
    perms = get_user_permissions(user, is_mongo=is_mongo)
    if is_mongo:
        return AdminUserResponse(
            id=str(user["_id"]),
            username=user["username"],
            email=user["email"],
            role=user["role"],
            permissions=UserPermissions(**perms),
            created_at=user.get("created_at"),
        )
    return AdminUserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role,
        permissions=UserPermissions(**perms),
        created_at=user.created_at,
    )


# ---------- List all users ----------
@router.get("/users", response_model=AdminUserListResponse)
@limiter.limit("30/minute")
async def list_users(
    request: Request,
    admin: TokenData = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        users = await UserCollection.find_all(mongo_db)
        return AdminUserListResponse(
            users=[_user_to_admin_response(u, is_mongo=True) for u in users]
        )

    users = db.query(User).all()
    return AdminUserListResponse(
        users=[_user_to_admin_response(u) for u in users]
    )


# ---------- Create a user (admin-initiated) ----------
@router.post("/users", response_model=AdminUserResponse, status_code=201)
@limiter.limit("20/minute")
async def create_user(
    request: Request,
    data: AdminUserCreate,
    admin: TokenData = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    import bcrypt

    if len(data.password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password too long (max 72 bytes for bcrypt)",
        )

    hashed_password = bcrypt.hashpw(
        data.password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    permissions = data.permissions.model_dump() if data.permissions else DEFAULT_PERMISSIONS.copy()

    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        if await UserCollection.find_by_username(mongo_db, data.username):
            raise HTTPException(status_code=400, detail="Username already exists")
        if await UserCollection.find_by_email(mongo_db, data.email):
            raise HTTPException(status_code=400, detail="Email already exists")

        user_doc = {
            "username": data.username,
            "email": data.email,
            "role": data.role,
            "hashed_password": hashed_password,
            "permissions": permissions,
            "created_at": datetime.now(timezone.utc),
        }
        created = await UserCollection.create(mongo_db, user_doc)
        return _user_to_admin_response(created, is_mongo=True)

    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")

    db_user = User(
        username=data.username,
        email=data.email,
        role=data.role,
        hashed_password=hashed_password,
        permissions_json=json.dumps(permissions),
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return _user_to_admin_response(db_user)


# ---------- Update user role/permissions ----------
@router.put("/users/{user_id}", response_model=AdminUserResponse)
@limiter.limit("30/minute")
async def update_user(
    request: Request,
    user_id: str,
    data: AdminUserUpdate,
    admin: TokenData = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        user = await UserCollection.find_by_id(mongo_db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        updates = {}
        if data.role is not None:
            updates["role"] = data.role
        if data.permissions is not None:
            updates["permissions"] = data.permissions.model_dump()

        if updates:
            user = await UserCollection.update_user(mongo_db, user_id, updates)
        return _user_to_admin_response(user, is_mongo=True)

    db_user = db.query(User).filter(User.id == int(user_id)).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    if data.role is not None:
        db_user.role = data.role
    if data.permissions is not None:
        db_user.permissions_json = json.dumps(data.permissions.model_dump())

    db.commit()
    db.refresh(db_user)
    return _user_to_admin_response(db_user)


# ---------- Delete user ----------
@router.delete("/users/{user_id}")
@limiter.limit("10/minute")
async def delete_user(
    request: Request,
    user_id: str,
    admin: TokenData = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        await _cascade_delete_user_data_mongo(mongo_db, user_id)
        success = await UserCollection.delete_user(mongo_db, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        return {"message": "User deleted"}

    db_user = db.query(User).filter(User.id == int(user_id)).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    _cascade_delete_user_data_sqlite(db, int(user_id))
    db.delete(db_user)
    db.commit()
    return {"message": "User deleted"}


async def _cascade_delete_user_data_mongo(mongo_db, user_id: str):
    """Mongo counterpart of _cascade_delete_user_data_sqlite — removes every
    document owned by this user before the user document itself is deleted."""
    agent_docs = await mongo_db["agents"].find({"user_id": user_id}, {"_id": 1}).to_list(length=10000)
    agent_ids = [str(a["_id"]) for a in agent_docs]
    session_docs = await mongo_db["sessions"].find({"user_id": user_id}, {"_id": 1}).to_list(length=10000)
    session_ids = [str(s["_id"]) for s in session_docs]
    kb_docs = await mongo_db["knowledge_bases"].find({"user_id": user_id}, {"_id": 1}).to_list(length=10000)
    kb_ids = [str(k["_id"]) for k in kb_docs]
    wa_channel_docs = await mongo_db["whatsapp_channels"].find({"user_id": user_id}, {"_id": 1}).to_list(length=10000)
    wa_channel_ids = [str(c["_id"]) for c in wa_channel_docs]

    if agent_ids:
        await mongo_db["messages"].delete_many({"agent_id": {"$in": agent_ids}})
        await mongo_db["agent_memories"].delete_many({"agent_id": {"$in": agent_ids}})
        await mongo_db["agent_versions"].delete_many({"agent_id": {"$in": agent_ids}})
        await mongo_db["async_jobs"].delete_many({"agent_id": {"$in": agent_ids}})
        await mongo_db["optimization_runs"].delete_many({"agent_id": {"$in": agent_ids}})
        await mongo_db["eval_suites"].update_many({"agent_id": {"$in": agent_ids}}, {"$set": {"agent_id": None}})
        await mongo_db["eval_suites"].update_many({"judge_agent_id": {"$in": agent_ids}}, {"$set": {"judge_agent_id": None}})
        await mongo_db["eval_runs"].update_many({"agent_id": {"$in": agent_ids}}, {"$set": {"agent_id": None}})
        await mongo_db["whatsapp_channels"].delete_many({"agent_id": {"$in": agent_ids}})

    if session_ids:
        await mongo_db["messages"].delete_many({"session_id": {"$in": session_ids}})
        await mongo_db["file_attachments"].delete_many({"session_id": {"$in": session_ids}})

    if kb_ids:
        await mongo_db["kb_documents"].delete_many({"kb_id": {"$in": kb_ids}})

    if wa_channel_ids:
        await mongo_db["wa_contact_sessions"].delete_many({"channel_id": {"$in": wa_channel_ids}})

    await mongo_db["sessions"].delete_many({"user_id": user_id})
    await mongo_db["eval_suites"].delete_many({"user_id": user_id})
    await mongo_db["optimization_runs"].delete_many({"user_id": user_id})
    await mongo_db["workflow_schedules"].delete_many({"user_id": user_id})
    await mongo_db["whatsapp_channels"].delete_many({"user_id": user_id})
    await mongo_db["teams"].delete_many({"user_id": user_id})
    await mongo_db["agents"].delete_many({"user_id": user_id})
    await mongo_db["mcp_servers"].delete_many({"user_id": user_id})
    await mongo_db["tool_definitions"].delete_many({"user_id": user_id})
    await mongo_db["skills"].delete_many({"user_id": user_id})
    await mongo_db["knowledge_bases"].delete_many({"user_id": user_id})
    await mongo_db["user_secrets"].delete_many({"user_id": user_id})
    await mongo_db["prompt_vault"].delete_many({"user_id": user_id})
    await mongo_db["llm_providers"].delete_many({"user_id": user_id})
    await mongo_db["api_clients"].delete_many({"created_by": user_id})


def _cascade_delete_user_data_sqlite(db: Session, uid: int):
    """Remove every row owned by this user before the user row itself is deleted,
    so nothing is left pointing at a dead user_id. Order matters: leaf tables
    (messages, memories, versions, ...) before the entities they reference."""
    from models import (
        Agent, LLMProvider, Team, MCPServer, ToolDefinition, Skill,
        KnowledgeBase, KnowledgeBaseDocument, UserSecret, PromptVault,
        Session as SessionModel, Message, FileAttachment, AgentMemory,
        AgentVersion, AsyncJob, EvalSuite, EvalRun, OptimizationRun,
        WhatsAppChannel, WAContactSession, WorkflowSchedule, APIClient,
    )

    agent_ids = [a.id for a in db.query(Agent.id).filter(Agent.user_id == uid).all()]
    session_ids = [s.id for s in db.query(SessionModel.id).filter(SessionModel.user_id == uid).all()]
    kb_ids = [k.id for k in db.query(KnowledgeBase.id).filter(KnowledgeBase.user_id == uid).all()]

    if agent_ids:
        db.query(Message).filter(Message.agent_id.in_(agent_ids)).delete(synchronize_session=False)
        db.query(AgentMemory).filter(AgentMemory.agent_id.in_(agent_ids)).delete(synchronize_session=False)
        db.query(AgentVersion).filter(AgentVersion.agent_id.in_(agent_ids)).delete(synchronize_session=False)
        db.query(AsyncJob).filter(AsyncJob.agent_id.in_(agent_ids)).delete(synchronize_session=False)
        db.query(OptimizationRun).filter(OptimizationRun.agent_id.in_(agent_ids)).delete(synchronize_session=False)
        db.query(EvalSuite).filter(EvalSuite.agent_id.in_(agent_ids)).update({"agent_id": None}, synchronize_session=False)
        db.query(EvalSuite).filter(EvalSuite.judge_agent_id.in_(agent_ids)).update({"judge_agent_id": None}, synchronize_session=False)
        db.query(EvalRun).filter(EvalRun.agent_id.in_(agent_ids)).update({"agent_id": None}, synchronize_session=False)
        db.query(WhatsAppChannel).filter(WhatsAppChannel.agent_id.in_(agent_ids)).delete(synchronize_session=False)

    if session_ids:
        db.query(Message).filter(Message.session_id.in_(session_ids)).delete(synchronize_session=False)
        db.query(FileAttachment).filter(FileAttachment.session_id.in_(session_ids)).delete(synchronize_session=False)

    if kb_ids:
        db.query(KnowledgeBaseDocument).filter(KnowledgeBaseDocument.kb_id.in_(kb_ids)).delete(synchronize_session=False)

    db.query(SessionModel).filter(SessionModel.user_id == uid).delete(synchronize_session=False)
    db.query(EvalSuite).filter(EvalSuite.user_id == uid).delete(synchronize_session=False)
    db.query(OptimizationRun).filter(OptimizationRun.user_id == uid).delete(synchronize_session=False)
    db.query(WorkflowSchedule).filter(WorkflowSchedule.user_id == uid).delete(synchronize_session=False)
    db.query(WAContactSession).filter(
        WAContactSession.channel_id.in_(
            db.query(WhatsAppChannel.id).filter(WhatsAppChannel.user_id == uid)
        )
    ).delete(synchronize_session=False)
    db.query(WhatsAppChannel).filter(WhatsAppChannel.user_id == uid).delete(synchronize_session=False)
    db.query(Team).filter(Team.user_id == uid).delete(synchronize_session=False)
    db.query(Agent).filter(Agent.user_id == uid).delete(synchronize_session=False)
    db.query(MCPServer).filter(MCPServer.user_id == uid).delete(synchronize_session=False)
    db.query(ToolDefinition).filter(ToolDefinition.user_id == uid).delete(synchronize_session=False)
    db.query(Skill).filter(Skill.user_id == uid).delete(synchronize_session=False)
    db.query(KnowledgeBase).filter(KnowledgeBase.user_id == uid).delete(synchronize_session=False)
    db.query(UserSecret).filter(UserSecret.user_id == uid).delete(synchronize_session=False)
    db.query(PromptVault).filter(PromptVault.user_id == uid).delete(synchronize_session=False)
    db.query(LLMProvider).filter(LLMProvider.user_id == uid).delete(synchronize_session=False)
    db.query(APIClient).filter(APIClient.created_by == uid).delete(synchronize_session=False)
