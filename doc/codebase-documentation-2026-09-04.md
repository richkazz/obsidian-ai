# Codebase Documentation — Obsidian AI
Generated: 2026-09-04

## Overview
Obsidian AI is an open-source, full-stack AI agent management, orchestration, and automation platform. It features a FastAPI backend (Python 3.12) supporting dual database persistence (SQLite via SQLAlchemy and MongoDB via Motor), a Next.js 16 frontend (React 19, Tailwind CSS 4, Zustand) with NextAuth v5, and a Node.js WhatsApp Web sidecar (`wa-bridge`). The architecture follows a client-server model with real-time Server-Sent Events (SSE) streaming for chat and workflow execution, background worker task scheduling via APScheduler, end-to-end AES payload encryption for auth credentials, and containerized Docker sandboxing for isolated code execution. Entry points for execution are `backend/main.py` for FastAPI API services, background scheduler, and lifespan startup/shutdown, `frontend/app/layout.tsx` / `frontend/proxy.ts` for web application rendering and API proxying, and `wa-bridge/index.js` for external WhatsApp integration.

---

## Directory Map

```text
obsidian-ai/
├── backend/                       # FastAPI (Python 3.12) server
│   ├── main.py                    # App entrypoint, lifespan startup/shutdown, routing, DB migrations
│   ├── config.py                  # Configuration & DATABASE_TYPE selector
│   ├── database.py                # SQLite engine & SessionLocal ORM setup
│   ├── database_mongo.py          # Motor async MongoDB client & DB connector
│   ├── models.py                  # SQLAlchemy ORM models (SQLite)
│   ├── models_mongo.py            # Motor collection wrappers & indexes (MongoDB)
│   ├── schemas.py                 # Pydantic request/response validation schemas
│   ├── auth.py                    # JWT token creation, verification, password hashing, RBAC permissions
│   ├── crypto_utils.py            # AES request payload decryption (PyCryptodome)
│   ├── encryption.py              # Fernet encryption for API keys and secrets at rest
│   ├── dag_executor.py            # Unified async topological DAG execution engine for workflows
│   ├── eval_engine.py             # Eval suite evaluation, grading logic (exact, contains, llm_judge)
│   ├── optimizer.py               # Trace-driven prompt auto-optimizer pipeline
│   ├── mcp_client.py              # Model Context Protocol (MCP) client & stdio/SSE transport
│   ├── rag_service.py             # Vector search indexing (FAISS/Leann) & RAG retrieval
│   ├── scheduler.py               # Global APScheduler background scheduler instance
│   ├── scheduler_executor.py      # Background cron workflow execution jobs
│   ├── async_job_poller.py        # Background poller for async long-running tools
│   ├── sandbox_tools.py           # Docker container execution tools (sandbox_bash, sandbox_python, etc.)
│   ├── builtin_tools.py           # Built-in agent tools (web_search, calculator, weather, time)
│   ├── team_delegation_tools.py   # Multi-agent team coordination tools (delegate_task, etc.)
│   ├── llm/                       # LLM provider abstractions (BaseLLMProvider factory)
│   │   ├── base.py                # Abstract BaseLLMProvider & LLMMessage/LLMStreamChunk types
│   │   ├── provider_factory.py    # Provider factory mapping provider_type to class
│   │   ├── openai_provider.py    # OpenAI & OpenRouter provider (Chat Completions & streaming)
│   │   ├── anthropic_provider.py # Anthropic Claude provider
│   │   ├── google_provider.py    # Google Gemini provider
│   │   └── nvidia_provider.py    # NVIDIA NIM provider
│   ├── services/                  # Core domain & background services
│   │   ├── agent_runner.py        # Headless agent execution turn for channels/WhatsApp
│   │   ├── whatsapp_service.py    # WhatsApp message handler & incoming webhook router
│   │   ├── tts_service.py         # Multi-backend TTS pipeline (Qwen3-TTS, Pocket TTS, Kokoro)
│   │   ├── stt_service.py         # Groq Whisper API / faster-whisper speech-to-text
│   │   ├── authorization_service.py # Granular RBAC and ownership authorization engine
│   │   └── schema_validation_service.py # Draft-07 JSON schema validator
│   └── routers/                   # REST & SSE API endpoints
│       ├── chat_router.py         # Streaming chat, HITL approval, tool proposals
│       ├── agents_router.py       # Agent CRUD, export/import, versioning, sandboxing
│       ├── teams_router.py        # Multi-agent team CRUD & coordination modes
│       ├── workflows_router.py    # Workflow DAG definitions
│       ├── workflow_runs_router.py# Workflow execution, live SSE run tracking
│       ├── whatsapp_router.py     # WhatsApp channel management & voice clone samples
│       └── ...                    # (auth, user, providers, tools, mcp, knowledge, eval, optimizer, etc.)
├── frontend/                      # Next.js 16 (React 19) web application
│   ├── app/                       # App Router pages and routes
│   │   ├── layout.tsx             # Root layout & providers
│   │   ├── page.tsx               # Landing page
│   │   └── (authenticated)/       # Protected application pages (playground, workflows, sessions, etc.)
│   ├── components/                # React UI components
│   │   ├── playground/            # Chat interface, sidebar, artifact panel, DAG editor
│   │   ├── ai-elements/           # SSE stream display (HITL approval cards, tool call chips, artifacts)
│   │   └── ui/                    # Radix UI / shadcn primitive components
│   ├── lib/                       # Frontend utility modules
│   │   ├── api-client.ts          # Axios HTTP client with auth headers
│   │   ├── crypto.ts              # Client-side AES payload encryption (CryptoJS)
│   │   └── stream.ts              # SSE stream parser & reader
│   └── stores/                    # Zustand client state stores
│       ├── playground-store.ts    # Playground state (agents, active session, artifacts, messages)
│       └── dashboard-store.ts     # Dashboard & analytics state
└── wa-bridge/                     # Node.js Baileys WhatsApp Web sidecar
    ├── index.js                   # Express server & Baileys socket connection manager
    └── package.json               # Node.js dependencies (@whiskeysockets/baileys, express, qrcode-terminal)
```

---

## Functionality Reference

### 1. User Registration & AES Auth Payload Decryption
- **Trigger:** User submits the registration form on `/register`.
- **Entry point:** `frontend/app/register/page.tsx` → `handleRegister()` calls `POST /auth/register` (`backend/routers/auth_router.py` → `register_user()`).
- **What it does:**
  1. Client encrypts sensitive fields (`username`, `email`, `password`) using AES (`frontend/lib/crypto.ts` → `encryptPayload()`).
  2. Server receives `EncryptedPayload`, decrypts using `backend/crypto_utils.py` → `decrypt_payload()` with `ENCRYPTION_KEY`.
  3. Validates unique username/email against database (`User` table / `users` Mongo collection).
  4. Hashes password using `bcrypt` (`backend/auth.py` → `get_password_hash()`).
  5. Creates user record with default role `guest` and permissions.
- **Touches:** `backend/crypto_utils.py`, `backend/auth.py`, `backend/models.py` / `backend/models_mongo.py`.
- **Inputs/Outputs:**
  - *Input:* `EncryptedPayload` (AES ciphertext string).
  - *Output:* `UserResponse` (`id`, `username`, `email`, `role`, `created_at`).
- **Side effects:** Writes new row to `users` database table/collection.
- **Notes/gotchas:** `ENCRYPTION_KEY` on backend must match `NEXT_PUBLIC_ENCRYPTION_KEY` on frontend, or payload decryption raises HTTP 400.

### 2. User Authentication, 2FA/TOTP & JWT Generation
- **Trigger:** User submits login form on `/login` or NextAuth credentials authorization.
- **Entry point:** `backend/routers/auth_router.py` → `login_user()`.
- **What it does:**
  1. Decrypts AES payload to extract credentials.
  2. Verifies user password against stored bcrypt hash via `verify_password()`.
  3. Checks if 2FA/TOTP is enabled on the account. If enabled, verifies 6-digit TOTP code using `pyotp.TOTP(totp_secret).verify(totp_code)`.
  4. Creates JWT access token containing `sub` (username), `user_id`, `role`, signed with `JWT_SECRET_KEY` using HS256.
- **Touches:** `backend/auth.py`, `backend/crypto_utils.py`, `pyotp`, `python-jose`.
- **Inputs/Outputs:**
  - *Input:* `LoginRequest` (encrypted payload with username, password, optional `totp_code`).
  - *Output:* `Token` (`access_token`, `token_type: bearer`).
- **Side effects:** Issues signed JWT token.
- **Notes/gotchas:** Token expiration controlled by `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` env var (default: 30 minutes).

### 3. User Account Management & Role-Based Permissions
- **Trigger:** Admin user updates user role or permissions on `/admin`.
- **Entry point:** `backend/routers/admin_router.py` → `update_user()`.
- **What it does:**
  1. Verifies requesting user has `admin` role via `get_current_admin_user()`.
  2. Updates target user record fields: `role` (`admin` or `guest`), `is_active`, and boolean permission flags (`can_create_agents`, `can_create_teams`, `can_create_workflows`, `can_create_tools`, `can_manage_providers`, `can_manage_mcp`).
  3. Saves changes to database.
- **Touches:** `backend/routers/admin_router.py`, `backend/auth.py`, `backend/services/authorization_service.py`, `backend/models.py`.
- **Inputs/Outputs:**
  - *Input:* `AdminUserUpdate` (role, permission flags, active status).
  - *Output:* `AdminUserResponse` object.
- **Side effects:** Updates `users` database table/collection.
- **Notes/gotchas:** Admins cannot revoke admin status from their own active account to prevent lockouts.

### 4. Real-Time Streaming Chat Execution (Agent/Team turn)
- **Trigger:** User sends a message in `/playground` chat input.
- **Entry point:** `frontend/components/playground/chat/chat-input.tsx` calls `POST /chat` (`backend/routers/chat_router.py` → `chat()`).
- **What it does:**
  1. Validates JWT auth token and user permissions.
  2. Resolves session (`session_id`) or creates a new session assigned to agent/team.
  3. Persists user message to `messages` database table/collection.
  4. Fetches agent configuration, attached tools, MCP servers, knowledge base vector stores, and active long-term memories (`agent_memories`).
  5. Injects long-term memories and context compaction summaries into system prompt.
  6. Constructs LLM provider instance via `backend/llm/provider_factory.py` -> `create_provider_from_config()`.
  7. Enters iterative tool execution loop (up to `MAX_TOOL_ROUNDS = 10`):
     - Streams LLM response chunks (`content`, `reasoning`, `tool_call`) as Server-Sent Events (`EventSourceResponse`).
     - If LLM emits tool call, checks Human-in-the-Loop (HITL) approval requirements:
       - If HITL required, yields `hitl_required` event and suspends execution via `asyncio.Event`.
     - Executes approved tool calls (native Python, HTTP, MCP, or Docker sandbox tool).
     - Feeds tool output back into LLM messages and resumes streaming.
  8. Automatically triggers background memory extraction on session boundary if enabled.
  9. Yields `[DONE]` SSE frame and saves assistant message, token usage, and trace spans (`trace_spans`).
- **Touches:** `backend/llm/provider_factory.py`, `backend/mcp_client.py`, `backend/sandbox_tools.py`, `backend/builtin_tools.py`, `backend/rag_service.py`, `backend/routers/memory_router.py`, `backend/routers/traces_router.py`.
- **Inputs/Outputs:**
  - *Input:* `ChatRequest` (`message`, `agent_id`, `team_id`, `session_id`, `attachments`).
  - *Output:* SSE event stream (`event: content`, `event: tool_call`, `event: hitl_required`, `event: artifact`, `event: done`).
- **Side effects:** Creates message records, updates session token totals, records `trace_spans`, creates `HITLApproval` records if paused.
- **Notes/gotchas:** Streaming uses `sse-starlette`. If connection drops mid-turn, pending HITL events time out after 10 minutes and auto-deny.

### 5. Human-In-The-Loop (HITL) Tool Approval Resolution
- **Trigger:** User clicks "Approve" or "Deny" on inline approval card in chat UI or top bar notification badge.
- **Entry point:** `frontend/components/ai-elements/hitl-approval.tsx` calls `POST /chat/hitl/{approval_id}/respond` (`backend/routers/chat_router.py` → `respond_hitl()`, `approve_hitl()`, `reject_hitl()`).
- **What it does:**
  1. Retrieves `HITLApproval` record by ID from database.
  2. Validates session ownership and pending status.
  3. Updates approval status to `approved` or `denied` and records `resolved_at`.
  4. Looks up `asyncio.Event` in module-level `_hitl_events` dict (`"{session_id}:{tool_call_id}"`).
  5. Sets event (`event.set()`), unblocking suspended chat generator in `chat()`.
- **Touches:** `backend/routers/chat_router.py`, `backend/models.py` / `backend/models_mongo.py`.
- **Inputs/Outputs:**
  - *Input:* `HITLApprovalResponse` (`status: approved | denied`).
  - *Output:* JSON status response (`{"status": "success", "approval_status": "approved"}`).
- **Side effects:** Unblocks waiting async task in `chat_router.py`; updates `hitl_approvals` table.
- **Notes/gotchas:** Server restart clears in-memory `_hitl_events` dict. On startup, `main.py` lifespan automatically auto-denies all pending approvals in DB to prevent orphan locks.

### 6. Dynamic Tool Proposal & Review
- **Trigger:** Agent with `allow_tool_creation = True` calls `create_tool` virtual function during chat.
- **Entry point:** `backend/routers/chat_router.py` → `approve_tool_proposal()`, `reject_tool_proposal()`.
- **What it does:**
  1. Agent proposes tool name, description, handler type (`python` or `http`), parameters schema, and handler code/URL.
  2. Server creates a `ToolProposal` record with status `pending`.
  3. Streamer yields `tool_proposal_required` SSE event to frontend.
  4. Chat generator suspends on `_tool_proposal_events` `asyncio.Event`.
  5. User reviews tool proposal card in chat and clicks "Approve" or "Reject" (`POST /chat/sessions/{session_id}/tool-proposals/{proposal_id}/approve`).
  6. Upon approval, backend creates a new active `ToolDefinition` record and injects tool into current session dynamic tools (`_session_dynamic_tools`).
  7. Unblocks chat stream and lets agent execute the newly created tool immediately.
- **Touches:** `backend/routers/chat_router.py`, `backend/routers/tools_router.py`, `backend/models.py` / `backend/models_mongo.py`.
- **Inputs/Outputs:**
  - *Input:* Proposal ID and session ID parameters.
  - *Output:* Newly created `ToolDefinition` and resumed chat stream.
- **Side effects:** Adds row to `tool_definitions` and `tool_proposals`.
- **Notes/gotchas:** Proposals expire after 10 minutes if left unreviewed.

### 7. Custom Tool Definition CRUD & Validation
- **Trigger:** User creates, edits, or deletes a custom tool definition on `/settings`.
- **Entry point:** `backend/routers/tools_router.py` → `create_tool_definition()`, `update_tool_definition()`, `delete_tool_definition()`.
- **What it does:**
  1. Validates input schema using Draft-07 JSON Schema validator (`backend/services/schema_validation_service.py`).
  2. Checks for unique tool name across active tools; returns 409 Conflict if duplicate exists.
  3. Saves tool definition with handler type (`python`, `http`, or `builtin`), parameters schema, code, or REST endpoint configuration.
  4. Supports setting default `requires_confirmation` flag for HITL enforcement.
- **Touches:** `backend/routers/tools_router.py`, `backend/services/schema_validation_service.py`, `backend/models.py`.
- **Inputs/Outputs:**
  - *Input:* `ToolDefinitionCreate` / `ToolDefinitionUpdate`.
  - *Output:* `ToolDefinitionResponse` object.
- **Side effects:** Inserts, updates, or soft-deletes rows in `tool_definitions` table.

### 8. Visual Workflow Creation & Topological DAG Execution Engine
- **Trigger:** User executes workflow manually from `/workflows` page or APScheduler triggers a scheduled workflow cron job.
- **Entry point:** Manual run: `POST /workflows/{id}/run` (`backend/routers/workflow_runs_router.py` → `run_workflow()`). Scheduled run: `backend/scheduler_executor.py` → `run_scheduled_workflow_sqlite()`. Core execution: `backend/dag_executor.py` → `execute_dag()`.
- **What it does:**
  1. Loads workflow steps definition. Step types supported: `agent`, `start`, `end`, `condition`, `approval`, `map`.
  2. Validates step graph topology for cycles using iterative DFS (`topological_validate()`).
  3. Constructs `DagContext` containing database-specific async callables for agent/provider lookup, tool building, and run state persistence.
  4. Runs topological execution loop:
     - Identifies all ready nodes (nodes whose `depends_on` parents have completed and branch conditions match).
     - Concurrently launches ready nodes as `asyncio.Task`s.
     - Resolves variable interpolation tags (`{{ nodes.<node_id>.output.<path> }}`).
     - For `agent` nodes: calls LLM streaming loop, handles tool calls, retries on failure with exponential backoff if configured.
     - For `condition` nodes: uses LLM or branch logic to pick active path, marks inactive branches as `skipped`.
     - For `approval` nodes: pauses run, creates `WorkflowApproval` record, waits on `workflow_hitl_events` with mandatory timeout (`DEFAULT_APPROVAL_TIMEOUT_SECONDS = 600`).
     - For `map` nodes: parses JSON list input, executes agent tasks concurrently up to `concurrency_limit` using `asyncio.Semaphore`, reduces outputs (`list` or `concat`).
  5. Emits SSE event frames for each node state transition (`node_start`, `node_content_delta`, `node_paused`, `node_complete`, `node_error`, `workflow_done`).
  6. Persists final `WorkflowRun` record with status (`completed` or `failed`) and full step outputs JSON.
- **Touches:** `backend/dag_executor.py`, `backend/routers/workflow_runs_router.py`, `backend/scheduler_executor.py`, `backend/models.py` / `backend/models_mongo.py`.
- **Inputs/Outputs:**
  - *Input:* `input_text` string, workflow step definitions JSON.
  - *Output:* Stream of workflow run SSE events and final `WorkflowRun` record.
- **Side effects:** Creates `WorkflowRun` and `TraceSpan` records.

### 9. Scheduled Workflow Background Cron Execution
- **Trigger:** APScheduler background worker triggers a registered workflow cron job.
- **Entry point:** `backend/routers/schedule_router.py` → `create_schedule()`, `backend/scheduler.py`, `backend/scheduler_executor.py` → `run_scheduled_workflow_sqlite()` / `run_scheduled_workflow_mongo()`.
- **What it does:**
  1. User creates schedule supplying standard 5-field cron expression (e.g. `0 9 * * 1-5`) and optional fixed input text.
  2. APScheduler registers cron trigger with persistent job store.
  3. On trigger time, `scheduler_executor` executes workflow headlessly via `execute_dag()`.
  4. Records execution output in `workflow_runs` table with trigger mode `scheduled`.
  5. Active schedules automatically re-register on server startup during lifespan.
- **Touches:** `backend/scheduler.py`, `backend/scheduler_executor.py`, `backend/routers/schedule_router.py`, `croniter`.
- **Inputs/Outputs:**
  - *Input:* `WorkflowScheduleCreate` (`cron_expression`, `input_text`, `is_active`).
  - *Output:* `WorkflowScheduleResponse` object.
- **Side effects:** Persists schedules in `workflow_schedules`; generates `WorkflowRun` records on execution.

### 10. Multi-Agent Team Configuration & Coordination Execution
- **Trigger:** User interacts with a multi-agent team in `/playground`.
- **Entry point:** `backend/routers/teams_router.py` → `create_team()`, `backend/routers/chat_router.py` → `_team_chat_coordinate()`, `_team_chat_route()`, `_team_chat_collaborate()`.
- **What it does:**
  1. Configures multi-agent team with specific mode:
     - `coordinate`: Lead agent decomposes user query, delegates sub-tasks to member agents via `delegate_task` tool, and synthesizes final answer.
     - `route`: Router logic evaluates message content and routes execution to the single best agent.
     - `collaborate`: Agents execute sequentially in defined pipeline order, passing accumulated outputs to subsequent members.
  2. Orchestrates turn execution using LLM provider calls and streams combined response to frontend.
- **Touches:** `backend/routers/teams_router.py`, `backend/routers/chat_router.py`, `backend/team_delegation_tools.py`.
- **Inputs/Outputs:**
  - *Input:* `TeamCreate` (`name`, `mode`, `leader_agent_id`, `member_agent_ids`).
  - *Output:* `TeamResponse` object and SSE chat stream.
- **Side effects:** Creates `teams` database record and multi-agent message logs.

### 11. Agent Configuration Versioning & Rollback
- **Trigger:** User updates agent configuration in agent dialog or clicks "Rollback" in version history panel.
- **Entry point:** Update: `PUT /agents/{id}` (`backend/routers/agents_router.py` → `update_agent()`). Rollback: `POST /versions/agents/{id}/{version_id}/rollback` (`backend/routers/versions_router.py` → `rollback_agent_version()`).
- **What it does:**
  1. On every agent update, server builds a complete JSON configuration snapshot of existing agent state (`_build_config_snapshot()`).
  2. Inserts snapshot record into `agent_versions` table with incremented `version_number`.
  3. On rollback request, retrieves snapshot by `version_id`.
  4. Restores all snapshot fields (`system_prompt`, `model_id`, `tools_json`, `mcp_servers_json`, `knowledge_base_ids_json`, `config_json`) back onto current agent record.
  5. Automatically creates a new version snapshot before restoring, so rollbacks themselves are fully undoable.
- **Touches:** `backend/routers/agents_router.py`, `backend/routers/versions_router.py`, `backend/models.py` / `backend/models_mongo.py`.
- **Inputs/Outputs:**
  - *Input:* Agent update body or version ID parameter.
  - *Output:* Updated `AgentResponse` object.
- **Side effects:** Inserts new row into `agent_versions` table; daily background job prunes versions older than 72 hours (always retaining latest version).

### 12. Agent Import and Export
- **Trigger:** User exports agent configuration as JSON file or imports agent JSON file.
- **Entry point:** Export: `GET /agents/{agent_id}/export` (`backend/routers/agents_router.py` → `export_agent()`). Import: `POST /agents/import` (`backend/routers/agents_router.py` → `import_agent()`).
- **What it does:**
  1. Export resolves all internal database IDs (tools, MCP servers, knowledge bases) into human-readable names and exports a self-contained portable JSON payload (`aios_export_version: "1"`).
  2. Import accepts JSON payload, maps names back to target user's existing resources in database, reports missing resource warnings, and creates new agent record.
- **Touches:** `backend/routers/agents_router.py`, `backend/models.py`.
- **Inputs/Outputs:**
  - *Input:* `agent_id` path param or JSON import file.
  - *Output:* Downloadable JSON file (export) or `AgentImportResponse` with warnings (import).
- **Side effects:** Reads/writes `agents` database records.

### 13. Long-Term Agent Memory Reflection & Storage
- **Trigger:** First message in a new agent session when `memory_enabled = True`.
- **Entry point:** `backend/routers/chat_router.py` → `_reflect_and_store_sqlite()` / `_reflect_and_store_mongo()`, `backend/routers/memory_router.py` → `get_agent_memories()`, `clear_agent_memories()`.
- **What it does:**
  1. Checks if previous session for `(agent_id, user_id)` pair has unprocessed messages (`memory_processed == False`).
  2. Calls background LLM reflection task to analyze conversation transcript.
  3. Extracts durable facts in four categories: `preference`, `context`, `decision`, `correction`.
  4. Assigns confidence score (0.0 - 1.0) to each extracted memory.
  5. Deduplicates against existing memories in `agent_memories` table based on memory key.
  6. Enforces maximum cap of 50 memories per agent/user pair (evicts lowest confidence facts when cap reached).
  7. Sets `memory_processed = True` on session.
  8. Injects all active memories into future system prompts as a structured context block.
- **Touches:** `backend/routers/memory_router.py`, `backend/routers/chat_router.py`, `backend/models.py` / `backend/models_mongo.py`.
- **Inputs/Outputs:**
  - *Input:* Session transcript text.
  - *Output:* List of created/updated `AgentMemory` records.
- **Side effects:** Inserts/updates rows in `agent_memories` table.

### 14. WhatsApp Channel Connection & Message Gateway
- **Trigger:** Incoming WhatsApp message delivered from Node.js sidecar (`wa-bridge`) via `POST /wa/incoming`.
- **Entry point:** `backend/routers/whatsapp_router.py` → `handle_whatsapp_incoming()` calls `backend/services/whatsapp_service.py` → `process_incoming_whatsapp_message()`.
- **What it does:**
  1. Sidecar (`wa-bridge/index.js`) maintains Baileys Web socket for WhatsApp connection and receives incoming messages.
  2. Forwards payload (`channel_id`, `sender_jid`, `message_text`, `media_path`) to FastAPI backend.
  3. Backend checks contact whitelist (`allowed_jids`). Rejects unauthorized senders with custom rejection message if configured.
  4. If incoming message is a voice note, calls `backend/services/stt_service.py` → `transcribe_audio()` using Groq Whisper API (`whisper-large-v3-turbo`) or local `faster-whisper` model.
  5. Resolves or creates persistent contact session (`WAContactSession`) mapping `(channel_id, sender_jid)` to an Obsidian AI `Session`.
  6. Executes agent turn headlessly via `backend/services/agent_runner.py` → `run_agent_headless()`.
  7. Strips XML `<artifact>` tags from text reply.
  8. If voice replies are enabled on channel (`voice_reply_enabled = True`):
     - Calls `backend/services/tts_service.py` -> `synthesize_speech()` pipeline (`Qwen3-TTS` on GPU with optional voice cloning sample -> `Pocket TTS` -> `Kokoro`).
     - Normalizes audio output to OGG Opus format using `ffmpeg`.
     - Sends voice note media payload back to sidecar.
  9. Sidecar posts text or voice reply back through Baileys socket to WhatsApp contact.
- **Touches:** `backend/routers/whatsapp_router.py`, `backend/services/whatsapp_service.py`, `backend/services/agent_runner.py`, `backend/services/tts_service.py`, `backend/services/stt_service.py`, `wa-bridge/index.js`.
- **Inputs/Outputs:**
  - *Input:* WhatsApp incoming webhook payload JSON.
  - *Output:* HTTP 200 JSON status response; outbound WhatsApp message sent via sidecar HTTP API (`POST http://localhost:3200/api/send`).
- **Side effects:** Persists messages in `messages` table, writes audio files to disk, sends WhatsApp messages.

### 15. WhatsApp Voice Reply Synthesis & Audio Processing
- **Trigger:** User uploads voice clone sample in channel settings or channel receives voice message.
- **Entry point:** `backend/routers/whatsapp_router.py` → `upload_voice_sample()`, `delete_voice_sample()`, `backend/services/tts_service.py` → `synthesize_speech()`.
- **What it does:**
  1. User uploads reference audio sample (WAV, MP3, WebM) on WhatsApp channel settings page.
  2. Backend normalizes audio sample to 16kHz mono WAV using `ffmpeg` and stores file in `VOICE_SAMPLES_DIR`.
  3. During voice reply synthesis, `tts_service.py` checks engine setting (`auto`, `qwen`, `classic`).
  4. If `Qwen3-TTS` is selected and voice sample exists, computes voice prompt embedding and caches in memory.
  5. Synthesizes voice note in user's cloned voice and encodes to OGG Opus for WhatsApp.
- **Touches:** `backend/routers/whatsapp_router.py`, `backend/services/tts_service.py`, `ffmpeg`.
- **Inputs/Outputs:**
  - *Input:* Uploaded audio file or text string.
  - *Output:* Transformed OGG Opus voice file path.
- **Side effects:** Writes voice sample files to disk storage.

### 16. Docker Sandbox Container Management & Tool Injection
- **Trigger:** User starts sandbox on agent/team page, or agent executes a sandbox tool (`sandbox_bash`, `sandbox_python`, `sandbox_write`, etc.).
- **Entry point:** Start container: `POST /agents/{id}/sandbox/start` (`backend/routers/sandbox_router.py` → `start_agent_sandbox()`). Execute tool: `backend/sandbox_tools.py` → `execute_sandbox_tool()`.
- **What it does:**
  1. On start: backend issues Docker API / CLI call to launch isolated container using image `obsidian-webdev-base:latest`.
  2. Container configured with 512MB RAM cap, 1 CPU core limit, and `/workspace` mount directory.
  3. Stores `sandbox_container_id` on agent or team model record.
  4. When chat turn runs on sandboxed agent/team, 9 sandbox tools are dynamically injected into agent toolset (`sandbox_bash`, `sandbox_write`, `sandbox_read`, `sandbox_ls`, `sandbox_glob`, `sandbox_grep`, `sandbox_delete`, `sandbox_python`, `sandbox_node`).
  5. Tool execution runs inside running container via `docker exec`.
  6. Output is captured and returned to LLM; files created or updated are instructed to be wrapped in `<artifact>` tags for instant UI preview.
- **Touches:** `backend/routers/sandbox_router.py`, `backend/sandbox_tools.py`, Docker engine API.
- **Inputs/Outputs:**
  - *Input:* Shell command string or file content path.
  - *Output:* Command execution output string (stdout/stderr).
- **Side effects:** Spawns Docker container process, modifies container workspace filesystem.
- **Notes/gotchas:** `obsidian-webdev-base:latest` image must be built before enabling sandbox (`docker build -f backend/Dockerfile.base -t obsidian-webdev-base:latest backend/`).

### 17. Eval Harness Test Suite Creation & Automated Grading
- **Trigger:** User clicks "Run Eval Suite" on `/evals` page or Prompt Auto-Optimizer triggers evaluation run.
- **Entry point:** `POST /evals/suites/{id}/run` (`backend/routers/eval_router.py` → `run_eval_suite_endpoint()`). Core logic: `backend/eval_engine.py` → `run_eval_suite_background()`.
- **What it does:**
  1. Creates an `EvalRun` record with status `pending`.
  2. Takes a snapshot of target agent's current configuration.
  3. Launches background task (`asyncio.create_task`).
  4. Iterates over test cases in suite (`test_cases_json`).
  5. For each test case, runs agent headlessly with case input.
  6. Grades response based on configured grading method:
     - `exact_match`: direct string equality.
     - `contains`: substring presence check.
     - `llm_judge`: calls secondary LLM judge agent to evaluate response quality and assign score (0.0 - 1.0) with reasoning.
  7. Calculates overall suite score (`passed_cases / total_cases` or average judge score).
  8. Updates `EvalRun` record status to `completed` with full results JSON.
- **Touches:** `backend/routers/eval_router.py`, `backend/eval_engine.py`, `backend/services/agent_runner.py`, `backend/models.py` / `backend/models_mongo.py`.
- **Inputs/Outputs:**
  - *Input:* `suite_id`, optional `agent_id`.
  - *Output:* `EvalRunResponse` with status, score, passed count, and detailed case results.
- **Side effects:** Inserts row into `eval_runs` table.

### 18. Prompt Auto-Optimizer Trace Analysis & Candidate Comparison
- **Trigger:** User clicks "Trigger Optimization" on prompt optimizer UI or APScheduler triggers weekly Monday 02:00 sweep.
- **Entry point:** `POST /optimizer/trigger` (`backend/routers/optimizer_router.py` → `trigger_optimization()`). Core pipeline: `backend/optimizer.py` → `start_optimization_sqlite()` / `start_optimization_mongo()`.
- **What it does:**
  1. Collects recent execution traces and sessions for agent (minimum 5 traces required).
  2. Sends session transcripts to LLM analysis prompt to identify failure patterns (hallucinations, tool call misuses, prompt non-compliance).
  3. Categorizes failure patterns by severity (`low`, `medium`, `high`).
  4. Generates proposed system prompt rewrite using secondary LLM call.
  5. If an `eval_suite_id` is provided, runs baseline eval against current prompt and candidate eval against proposed prompt to compare scores (e.g. 60% -> 85%).
  6. Stores result in `optimization_runs` table with status `pending_review`.
  7. User reviews proposed prompt diff in UI and clicks "Accept" (`POST /optimizer/runs/{id}/accept`) or "Reject".
  8. Upon acceptance: creates version snapshot of agent, updates agent's `system_prompt`, and optionally saves prompt into Prompt Vault.
- **Touches:** `backend/routers/optimizer_router.py`, `backend/optimizer.py`, `backend/eval_engine.py`, `backend/routers/agents_router.py`, `backend/routers/prompt_vault_router.py`.
- **Inputs/Outputs:**
  - *Input:* `agent_id`, optional `eval_suite_id`, `min_traces`.
  - *Output:* `OptimizationRunResponse` containing failure patterns, proposed prompt, rationale, and score diffs.
- **Side effects:** Writes `optimization_runs` record; updates agent prompt upon user acceptance.

### 19. Knowledge Base Creation & Document Vector Indexing
- **Trigger:** User uploads file or pastes text document into a Knowledge Base on `/knowledge/[id]`.
- **Entry point:** `POST /knowledge/{id}/documents` (`backend/routers/knowledge_router.py` → `add_kb_document()`). Vector pipeline: `backend/rag_service.py` → `index_kb_document()`.
- **What it does:**
  1. Saves document record into `kb_documents` table (`doc_type: text | file`).
  2. Parses document text (extracts plain text from PDF, DOCX, TXT, or Markdown).
  3. Chunks text into overlapping segments using recursive text splitter.
  4. Generates text embeddings using Google Vertex AI Embeddings or FAISS vectorizer.
  5. Stores document vectors in persistent vector index (`faiss` on Windows, `leann` HNSW on Linux/macOS).
  6. Marks document `indexed = True`.
  7. When agent with attached KB handles chat query, `rag_service.py` performs vector similarity search and retrieves top-k relevant context chunks.
- **Touches:** `backend/routers/knowledge_router.py`, `backend/rag_service.py`, `backend/file_storage.py`, vector store engine.
- **Inputs/Outputs:**
  - *Input:* Document text or uploaded file (`UploadFile`).
  - *Output:* `KBDocumentResponse` object.
- **Side effects:** Writes files to disk; updates vector index on disk.

### 20. MCP (Model Context Protocol) Server Binding & Discovery
- **Trigger:** User adds or tests an MCP server configuration on `/settings` or sidebar.
- **Entry point:** `POST /mcp-servers/{id}/test` (`backend/routers/mcp_servers_router.py` → `test_mcp_server()`). Core transport: `backend/mcp_client.py` → `connect_mcp_server()`.
- **What it does:**
  1. Establishes connection to MCP server using stdio transport (local child process: Docker, npx, Python) or SSE transport (remote HTTP URL).
  2. Passes environment variables and custom arguments securely.
  3. Issues MCP `tools/list` RPC request to discover exposed tool definitions.
  4. Returns list of available tools with JSON schemas.
  5. When agent has attached MCP servers, `chat()` automatically bridges MCP tools into LLM function call schemas using namespace prefixing (`mcp__{server_name}__{tool_name}`).
- **Touches:** `backend/routers/mcp_servers_router.py`, `backend/mcp_client.py`, MCP Python SDK.
- **Inputs/Outputs:**
  - *Input:* MCP server configuration (`transport: stdio | sse`, `command`, `args`, `env`, `url`).
  - *Output:* List of discovered MCP tools (`name`, `description`, `inputSchema`).
- **Side effects:** Spawns stdio child processes or opens HTTP SSE streams.

### 21. Skills Vault Management (Claude Agents)
- **Trigger:** User creates a skill on `/skills` or attaches skills to a Claude agent in agent dialog.
- **Entry point:** `POST /skills` (`backend/routers/skills_router.py` → `create_skill()`).
- **What it does:**
  1. Stores named instruction bundle in `skills` table/collection.
  2. Skill gate in frontend dialog verifies provider is Anthropic and model ID starts with `claude`.
  3. When Claude agent executes chat turn, attached skill instructions are injected into system prompt as progressive disclosure instruction blocks.
- **Touches:** `backend/routers/skills_router.py`, `backend/routers/agents_router.py`, `backend/routers/chat_router.py`.
- **Inputs/Outputs:**
  - *Input:* `SkillCreate` (`name`, `description`, `content`).
  - *Output:* `SkillResponse` object.
- **Side effects:** Inserts row into `skills` table/collection.
- **Notes/gotchas:** Restricted to Claude models by design; no dependency on Anthropic beta code-execution containers.

### 22. Prompt Vault Management
- **Trigger:** User creates, edits, or views saved system prompts on `/prompt-vault`.
- **Entry point:** `POST /prompt-vault` (`backend/routers/prompt_vault_router.py` → `create_prompt_vault_entry()`).
- **What it does:**
  1. Saves reusable prompt templates (`title`, `description`, `content`, `tags`) to database.
  2. Prompts can be selected directly when building new agents or saved directly from Prompt Auto-Optimizer runs.
- **Touches:** `backend/routers/prompt_vault_router.py`, `backend/routers/optimizer_router.py`, `backend/models.py`.
- **Inputs/Outputs:**
  - *Input:* `PromptVaultCreate` (`title`, `description`, `content`, `tags`).
  - *Output:* `PromptVaultResponse` object.
- **Side effects:** Writes row to `prompt_vault` database table/collection.

### 23. Secrets Vault & Fernet Encryption
- **Trigger:** User saves API key or credential in Secrets Vault on `/settings`.
- **Entry point:** `POST /secrets` (`backend/routers/secrets_router.py` → `create_secret()`).
- **What it does:**
  1. Encrypts sensitive secret value at rest using Fernet symmetric key (`backend/encryption.py` -> `encrypt_secret()`).
  2. Stores masked preview string (e.g. `sk-...1234`) alongside Fernet ciphertext.
  3. When configuring LLM providers, user can reference secret key ID (`secret_id`) instead of raw key string.
- **Touches:** `backend/routers/secrets_router.py`, `backend/encryption.py`, `backend/models.py`.
- **Inputs/Outputs:**
  - *Input:* `SecretCreate` (`key_name`, `secret_value`).
  - *Output:* `SecretResponse` (`id`, `key_name`, `masked_value`).
- **Side effects:** Writes encrypted secret row to `secrets` table.

### 24. File Attachment Upload & File Storage
- **Trigger:** User attaches image, PDF, or text file in chat input or knowledge base upload.
- **Entry point:** `POST /files/upload` (`backend/routers/files_router.py` → `upload_file()`).
- **What it does:**
  1. Validates file extension and size limit.
  2. Generates unique stored filename on disk via `backend/file_storage.py`.
  3. Saves file bytes to configured upload directory (`/app/data/uploads` or local directory).
  4. Returns file URL and metadata for session attachment.
- **Touches:** `backend/routers/files_router.py`, `backend/file_storage.py`.
- **Inputs/Outputs:**
  - *Input:* `UploadFile` multipart file binary.
  - *Output:* File upload response (`file_url`, `filename`, `media_type`, `size`).
- **Side effects:** Writes file binary to server disk storage.

### 25. LLM Provider Management & Connection Testing
- **Trigger:** User adds or tests an LLM provider endpoint on `/settings` or sidebar.
- **Entry point:** `POST /providers/{provider_id}/test` (`backend/routers/providers_router.py` → `test_provider()`).
- **What it does:**
  1. Retrieves provider record (`openai`, `anthropic`, `google`, `nvidia`, or `custom`).
  2. Decrypts stored provider API key using Fernet key or resolves secret reference.
  3. Instantiates provider class via `backend/llm/provider_factory.py`.
  4. Issues test completion request to provider API (e.g. "ping").
  5. Returns success or detailed connection error message.
- **Touches:** `backend/routers/providers_router.py`, `backend/llm/provider_factory.py`, `backend/encryption.py`.
- **Inputs/Outputs:**
  - *Input:* `provider_id` path parameter.
  - *Output:* JSON connection result (`{"status": "success", "message": "Connection successful"}`).
- **Side effects:** Calls external provider LLM API.

### 26. Execution Trace Retrieval
- **Trigger:** User opens Activity/Trace panel for a session or workflow run.
- **Entry point:** `GET /traces/sessions/{session_id}` (`backend/routers/traces_router.py` → `get_session_trace()`).
- **What it does:**
  1. Fetches all recorded `TraceSpan` records associated with `session_id` or `workflow_run_id`.
  2. Sanitizes trace attributes using `sanitize_trace_data()` to strip API keys, Fernet ciphertexts, and auth headers.
  3. Groups spans by execution round (LLM turn, tool call, MCP call, workflow node execution).
  4. Calculates overall latency duration and token counts.
- **Touches:** `backend/routers/traces_router.py`, `backend/crypto_utils.py`, `backend/models.py`.
- **Inputs/Outputs:**
  - *Input:* `session_id` or `run_id` path parameter.
  - *Output:* `SessionTraceResponse` or `WorkflowRunTraceResponse`.
- **Side effects:** Reads `trace_spans` database table.

### 27. Analytics Overview & Cost Metrics
- **Trigger:** User views Observability or Analytics dashboard page.
- **Entry point:** `GET /analytics/overview` (`backend/routers/analytics_router.py` → `get_overview_stats()`).
- **What it does:**
  1. Queries session messages, trace spans, and token logs across selected date range.
  2. Calculates total tokens consumed, average latency per model, tool usage counts, and estimated USD cost based on per-model pricing table.
  3. Aggregates stats into time series data for charts.
- **Touches:** `backend/routers/analytics_router.py`, `backend/models.py`.
- **Inputs/Outputs:**
  - *Input:* Date range filter query parameters (`start_date`, `end_date`).
  - *Output:* `AnalyticsOverviewResponse` object.
- **Side effects:** Reads message, session, and trace span records.

---

## Interaction Map

### Primary Flow: User Chat Turn Execution
```text
[User Browser (Next.js)]
       │
       │ 1. POST /chat (JSON / EventSource)
       ▼
[Next.js API Proxy / rewrite]
       │
       │ 2. Forward request with JWT header
       ▼
[FastAPI chat_router.py :: chat()]
       │
       ├─► 3. Decrypt payload / Verify JWT token (auth.py)
       ├─► 4. Load Agent & LLM Provider config (providers_router.py)
       ├─► 5. Retrieve Long-Term Memories (memory_router.py)
       ├─► 6. Fetch Vector RAG Context (rag_service.py)
       │
       ▼
[LLM Provider Factory (llm/provider_factory.py)]
       │
       │ 7. Construct LLM instance (OpenAI / Anthropic / Gemini / NVIDIA)
       ▼
[Iterative Tool Execution Loop (up to 10 rounds)]
       │
       ├─► Native Builtin Tool (builtin_tools.py)
       ├─► Docker Sandbox Tool (sandbox_tools.py)
       ├─► MCP Tool Call (mcp_client.py -> Stdio/SSE)
       ├─► HITL Approval Pause (_hitl_events asyncio.Event)
       └─► Tool Proposal Pause (_tool_proposal_events asyncio.Event)
       │
       ▼
[SSE Stream Generator (sse-starlette)]
       │
       │ 8. Yield content deltas, tool calls, reasoning steps, artifacts
       ▼
[Frontend Zustand Store (playground-store.ts)]
       │
       │ 9. Update React state & render markdown / code / artifacts / HITL cards
       ▼
[User UI Display]
```

### Headless Channel Execution Flow: WhatsApp Integration
```text
[WhatsApp User Phone]
       │
       │ 1. Sends text or voice note
       ▼
[Node.js wa-bridge sidecar (Baileys Web Socket)]
       │
       │ 2. POST /wa/incoming
       ▼
[FastAPI whatsapp_router.py -> whatsapp_service.py]
       │
       ├─► 3. Check contact whitelist (allowed_jids)
       ├─► 4. If voice note: STT transcribe (stt_service.py / Groq Whisper)
       ├─► 5. Map (channel_id, wa_chat_id) -> Session
       │
       ▼
[agent_runner.py :: run_agent_headless()]
       │
       │ 6. Run full agent tool turn (No SSE stream)
       ▼
[TTS Pipeline (tts_service.py)] (if voice reply enabled)
       │
       │ 7. Synthesize audio: Qwen3-TTS (GPU) / Pocket TTS / Kokoro
       │ 8. Convert to OGG Opus via ffmpeg
       ▼
[POST http://localhost:3200/api/send (wa-bridge)]
       │
       │ 9. Send WhatsApp message back to user
       ▼
[WhatsApp User Phone]
```

---

## Naming & Config Notes

| Internal Name / Key | User-Facing UI Label | Where Used | Notes & Gotchas |
|---------------------|----------------------|------------|-----------------|
| `DATABASE_TYPE` | Database Backend | `backend/config.py` | Must be `sqlite` or `mongo`. Dictates whether SQLAlchemy or Motor async driver is used. |
| `ENCRYPTION_KEY` | Public Encryption Key | `backend/crypto_utils.py`, `frontend/.env.local` | AES key for transit payload encryption. **MUST match** `NEXT_PUBLIC_ENCRYPTION_KEY` exactly. |
| `PROVIDER_KEY_SECRET` | Provider Key Encryption Secret | `backend/encryption.py` | Valid 32-byte Fernet key (`cryptography.fernet`) used to encrypt provider API keys at rest in DB. |
| `hitl_confirmation_tools_json` | Require Approval For | Agent Edit Dialog / HITL | List of tool names requiring explicit human approval per agent, independent of tool-level flags. |
| `allow_tool_creation` | Allow Tool Creation | Agent Edit Dialog | Toggle enabling agent to call `create_tool` virtual function and propose new dynamic tools mid-conversation. |
| `sandbox_enabled` | Docker Sandbox | Agent/Team Edit Dialog | Launches `obsidian-webdev-base` Docker container and injects 9 `sandbox_*` tools into agent toolset. |
| `tts_backend` | TTS Engine | WhatsApp Channel Settings | Values: `auto` (Qwen3-TTS on GPU, Pocket TTS on CPU), `qwen` (forces Qwen3-TTS), `classic` (forces Pocket TTS/Kokoro). |
| `aip_` / `AgentAPIConfig` | External Agent API | `/agent-api/*` router | External API client keys and application configurations for embedding agents into external systems. |
| `aip_key_...` | API Client Secret | API Client Settings | Encrypted API client secret pairs for headless REST authentication (`X-API-Key`, `X-API-Secret`). |

---

## Open Questions / Needs Verification

1. **`backend/llm/nvidia.py` vs `backend/llm/nvidia_provider.py`**:
   - *Observation:* Both `nvidia.py` and `nvidia_provider.py` exist in `backend/llm/`. `provider_factory.py` imports `NvidiaProvider` from `nvidia_provider.py`.
   - *Needs Verification:* Confirm if `backend/llm/nvidia.py` is legacy/unused code or reserved for a specific legacy import path.
2. **FAISS vs Leann Vector Store Platform Gating**:
   - *Observation:* `rag_service.py` uses `faiss` on Windows and `leann` on Linux/macOS.
   - *Needs Verification:* Verify whether deployment environments with custom C++ builds can override vector engine selection via environment variables.
3. **In-Memory Event Map Persistence across Restarts**:
   - *Observation:* `_hitl_events`, `_tool_proposal_events`, and `workflow_hitl_events` are held in module-level Python dicts.
   - *Needs Verification:* If a server restarts while an approval is pending, the database records are auto-denied on startup by `main.py` lifespan. Future migration to Microsoft Agent Framework should evaluate moving event signaling to Redis or a shared pub/sub channel for multi-instance horizontal scaling.
