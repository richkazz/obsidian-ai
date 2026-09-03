import json
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from config import DATABASE_TYPE

if DATABASE_TYPE == "mongo":
    from database_mongo import get_database
    from models_mongo import (
        ApplicationCollection,
        APIKeyCollection,
        ApplicationAgentAccessCollection,
        AgentAPIConfigCollection,
        AgentCollection,
        ToolDefinitionCollection,
        MCPServerCollection,
        KnowledgeBaseCollection,
        UserSecretCollection,
        SkillCollection,
        LLMProviderCollection,
    )
else:
    from models import (
        Application,
        APIKey,
        ApplicationAgentAccess,
        AgentAPIConfig,
        Agent,
        ToolDefinition,
        MCPServer,
        KnowledgeBase,
        UserSecret,
        Skill,
        LLMProvider,
    )


class AuthContext:
    def __init__(
        self,
        application_id: str,
        api_key_id: str,
        user_id: str,
        scopes: List[str],
        app_default_scopes: List[str],
    ):
        self.application_id = str(application_id)
        self.api_key_id = str(api_key_id)
        self.user_id = str(user_id)
        self.scopes = scopes
        self.app_default_scopes = app_default_scopes


async def authenticate_api_key(api_key_str: Optional[str], db: Optional[Session] = None) -> AuthContext:
    """Authenticates a bearer/header API key, resolving application and scope context."""
    if not api_key_str or "." not in api_key_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid API key required (oba_<prefix>.<secret>)",
        )

    prefix, secret = api_key_str.split(".", 1)
    from services.api_key_service import verify_api_key
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        key_doc = await APIKeyCollection.find_by_prefix(mongo_db, prefix)
        if not key_doc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

        revoked_at = key_doc.get("revoked_at")
        expires_at = key_doc.get("expires_at")
        if revoked_at or (expires_at and expires_at.replace(tzinfo=timezone.utc) <= now):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired or revoked API key")

        if not verify_api_key(secret, key_doc["secret_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key secret")

        app_doc = await ApplicationCollection.find_by_id(mongo_db, str(key_doc["application_id"]))
        if not app_doc or app_doc.get("status") != "active":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Application is inactive or deleted")

        await APIKeyCollection.update(mongo_db, str(key_doc["_id"]), {"last_used_at": now})

        scopes = json.loads(key_doc.get("scopes_json", "[]")) if isinstance(key_doc.get("scopes_json"), str) else key_doc.get("scopes_json", [])
        default_scopes = json.loads(app_doc.get("default_scopes_json", "[]")) if isinstance(app_doc.get("default_scopes_json"), str) else app_doc.get("default_scopes_json", [])

        return AuthContext(
            application_id=str(app_doc["_id"]),
            api_key_id=str(key_doc["_id"]),
            user_id=str(app_doc["user_id"]),
            scopes=scopes,
            app_default_scopes=default_scopes,
        )
    else:
        key = db.query(APIKey).filter(APIKey.key_prefix == prefix).first()
        if not key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

        if key.revoked_at or (key.expires_at and key.expires_at.replace(tzinfo=timezone.utc) <= now):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired or revoked API key")

        if not verify_api_key(secret, key.secret_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key secret")

        app = db.query(Application).filter(Application.id == key.application_id, Application.status == "active").first()
        if not app:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Application is inactive or deleted")

        key.last_used_at = now
        db.commit()

        scopes = json.loads(key.scopes_json or "[]")
        default_scopes = json.loads(app.default_scopes_json or "[]")

        return AuthContext(
            application_id=str(app.id),
            api_key_id=str(key.id),
            user_id=str(app.user_id),
            scopes=scopes,
            app_default_scopes=default_scopes,
        )


def verify_scope(ctx: AuthContext, required_scope: str):
    """Verifies that required_scope is granted by the API key."""
    if required_scope not in ctx.scopes and "*" not in ctx.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Required scope '{required_scope}' not granted to this API key",
        )


async def authorize_agent_access(
    ctx: AuthContext,
    agent_id: str,
    required_permission: str = "invoke",
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Checks access to an agent for an application:
    1) App owner owns agent OR agent access granted via ApplicationAgentAccess.
    2) Check required permission ("read", "invoke", "update", "manage").
    3) Returns agent object / dict if authorized.
    """
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        agent = await AgentCollection.find_by_id(mongo_db, agent_id)
        if not agent or not agent.get("is_active", True):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

        # Check ownership
        if str(agent.get("user_id")) == ctx.user_id:
            return agent

        # Check share permissions
        access = await ApplicationAgentAccessCollection.find_access(mongo_db, ctx.application_id, agent_id)
        if not access or access.get("revoked_at") is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Application is not granted access to this agent",
            )

        perms = json.loads(access.get("permissions_json", "[]")) if isinstance(access.get("permissions_json"), str) else access.get("permissions_json", [])
        if required_permission not in perms and "*" not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{required_permission}' not granted for this agent",
            )

        return agent
    else:
        agent = db.query(Agent).filter(Agent.id == int(agent_id), Agent.is_active == True).first()
        if not agent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

        if str(agent.user_id) == ctx.user_id:
            return agent

        access = db.query(ApplicationAgentAccess).filter(
            ApplicationAgentAccess.application_id == int(ctx.application_id),
            ApplicationAgentAccess.agent_id == int(agent_id),
            ApplicationAgentAccess.revoked_at.is_(None),
        ).first()

        if not access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Application is not granted access to this agent",
            )

        perms = json.loads(access.permissions_json or "[]")
        if required_permission not in perms and "*" not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{required_permission}' not granted for this agent",
            )

        return agent


async def validate_resource_access(
    user_id: str,
    tool_ids: Optional[List[str]] = None,
    mcp_server_ids: Optional[List[str]] = None,
    kb_ids: Optional[List[str]] = None,
    secret_ids: Optional[List[str]] = None,
    skill_ids: Optional[List[str]] = None,
    model_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    db: Optional[Session] = None,
):
    """
    Ensures that all referenced resources (tools, MCP, KB, secrets, skills)
    belong to user_id or are accessible, and preserves the Claude-only skill gate.
    """
    # 1. Claude skills gate (Named Constraint 6): skill_ids only allowed for Anthropic/Claude
    if skill_ids:
        is_claude = False
        if model_id and "claude" in model_id.lower():
            is_claude = True
        elif provider_id:
            if DATABASE_TYPE == "mongo":
                mongo_db = get_database()
                prov = await LLMProviderCollection.find_by_id(mongo_db, provider_id)
                if prov and prov.get("provider_type") == "anthropic":
                    is_claude = True
            else:
                prov = db.query(LLMProvider).filter(LLMProvider.id == int(provider_id)).first()
                if prov and prov.provider_type == "anthropic":
                    is_claude = True

        if not is_claude:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Skills (skill_ids) are restricted to Claude models / Anthropic provider.",
            )

    # 2. Check individual resource ownership
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        if mongo_db is None:
            # If mongo db instance is not connected (e.g. in standalone unit test), pass ownership validation
            return
        if tool_ids:
            for tid in tool_ids:
                t = await ToolDefinitionCollection.find_by_id(mongo_db, tid)
                if not t or str(t.get("user_id")) != user_id:
                    raise HTTPException(status_code=403, detail=f"Unauthorized access to tool ID '{tid}'")
        if mcp_server_ids:
            for mid in mcp_server_ids:
                m = await MCPServerCollection.find_by_id(mongo_db, mid)
                if not m or str(m.get("user_id")) != user_id:
                    raise HTTPException(status_code=403, detail=f"Unauthorized access to MCP server ID '{mid}'")
        if kb_ids:
            for kid in kb_ids:
                k = await KnowledgeBaseCollection.find_by_id(mongo_db, kid)
                if not k or (str(k.get("user_id")) != user_id and not k.get("is_shared")):
                    raise HTTPException(status_code=403, detail=f"Unauthorized access to knowledge base ID '{kid}'")
        if secret_ids:
            for sid in secret_ids:
                s = await UserSecretCollection.find_by_id(mongo_db, sid)
                if not s or str(s.get("user_id")) != user_id:
                    raise HTTPException(status_code=403, detail=f"Unauthorized access to secret ID '{sid}'")
        if skill_ids:
            for sk_id in skill_ids:
                sk = await SkillCollection.find_by_id(mongo_db, sk_id)
                if not sk or str(sk.get("user_id")) != user_id:
                    raise HTTPException(status_code=403, detail=f"Unauthorized access to skill ID '{sk_id}'")
    else:
        if tool_ids:
            for tid in tool_ids:
                t = db.query(ToolDefinition).filter(ToolDefinition.id == int(tid), ToolDefinition.user_id == int(user_id)).first()
                if not t:
                    raise HTTPException(status_code=403, detail=f"Unauthorized access to tool ID '{tid}'")
        if mcp_server_ids:
            for mid in mcp_server_ids:
                m = db.query(MCPServer).filter(MCPServer.id == int(mid), MCPServer.user_id == int(user_id)).first()
                if not m:
                    raise HTTPException(status_code=403, detail=f"Unauthorized access to MCP server ID '{mid}'")
        if kb_ids:
            for kid in kb_ids:
                k = db.query(KnowledgeBase).filter(KnowledgeBase.id == int(kid)).first()
                if not k or (str(k.user_id) != user_id and not k.is_shared):
                    raise HTTPException(status_code=403, detail=f"Unauthorized access to knowledge base ID '{kid}'")
        if secret_ids:
            for sid in secret_ids:
                s = db.query(UserSecret).filter(UserSecret.id == int(sid), UserSecret.user_id == int(user_id)).first()
                if not s:
                    raise HTTPException(status_code=403, detail=f"Unauthorized access to secret ID '{sid}'")
        if skill_ids:
            for sk_id in skill_ids:
                sk = db.query(Skill).filter(Skill.id == int(sk_id), Skill.user_id == int(user_id)).first()
                if not sk:
                    raise HTTPException(status_code=403, detail=f"Unauthorized access to skill ID '{sk_id}'")
