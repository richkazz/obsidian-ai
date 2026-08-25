"""
Background poll executors for AsyncJob records, run by APScheduler on an interval.

Must live in a top-level, importable module because APScheduler serializes job
references by dotted module path (e.g. "async_job_poller.poll_async_job_sqlite"),
same constraint as scheduler_executor.py.

Each poll: opens a standalone MCP connection (independent of any chat request),
re-invokes the stored poll tool, asks the job's owning LLM provider a short
completion-classifier question, and on a genuine completion/failure verdict
writes a new assistant Message into the session and stops rescheduling.
"""
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_COMPLETION_CLASSIFIER_PROMPT = """You are checking whether a background job has finished.

Tool result from the status-check call:
{result}

Reply with EXACTLY one word:
- COMPLETE if the result clearly indicates the job finished successfully
- FAILED if the result clearly indicates the job failed or errored
- PENDING if the job is still in progress or the result is ambiguous

One word only, no punctuation."""


async def _classify_completion(llm, result_text: str) -> str:
    """Ask the LLM a tight yes/no-style question to decide whether to keep polling.
    Defaults to PENDING on any ambiguity or error so we never falsely report
    completion on a parse failure."""
    from llm.base import LLMMessage
    try:
        response = await llm.chat(
            [LLMMessage(role="user", content=_COMPLETION_CLASSIFIER_PROMPT.format(result=result_text[:4000]))],
        )
        verdict = (response.content or "").strip().upper()
        if "COMPLETE" in verdict:
            return "completed"
        if "FAILED" in verdict:
            return "failed"
        return "pending"
    except Exception as e:
        logger.warning(f"Async job completion classification failed: {e}")
        return "pending"


async def poll_async_job_sqlite(job_id: int):
    from database import SessionLocal
    from models import AsyncJob, MCPServer, Agent, LLMProvider
    from mcp_client import connect_mcp_server
    from encryption import decrypt_api_key
    from llm.provider_factory import create_provider_from_config

    db = SessionLocal()
    try:
        job = db.query(AsyncJob).filter(AsyncJob.id == job_id).first()
        if not job or job.status != "pending":
            _unschedule(job_id)
            return

        job.poll_count += 1
        if job.poll_count > job.max_polls:
            job.status = "expired"
            job.resolved_at = datetime.now(timezone.utc)
            db.commit()
            _post_job_message(db, job, "expired")
            _unschedule(job_id)
            return

        server = db.query(MCPServer).filter(MCPServer.id == job.mcp_server_id).first()
        if not server:
            job.status = "failed"
            job.error = "MCP server no longer exists"
            job.resolved_at = datetime.now(timezone.utc)
            db.commit()
            _post_job_message(db, job, "failed")
            _unschedule(job_id)
            return

        config = {
            "id": str(server.id), "name": server.name, "transport_type": server.transport_type,
            "command": server.command, "args_json": server.args_json, "env_json": server.env_json,
            "url": server.url, "headers_json": server.headers_json,
        }

        try:
            poll_args = json.loads(job.poll_arguments_json) if job.poll_arguments_json else {}
            async with connect_mcp_server(config) as conn:
                result_text = await conn.call_tool(job.poll_tool_name, poll_args)
        except Exception as e:
            db.commit()  # persist poll_count increment even though the call failed
            logger.warning(f"Async job {job_id} poll call failed (will retry): {e}")
            return

        job.last_result = result_text[:8000] if result_text else None
        db.commit()

        agent = db.query(Agent).filter(Agent.id == job.agent_id).first() if job.agent_id else None
        llm = None
        if agent and agent.provider_id:
            provider = db.query(LLMProvider).filter(LLMProvider.id == agent.provider_id).first()
            if provider:
                api_key = decrypt_api_key(provider.api_key) if provider.api_key else None
                pconfig = json.loads(provider.config_json) if provider.config_json else None
                llm = create_provider_from_config(
                    provider_type=provider.provider_type, api_key=api_key,
                    base_url=provider.base_url, model_id=agent.model_id or provider.model_id or "gpt-4o",
                    config=pconfig,
                )

        verdict = await _classify_completion(llm, result_text or "") if llm else "pending"

        if verdict in ("completed", "failed"):
            job.status = verdict
            job.resolved_at = datetime.now(timezone.utc)
            db.commit()
            _post_job_message(db, job, verdict)
            _unschedule(job_id)
    except Exception as e:
        logger.exception(f"Async job {job_id} poll raised an unexpected error: {e}")
    finally:
        db.close()


def _post_job_message(db, job, verdict: str):
    from models import Message
    label = {"completed": "✅ Background job finished", "failed": "⚠️ Background job failed", "expired": "⏱️ Background job check timed out"}[verdict]
    content = f"{label}: {job.description}\n\n{job.last_result or job.error or ''}".strip()
    msg = Message(
        session_id=job.session_id,
        role="assistant",
        content=content,
        agent_id=job.agent_id,
        metadata_json=json.dumps({"async_job_id": job.id, "async_job_status": verdict}),
    )
    db.add(msg)
    db.commit()


def _unschedule(job_id):
    from scheduler import scheduler
    try:
        scheduler.remove_job(f"async_job_{job_id}")
    except Exception:
        pass


async def poll_async_job_mongo(job_id: str):
    from database_mongo import get_database
    from models_mongo import AsyncJobCollection, MCPServerCollection, MessageCollection, AgentCollection, LLMProviderCollection
    from mcp_client import connect_mcp_server
    from encryption import decrypt_api_key
    from llm.provider_factory import create_provider_from_config
    from bson import ObjectId

    mongo_db = get_database()
    job = await AsyncJobCollection.find_by_id(mongo_db, job_id)
    if not job or job.get("status") != "pending":
        _unschedule(job_id)
        return

    poll_count = job.get("poll_count", 0) + 1
    max_polls = job.get("max_polls", 120)
    if poll_count > max_polls:
        await AsyncJobCollection.update(mongo_db, job_id, {
            "status": "expired", "poll_count": poll_count, "resolved_at": datetime.now(timezone.utc),
        })
        job["status"] = "expired"
        await _post_job_message_mongo(mongo_db, job, "expired")
        _unschedule(job_id)
        return

    server = await MCPServerCollection.find_by_id(mongo_db, job["mcp_server_id"])
    if not server:
        await AsyncJobCollection.update(mongo_db, job_id, {
            "status": "failed", "error": "MCP server no longer exists",
            "poll_count": poll_count, "resolved_at": datetime.now(timezone.utc),
        })
        job["status"] = "failed"
        job["error"] = "MCP server no longer exists"
        await _post_job_message_mongo(mongo_db, job, "failed")
        _unschedule(job_id)
        return

    config = dict(server)
    config["id"] = str(server["_id"])

    try:
        poll_args_raw = job.get("poll_arguments_json")
        poll_args = json.loads(poll_args_raw) if poll_args_raw else {}
        async with connect_mcp_server(config) as conn:
            result_text = await conn.call_tool(job["poll_tool_name"], poll_args)
    except Exception as e:
        await AsyncJobCollection.update(mongo_db, job_id, {"poll_count": poll_count})
        logger.warning(f"Async job {job_id} poll call failed (will retry): {e}")
        return

    updates = {"poll_count": poll_count, "last_result": result_text[:8000] if result_text else None}

    agent = await AgentCollection.find_by_id(mongo_db, job["agent_id"]) if job.get("agent_id") else None
    llm = None
    if agent and agent.get("provider_id"):
        provider = await LLMProviderCollection.find_by_id(mongo_db, str(agent["provider_id"]))
        if provider:
            api_key = decrypt_api_key(provider["api_key"]) if provider.get("api_key") else None
            pconfig_raw = provider.get("config_json")
            pconfig = json.loads(pconfig_raw) if isinstance(pconfig_raw, str) and pconfig_raw else pconfig_raw
            llm = create_provider_from_config(
                provider_type=provider["provider_type"], api_key=api_key,
                base_url=provider.get("base_url"), model_id=agent.get("model_id") or provider.get("model_id") or "gpt-4o",
                config=pconfig,
            )

    verdict = await _classify_completion(llm, result_text or "") if llm else "pending"

    if verdict in ("completed", "failed"):
        updates["status"] = verdict
        updates["resolved_at"] = datetime.now(timezone.utc)
        await AsyncJobCollection.update(mongo_db, job_id, updates)
        job.update(updates)
        await _post_job_message_mongo(mongo_db, job, verdict)
        _unschedule(job_id)
    else:
        await AsyncJobCollection.update(mongo_db, job_id, updates)


async def _post_job_message_mongo(mongo_db, job: dict, verdict: str):
    from models_mongo import MessageCollection
    label = {"completed": "✅ Background job finished", "failed": "⚠️ Background job failed", "expired": "⏱️ Background job check timed out"}[verdict]
    content = f"{label}: {job.get('description', '')}\n\n{job.get('last_result') or job.get('error') or ''}".strip()
    await MessageCollection.create(mongo_db, {
        "session_id": job["session_id"],
        "role": "assistant",
        "content": content,
        "agent_id": job.get("agent_id"),
        "metadata_json": json.dumps({"async_job_id": str(job["_id"]), "async_job_status": verdict}),
    })
