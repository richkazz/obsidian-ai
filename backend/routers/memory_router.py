import json
from typing import Any, Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from config import DATABASE_TYPE
from database import get_db
from models import AgentMemory, Agent
from schemas import AgentMemoryResponse, AgentMemoryListResponse
from auth import get_current_user, TokenData

if DATABASE_TYPE == "mongo":
    from database_mongo import get_database
    from models_mongo import AgentMemoryCollection, AgentCollection

router = APIRouter(prefix="/memory", tags=["memory"])

MAX_MEMORIES = 50


def _memory_to_response(mem, is_mongo=False) -> AgentMemoryResponse:
    if is_mongo:
        return AgentMemoryResponse(
            id=str(mem["_id"]),
            agent_id=str(mem["agent_id"]),
            user_id=str(mem["user_id"]),
            key=mem["key"],
            value=mem["value"],
            category=mem.get("category", "context"),
            confidence=mem.get("confidence", 1.0),
            session_id=str(mem["session_id"]) if mem.get("session_id") else None,
            created_at=mem["created_at"],
            updated_at=mem.get("updated_at"),
        )
    return AgentMemoryResponse(
        id=str(mem.id),
        agent_id=str(mem.agent_id),
        user_id=str(mem.user_id),
        key=mem.key,
        value=mem.value,
        category=mem.category,
        confidence=mem.confidence,
        session_id=str(mem.session_id) if mem.session_id else None,
        created_at=mem.created_at,
        updated_at=mem.updated_at,
    )


@router.get("/agents/{agent_id}", response_model=AgentMemoryListResponse)
async def list_agent_memories(
    agent_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        # Verify agent ownership
        agent = await AgentCollection.find_by_id(mongo_db, agent_id)
        if not agent or agent.get("user_id") != current_user.user_id:
            raise HTTPException(status_code=404, detail="Agent not found")
        memories = await AgentMemoryCollection.find_by_agent_user(
            mongo_db, agent_id, current_user.user_id
        )
        return AgentMemoryListResponse(memories=[_memory_to_response(m, is_mongo=True) for m in memories])

    agent = db.query(Agent).filter(
        Agent.id == int(agent_id),
        Agent.user_id == int(current_user.user_id),
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    memories = db.query(AgentMemory).filter(
        AgentMemory.agent_id == int(agent_id),
        AgentMemory.user_id == int(current_user.user_id),
    ).order_by(AgentMemory.created_at.desc()).limit(MAX_MEMORIES).all()

    return AgentMemoryListResponse(memories=[_memory_to_response(m) for m in memories])


@router.delete("/agents/{agent_id}/{memory_id}")
async def delete_agent_memory(
    agent_id: str,
    memory_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        deleted = await AgentMemoryCollection.delete_by_id(mongo_db, memory_id, current_user.user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Memory not found")
        return {"message": "Memory deleted"}

    memory = db.query(AgentMemory).filter(
        AgentMemory.id == int(memory_id),
        AgentMemory.agent_id == int(agent_id),
        AgentMemory.user_id == int(current_user.user_id),
    ).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    db.delete(memory)
    db.commit()
    return {"message": "Memory deleted"}


@router.delete("/agents/{agent_id}")
async def clear_agent_memories(
    agent_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        count = await AgentMemoryCollection.delete_all_by_agent_user(
            mongo_db, agent_id, current_user.user_id
        )
        return {"message": f"Cleared {count} memories"}

    deleted = db.query(AgentMemory).filter(
        AgentMemory.agent_id == int(agent_id),
        AgentMemory.user_id == int(current_user.user_id),
    ).delete()
    db.commit()
    return {"message": f"Cleared {deleted} memories"}


# ── MAF MemoryContextProvider Integration ──────────────────────────────────────

try:
    from agent_framework import ContextProvider, SessionContext, AgentSession
except ImportError:
    ContextProvider = object
    SessionContext = None
    AgentSession = None


class MemoryContextProvider(ContextProvider if ContextProvider != object else object):
    """
    MAF ContextProvider bridging long-term agent memories into MAF conversation context.
    Retrieves active user memories (up to 50, sorted by confidence) and injects them
    into the agent context prior to model invocation.
    """

    def __init__(
        self,
        agent_id: str | int,
        user_id: str | int,
        db=None,
        db_type: str = DATABASE_TYPE,
        top_k: int = MAX_MEMORIES,
        source_id: str = "long_term_memory",
    ):
        if ContextProvider != object:
            super().__init__(source_id=source_id)
        else:
            self.source_id = source_id
        self.agent_id = str(agent_id)
        self.user_id = str(user_id)
        self.db = db
        self.db_type = db_type
        self.top_k = min(top_k, MAX_MEMORIES)

    async def before_run(
        self,
        *,
        agent: Any,
        session: Any,
        context: Any,
        state: dict,
    ) -> None:
        """Fetch active user memories and inject them into context instructions."""
        if not context:
            return

        memories_list = []

        if self.db_type == "mongo":
            from database_mongo import get_database
            from models_mongo import AgentMemoryCollection
            mongo_db = get_database() if self.db is None else self.db
            raw_mems = await AgentMemoryCollection.find_by_agent_user(
                mongo_db, self.agent_id, self.user_id
            )
            # Sort by confidence desc
            raw_mems = sorted(raw_mems, key=lambda x: x.get("confidence", 1.0), reverse=True)[: self.top_k]
            for m in raw_mems:
                memories_list.append({
                    "key": m.get("key"),
                    "value": m.get("value"),
                    "category": m.get("category", "context"),
                    "confidence": m.get("confidence", 1.0),
                })
        else:
            if self.db:
                raw_mems = self.db.query(AgentMemory).filter(
                    AgentMemory.agent_id == int(self.agent_id),
                    AgentMemory.user_id == int(self.user_id),
                ).order_by(AgentMemory.confidence.desc(), AgentMemory.created_at.desc()).limit(self.top_k).all()
                for m in raw_mems:
                    memories_list.append({
                        "key": m.key,
                        "value": m.value,
                        "category": m.category,
                        "confidence": m.confidence,
                    })

        if not memories_list:
            return

        formatted_memories = ["Long-Term Memories:"]
        for m in memories_list:
            formatted_memories.append(
                f"- [{m['category']}] {m['key']}: {m['value']} (confidence: {m['confidence']})"
            )

        instruction = "\n".join(formatted_memories)
        context.extend_instructions(self.source_id, instruction)
