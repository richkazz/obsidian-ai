"""
call_teammate — a native tool injected only during team chats, letting any
agent delegate a sub-question to a named teammate mid-turn and get their
response back as a tool result to reason over.

Previously "team" collaboration meant strictly: a router picks one agent
(coordinate), all agents fire independently in parallel with no visibility
into each other (route), or a fixed one-way relay of full outputs
(collaborate) — no agent could ever actually ask another agent something.
This tool is the first real inter-agent handoff mechanism.

Delegation is capped at one hop (MAX_DELEGATION_DEPTH) — the delegate agent
answers using its own tools/expertise but cannot itself call call_teammate
again. This bounds worst-case latency/cost and avoids delegation cycles
(A calls B calls A calls B...) without needing cycle detection.
"""
import json

MAX_DELEGATION_DEPTH = 1

CALL_TEAMMATE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "call_teammate",
        "description": (
            "Ask a specific teammate on this team to answer a question or perform a sub-task, "
            "and get their response back to use in your own answer. Use this when a teammate has "
            "expertise, tools, or context you don't have — e.g. delegate a data-lookup question to "
            "the agent whose role covers it. The teammate answers using their own tools and knowledge; "
            "you then incorporate their response into your final answer to the user."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "teammate_name": {
                    "type": "string",
                    "description": "Exact name of the teammate to ask, as listed in your team context.",
                },
                "message": {
                    "type": "string",
                    "description": "The question or task to send to that teammate.",
                },
            },
            "required": ["teammate_name", "message"],
        },
    },
}


def is_call_teammate_tool(tool_name: str) -> bool:
    return tool_name == "call_teammate"


async def execute_call_teammate(
    arguments_str: str,
    agents_with_providers: list,
    current_agent_id,
    db_type: str,
    db,
    depth: int = 0,
) -> str:
    """Resolve teammate_name against the team roster and run a bounded,
    non-streaming turn for that teammate. Returns a JSON string result
    (mirrors other tool executors' str-return convention)."""
    try:
        args = json.loads(arguments_str) if arguments_str else {}
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid arguments JSON"})

    teammate_name = (args.get("teammate_name") or "").strip()
    message = args.get("message", "")
    if not teammate_name or not message:
        return json.dumps({"error": "teammate_name and message are required"})

    if depth >= MAX_DELEGATION_DEPTH:
        return json.dumps({"error": "Delegation depth limit reached — the teammate you're asking cannot delegate further."})

    if db_type == "mongo":
        target = next(
            (ag_pr for ag_pr in agents_with_providers
             if ag_pr[0].get("name", "").lower() == teammate_name.lower() and str(ag_pr[0]["_id"]) != str(current_agent_id)),
            None,
        )
    else:
        target = next(
            (ag_pr for ag_pr in agents_with_providers
             if ag_pr[0].name.lower() == teammate_name.lower() and ag_pr[0].id != current_agent_id),
            None,
        )

    if not target:
        names = [
            (ag.get("name") if db_type == "mongo" else ag.name)
            for ag, _ in agents_with_providers
        ]
        return json.dumps({"error": f"No teammate named '{teammate_name}' found. Available: {', '.join(names)}"})

    target_agent, target_provider = target

    from llm.base import LLMMessage

    try:
        if db_type == "mongo":
            from routers.chat_router import _create_llm_for_mongo_provider, _build_tools_for_llm_mongo, _chat_with_tools_mongo, _chat_with_tools_and_mcp_mongo, _load_mcp_server_configs_mongo
            llm = _create_llm_for_mongo_provider(target_provider, target_agent.get("model_id") or target_provider.get("model_id") or "gpt-4o")
            tools = await _build_tools_for_llm_mongo(target_agent, db)
            mcp_configs = await _load_mcp_server_configs_mongo(target_agent, db)
            system_prompt = (target_agent.get("system_prompt") or "") + (
                "\n\nA teammate has delegated this question to you directly. Answer it clearly and completely — "
                "your response will be relayed back to them, not shown directly to the end user."
            )
            if mcp_configs:
                content = await _chat_with_tools_and_mcp_mongo(llm, [LLMMessage(role="user", content=message)], system_prompt, tools, db, mcp_configs)
            else:
                content = await _chat_with_tools_mongo(llm, [LLMMessage(role="user", content=message)], system_prompt, tools, db)
        else:
            from routers.chat_router import _create_llm_for_provider, _build_tools_for_llm, _chat_with_tools, _chat_with_tools_and_mcp, _load_mcp_server_configs
            llm = _create_llm_for_provider(target_provider, target_agent.model_id or target_provider.model_id or "gpt-4o")
            tools = _build_tools_for_llm(target_agent, db)
            mcp_configs = _load_mcp_server_configs(target_agent, db)
            system_prompt = (target_agent.system_prompt or "") + (
                "\n\nA teammate has delegated this question to you directly. Answer it clearly and completely — "
                "your response will be relayed back to them, not shown directly to the end user."
            )
            if mcp_configs:
                content = await _chat_with_tools_and_mcp(llm, [LLMMessage(role="user", content=message)], system_prompt, tools, db, mcp_configs)
            else:
                content = await _chat_with_tools(llm, [LLMMessage(role="user", content=message)], system_prompt, tools, db)
    except Exception as e:
        return json.dumps({"error": f"Teammate '{teammate_name}' failed to respond: {e}"})

    return json.dumps({"teammate": teammate_name, "response": content})
