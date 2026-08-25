"""
schedule_async_check — a native tool agents can call when an MCP tool they just
invoked started a long-running job (e.g. "create_design" that must be polled via
a separate "get_design_status" tool). The agent explicitly opts into background
polling instead of promising to "check back later" with no mechanism behind it.

Execution creates an AsyncJob record and registers a recurring APScheduler job
(async_job_poller.poll_async_job_{sqlite,mongo}) that re-invokes the given MCP
tool on an interval, until it reports completion, fails, or hits max_polls.
"""
import json

SCHEDULE_ASYNC_CHECK_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "schedule_async_check",
        "description": (
            "Register a background check for a long-running job you just started via an MCP tool "
            "(e.g. after calling create_design, schedule a check of get_design_status). The backend "
            "will re-invoke the given MCP tool on an interval, even after this conversation turn ends, "
            "and post a new message into this session once it completes. Only call this for tools on "
            "MCP servers currently connected to this agent."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mcp_server_name": {
                    "type": "string",
                    "description": "The MCP server name (as used in the mcp__<server>__<tool> tool prefix) that owns the poll tool.",
                },
                "poll_tool_name": {
                    "type": "string",
                    "description": "Unprefixed name of the MCP tool to re-invoke to check status (e.g. 'get_design_status').",
                },
                "poll_arguments": {
                    "type": "object",
                    "description": "Arguments to pass on every poll call (e.g. the job/design ID returned by the tool that started the job).",
                },
                "description": {
                    "type": "string",
                    "description": "Short human-readable label for what's being waited on, shown to the user (e.g. 'Landing page design generation').",
                },
                "interval_seconds": {
                    "type": "integer",
                    "description": "Seconds between checks. Default 30. Minimum 15.",
                },
            },
            "required": ["mcp_server_name", "poll_tool_name", "poll_arguments", "description"],
        },
    },
}


def is_async_job_tool(tool_name: str) -> bool:
    return tool_name == "schedule_async_check"


async def execute_schedule_async_check(
    arguments_str: str,
    session_id: int | str,
    agent_id: int | str | None,
    mcp_server_configs: list[dict],
    db_type: str,
    db=None,
) -> str:
    """
    Handles a schedule_async_check tool call: resolves the named MCP server
    against the agent's currently-connected servers, persists an AsyncJob, and
    registers the recurring APScheduler poll job. Returns a JSON string result
    for the LLM (mirrors other tool executors' str-return convention).
    """
    try:
        args = json.loads(arguments_str) if arguments_str else {}
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid arguments JSON"})

    server_name = args.get("mcp_server_name", "")
    poll_tool_name = args.get("poll_tool_name", "")
    poll_arguments = args.get("poll_arguments") or {}
    description = args.get("description", "Background job")
    interval_seconds = max(int(args.get("interval_seconds") or 30), 15)

    if not server_name or not poll_tool_name:
        return json.dumps({"error": "mcp_server_name and poll_tool_name are required"})

    server_config = next((c for c in mcp_server_configs if c.get("name") == server_name), None)
    if not server_config:
        return json.dumps({"error": f"MCP server '{server_name}' is not connected to this agent"})

    mcp_server_id = server_config.get("id")

    from scheduler import scheduler
    from apscheduler.triggers.interval import IntervalTrigger

    if db_type == "mongo":
        from models_mongo import AsyncJobCollection
        job = await AsyncJobCollection.create(db, {
            "session_id": str(session_id),
            "agent_id": str(agent_id) if agent_id else None,
            "mcp_server_id": str(mcp_server_id),
            "description": description,
            "poll_tool_name": poll_tool_name,
            "poll_arguments_json": json.dumps(poll_arguments),
            "interval_seconds": interval_seconds,
            "max_polls": 120,
        })
        job_id = str(job["_id"])
        from async_job_poller import poll_async_job_mongo
        scheduler.add_job(
            poll_async_job_mongo,
            trigger=IntervalTrigger(seconds=interval_seconds),
            args=[job_id],
            id=f"async_job_{job_id}",
            replace_existing=True,
        )
    else:
        from models import AsyncJob
        job = AsyncJob(
            session_id=int(session_id),
            agent_id=int(agent_id) if agent_id else None,
            mcp_server_id=int(mcp_server_id),
            description=description,
            poll_tool_name=poll_tool_name,
            poll_arguments_json=json.dumps(poll_arguments),
            interval_seconds=interval_seconds,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
        from async_job_poller import poll_async_job_sqlite
        scheduler.add_job(
            poll_async_job_sqlite,
            trigger=IntervalTrigger(seconds=interval_seconds),
            args=[job_id],
            id=f"async_job_{job_id}",
            replace_existing=True,
        )

    return json.dumps({
        "success": True,
        "job_id": job_id,
        "message": f"Background check registered. I will re-check '{poll_tool_name}' every {interval_seconds}s and post a message to this session when it completes.",
    })
