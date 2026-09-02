# Codebase Documentation — Obsidian AI
Generated: 2026-09-02

## Overview

Obsidian AI is an open-source, full-stack AI agent management and orchestration platform that enables users to build, deploy, and manage AI agents, multi-agent teams, and workflow pipelines. The platform features a Next.js 16 (React 19) frontend client operating with NextAuth v5 and Zustand state management, coupled to an asynchronous FastAPI (Python 3.12) backend server. Data persistence is powered by a dual database architecture supporting SQLite (via SQLAlchemy ORM) and MongoDB (via Motor async driver). External channel connectivity is provided by a Node.js WhatsApp bridge sidecar (`wa-bridge`), with isolated code execution provided by Docker sandbox containers. The system start entry points are `backend/main.py` for the backend server, `frontend/app/layout.tsx` for the web client, and `wa-bridge/index.js` for the WhatsApp socket service.

---

## Directory Map

```text
obsidian-ai/
├── package.json                        # Root script orchestrator (runs frontend + backend)
├── doc/                                # System documentation
│   └── codebase-documentation-2026-09-02.md
├── backend/                            # Python FastAPI Application
│   ├── main.py                         # FastAPI startup entry point, middleware & lifespan
│   ├── config.py                       # Global database and environment configuration
│   ├── database.py                     # SQLAlchemy SQLite engine setup and session factory
│   ├── database_mongo.py               # Motor async MongoDB driver connection manager
│   ├── models.py                       # SQLAlchemy ORM database models
│   ├── models_mongo.py                 # MongoDB collection helpers and Pydantic schemas
│   ├── schemas.py                      # Pydantic request/response validation schemas
│   ├── auth.py                         # JWT token creation, verification, and password hashing
│   ├── rate_limiter.py                 # SlowAPI rate limiting configuration
│   ├── crypto_utils.py                 # Client-server payload AES encryption/decryption
│   ├── encryption.py                   # Fernet symmetric encryption for secrets at rest
│   ├── dag_executor.py                 # Asynchronous DAG topological workflow engine
│   ├── eval_engine.py                  # Evaluation suite judge engine and background runner
│   ├── optimizer.py                    # Prompt auto-optimizer trace analysis & generator
│   ├── mcp_client.py                   # Model Context Protocol stdio/SSE client manager
│   ├── rag_service.py                  # Document chunking, FAISS/Leann vector store manager
│   ├── scheduler.py                    # APScheduler instance setup & cron helpers
│   ├── scheduler_executor.py           # Background cron workflow execution engine
│   ├── async_job_poller.py             # Background polling engine for asynchronous jobs
│   ├── async_job_tools.py              # Tool wrappers for long-running async tasks
│   ├── builtin_tools.py                # Pre-built agent tools (weather, web search, calculator)
│   ├── sandbox_tools.py                # Isolated Docker sandbox container tools
│   ├── team_delegation_tools.py        # Inter-agent communication tools for teams
│   ├── llm/                            # LLM Provider abstraction layer
│   │   ├── base.py                     # Abstract Base Provider interface
│   │   ├── provider_factory.py         # Dynamic LLM provider resolver
│   │   ├── openai_provider.py         # OpenAI & OpenAI-compatible provider
│   │   ├── anthropic_provider.py      # Anthropic Claude provider
│   │   ├── google_provider.py          # Google Gemini provider
│   │   └── ollama_provider.py         # Local Ollama provider
│   ├── services/                       # Standalone background services
│   │   ├── whatsapp_service.py         # Inbound WhatsApp message processor & agent runner
│   │   └── tts_service.py              # Multi-engine TTS pipeline (Qwen3/Pocket TTS/Kokoro)
│   └── routers/                        # FastAPI REST API endpoint routers
│       ├── admin_router.py             # Admin RBAC and user management
│       ├── agents_router.py            # Agent CRUD, versioning, export/import, sandbox
│       ├── analytics_router.py         # Usage metrics and token cost calculations
│       ├── auth_router.py              # Login, registration, 2FA, API credentials
│       ├── chat_router.py              # Real-time streaming chat & HITL approvals
│       ├── dashboard_router.py         # High-level system statistics
│       ├── eval_router.py              # Eval suite CRUD and execution management
│       ├── files_router.py             # Chat file attachments and storage
│       ├── knowledge_router.py         # Knowledge bases and document RAG indexing
│       ├── mcp_servers_router.py       # MCP server configurations and tool discovery
│       ├── memory_router.py            # Agent long-term memory management
│       ├── optimizer_router.py         # Prompt auto-optimizer control and review
│       ├── prompt_vault_router.py      # System prompt vault management
│       ├── providers_router.py         # LLM provider configuration and model listing
│       ├── sandbox_router.py           # Docker container control endpoints
│       ├── schedule_router.py          # Workflow cron schedule management
│       ├── secrets_router.py           # Encrypted secrets vault
│       ├── sessions_router.py          # Chat session history and message retrieval
│       ├── settings_router.py          # Application-wide dynamic configuration
│       ├── skills_router.py            # Claude agent instruction skill bundles
│       ├── teams_router.py             # Multi-agent team configuration and sandbox
│       ├── tools_router.py             # Built-in and custom tool management
│       ├── traces_router.py            # Execution span trace retrieval
│       ├── user_router.py              # Current user profile and settings
│       ├── versions_router.py          # Agent config version snapshots and rollback
│       ├── whatsapp_router.py          # WhatsApp channel configuration & pairing
│       ├── workflow_runs_router.py     # Workflow execution state and logs
│       └── workflows_router.py         # Visual workflow canvas definitions
├── frontend/                           # Next.js 16 Web Application
│   ├── app/                            # App Router page hierarchy
│   │   ├── (authenticated)/            # Protected route group with AppShell navigation
│   │   │   ├── admin/page.tsx          # System administration control panel
│   │   │   ├── channels/page.tsx       # WhatsApp channel management page
│   │   │   ├── evals/page.tsx          # Regression evaluation harness UI
│   │   │   ├── home/page.tsx           # Dashboard home
│   │   │   ├── knowledge/page.tsx      # RAG Knowledge base management
│   │   │   ├── observability/page.tsx  # Execution traces and analytics dashboard
│   │   │   ├── playground/page.tsx     # Unified chat, team, and workflow canvas playground
│   │   │   ├── prompts/page.tsx        # System Prompt Vault UI
│   │   │   ├── secrets/page.tsx        # Encrypted Secrets Vault UI
│   │   │   ├── sessions/page.tsx       # Conversation history browser
│   │   │   ├── settings/page.tsx       # User settings and 2FA configuration
│   │   │   ├── skills/page.tsx         # Claude Agent Skills Vault UI
│   │   │   └── user/page.tsx           # User account profile
│   │   ├── login/page.tsx              # Authentication login screen
│   │   ├── register/page.tsx           # User registration screen
│   │   ├── layout.tsx                  # Root Next.js layout and global providers
│   │   └── providers.tsx               # Client-side Zustand and Auth providers
│   ├── components/                     # React UI components
│   │   ├── ai-elements/                # Chat stream rendering (artifacts, CoT, HITL cards)
│   │   ├── dialogs/                    # Modal forms (workflows, tools, schedules, MCP)
│   │   ├── notification/               # Global header alerts (HITL pending, Async jobs)
│   │   ├── playground/                 # Chat interface, sidebar, and DAG workflow canvas
│   │   └── ui/                         # Primitive components (Radix UI / Tailwind CSS)
│   ├── lib/                            # Frontend utility modules
│   │   ├── api-client.ts               # Authenticated fetch wrapper with token injection
│   │   ├── crypto.ts                   # Client-side AES payload encryption helper
│   │   └── stream.ts                   # Server-Sent Events (SSE) reader stream handler
│   └── stores/                         # Zustand state stores
│       ├── playground-store.ts         # Active agent, chat sessions, artifacts, workflow state
│       ├── admin-store.ts              # System administration state
│       ├── dashboard-store.ts          # Home dashboard metrics state
│       └── permissions-store.ts        # User role and permission state
└── wa-bridge/                          # WhatsApp Web Node.js Sidecar
    ├── index.js                        # Baileys WebSocket bridge server
    └── package.json                    # Node.js dependencies (@whiskeysockets/baileys)
```

---

## Functionality Reference

### 1. User Authentication & Session Verification
- **Trigger:** Web user submits login/registration forms or accesses protected routes.
- **Entry point:** `backend/routers/auth_router.py` → `login()`, `register_user()`, `verify_totp_login()`
- **What it does:**
  1. Validates incoming user credentials (email/password) using bcrypt password hashing.
  2. If 2FA TOTP is enabled on the user account, returns a temporary 2FA ticket requiring verification.
  3. Validates TOTP code via `pyotp` if requested.
  4. Issues an HS256 JWT access token encoding the `user_id` and role permissions.
  5. NextAuth v5 client session (`frontend/auth.ts`) stores the token and passes it as `Authorization: Bearer <token>` in subsequent client requests.
- **Touches:** `backend/models.py` (`User`), `backend/auth.py`, `frontend/app/login/page.tsx`
- **Inputs/Outputs:**
  - *Input:* `UserLogin` or `UserCreate` JSON schema.
  - *Output:* JWT Access Token string and user profile metadata.
- **Side effects:** Writes new user records to `users` database table; updates `last_login` timestamp.
- **Notes/gotchas:** Client request payloads are AES-encrypted when `NEXT_PUBLIC_ENCRYPTION_KEY` is set; `crypto_utils.py` decrypts incoming request bodies before route processing.

---

### 2. Real-Time Chat & Tool-Execution Loop
- **Trigger:** User sends a chat message in the Playground interface.
- **Entry point:** `backend/routers/chat_router.py` → `chat_endpoint()`
- **What it does:**
  1. Authenticates user and retrieves active agent, team, or workflow entity.
  2. Creates or fetches the `Session` record and appends the user message to `messages`.
  3. Injects long-term agent memories (`agent_memories` table) and attached Claude skills into system prompt.
  4. Binds attached tools, sandbox tools, and discovered MCP tools.
  5. Invokes LLM provider via `llm/provider_factory.py`.
  6. Streams output tokens back to the frontend via Server-Sent Events (SSE).
  7. If the model invokes a tool:
     - Checks if tool requires Human-In-The-Loop (HITL) approval (via tool flag or agent override).
     - If HITL is required, pauses streaming, creates `HITLApproval` record, and streams `hitl_approval_required` event.
     - Upon execution, runs tool (Python function, HTTP REST call, Sandbox bash/code, or MCP client), records execution span in `trace_spans`, and loops up to 10 iterations.
  8. Parses `<artifact>` XML tags from output stream and emits `artifact` events for side-panel preview.
  9. Fires an async background task to perform LLM session reflection for long-term memory extraction.
- **Touches:** `backend/routers/chat_router.py`, `backend/llm/provider_factory.py`, `backend/mcp_client.py`, `backend/sandbox_tools.py`, `backend/rag_service.py`, `frontend/lib/stream.ts`, `frontend/stores/playground-store.ts`
- **Inputs/Outputs:**
  - *Input:* `ChatRequest` JSON payload containing `session_id`, `agent_id`/`team_id`, `message`, `files`.
  - *Output:* Server-Sent Event stream (`text_delta`, `tool_call`, `hitl_approval_required`, `artifact`, `done`).
- **Side effects:** Inserts user and assistant messages into database; writes trace spans; updates session token usage counters.
- **Notes/gotchas:** Maximum tool iterations hardcoded to 10 per request to prevent infinite model loops.

---

### 3. Human-In-The-Loop (HITL) Approval Flow
- **Trigger:** Model calls a sensitive tool marked for approval, or user clicks Approve/Deny on approval card.
- **Entry point:** `backend/routers/chat_router.py` → `approve_hitl()`, `get_pending_hitl_approvals()`
- **What it does:**
  1. When tool call is requested, server creates a `pending` row in `hitl_approvals` table and blocks LLM loop on an `asyncio.Event`.
  2. Approval card renders in active chat message and in global header badge (`frontend/components/notifications/hitl-global-badge.tsx`).
  3. User clicks Approve or Deny. `POST /chat/hitl/{approval_id}/respond` sets approval status to `approved` or `denied`.
  4. Server unblocks `asyncio.Event` and resumes agent execution loop.
  5. Unanswered approvals auto-deny after 10 minutes or upon backend server restart.
- **Touches:** `backend/routers/chat_router.py`, `backend/models.py` (`HITLApproval`), `frontend/components/ai-elements/hitl-approval.tsx`
- **Inputs/Outputs:**
  - *Input:* `approval_id` path param, `approved` boolean body.
  - *Output:* JSON success confirmation.
- **Side effects:** Updates `hitl_approvals` record status; resumes or aborts model tool execution.

---

### 4. Visual Workflow Automation Engine (DAG & Pipelines)
- **Trigger:** User runs a visual workflow manually or a workflow cron schedule fires.
- **Entry point:** `backend/routers/workflow_runs_router.py` → `run_workflow_endpoint()`, `backend/dag_executor.py` → `execute_dag_workflow()`
- **What it does:**
  1. Loads visual canvas definition (nodes and directed edges) from `Workflow`.
  2. Validates topology using Depth-First Search (DFS) cycle detection to ensure a valid Directed Acyclic Graph (DAG).
  3. Constructs topological dependency graph.
  4. `dag_executor.py` runs independent parallel nodes concurrently using `asyncio.gather()`.
  5. Passes outputs of parent nodes as context variables into child step prompts.
  6. Emits live node execution status events (`node_start`, `node_complete`, `node_failed`) via SSE.
  7. Persists overall run execution status and per-node step output to `workflow_runs` table.
- **Touches:** `backend/dag_executor.py`, `backend/routers/workflows_router.py`, `backend/routers/workflow_runs_router.py`, `frontend/components/playground/workflow-steps-view.tsx`
- **Inputs/Outputs:**
  - *Input:* `workflow_id`, initial `input_text`.
  - *Output:* SSE stream of workflow execution logs and step results; `WorkflowRun` record.
- **Side effects:** Creates `WorkflowRun` entry and execution `trace_spans`.

---

### 5. Scheduled Cron Workflow Execution
- **Trigger:** APScheduler background job trigger based on cron schedule expression.
- **Entry point:** `backend/scheduler_executor.py` → `run_scheduled_workflow_sqlite()`, `run_scheduled_workflow_mongo()`
- **What it does:**
  1. Cron trigger fires based on standard 5-field expression in `workflow_schedules`.
  2. Verifies schedule `is_active` state and acquires lock.
  3. Spawns headless workflow DAG execution passing pre-configured `input_text`.
  4. Saves execution result in `workflow_runs`.
  5. Updates `last_run_at` and `next_run_at` timestamps on schedule record.
- **Touches:** `backend/scheduler.py`, `backend/scheduler_executor.py`, `backend/routers/schedule_router.py`
- **Inputs/Outputs:**
  - *Input:* `schedule_id`.
  - *Output:* Generated `WorkflowRun` database record.
- **Side effects:** Updates `workflow_schedules` timing columns; executes workflow agents headlessly.

---

### 6. WhatsApp Channel Integration & Voice Sidecar
- **Trigger:** Inbound WhatsApp message received by Baileys WebSocket sidecar (`wa-bridge`).
- **Entry point:** `wa-bridge/index.js` → `backend/services/whatsapp_service.py` → `handle_incoming_whatsapp_message()`
- **What it does:**
  1. `wa-bridge` captures inbound WhatsApp Web socket message and posts JSON to `POST /wa/incoming`.
  2. Backend matches WhatsApp sender JID to persistent session in `wa_contact_sessions` table.
  3. If message contains audio voice note, transcribes audio locally using `faster-whisper` CPU model.
  4. Executes assigned channel agent headlessly through agent completion loop.
  5. If channel `voice_reply_enabled` is True:
     - Directs response text to `backend/services/tts_service.py`.
     - Synthesizes audio reply using selected engine: `Qwen3-TTS` (CUDA GPU with voice clone sample support) → `Pocket TTS` (CPU) → `Kokoro` (CPU fallback).
     - Converts output audio to OGG Opus via `ffmpeg`.
     - Sends audio payload back to `wa-bridge` for WhatsApp dispatch.
  6. Posts text or voice message response back to contact JID via `wa-bridge` API.
- **Touches:** `wa-bridge/index.js`, `backend/routers/whatsapp_router.py`, `backend/services/whatsapp_service.py`, `backend/services/tts_service.py`
- **Inputs/Outputs:**
  - *Input:* WhatsApp message object (text or audio buffer) from `wa-bridge`.
  - *Output:* Outbound WhatsApp message response delivered via Baileys socket.
- **Side effects:** Updates channel session message history; generates audio files in cache directory.

---

### 7. Docker Sandbox Container Execution
- **Trigger:** User starts sandbox for agent/team, or agent executes a sandbox built-in tool.
- **Entry point:** `backend/routers/sandbox_router.py`, `backend/sandbox_tools.py`
- **What it does:**
  1. `POST /agents/{id}/sandbox/start` provisions isolated Docker container running `obsidian-webdev-base:latest` (512MB RAM cap, 1 CPU limit).
  2. Binds container tools (`sandbox_bash`, `sandbox_python`, `sandbox_node`, `sandbox_read`, `sandbox_write`, `sandbox_ls`, `sandbox_glob`, `sandbox_grep`, `sandbox_delete`) into agent context.
  3. When tool executes, runs command inside container using Docker SDK Python client (`docker.from_env()`).
  4. System prompt instructs agent to read generated files using `sandbox_read` and format as `<artifact>` tags for instant client rendering.
- **Touches:** `backend/routers/sandbox_router.py`, `backend/sandbox_tools.py`, `backend/Dockerfile.base`
- **Inputs/Outputs:**
  - *Input:* Tool arguments (command string, file path, script body).
  - *Output:* Command standard output/error, file contents, container execution status.
- **Side effects:** Starts, modifies, or stops Docker containers on host system.

---

### 8. Knowledge Base & RAG Indexing Service
- **Trigger:** User uploads document or text block to a Knowledge Base.
- **Entry point:** `backend/routers/knowledge_router.py` → `add_kb_document()`
- **What it does:**
  1. Parses raw file (PDF, DOCX, TXT, Markdown) or direct text payload.
  2. `rag_service.py` chunks text into overlapping passages (1000 characters with 150 overlap).
  3. Embeds chunks into local vector store using FAISS (or Leann HNSW on Linux/macOS).
  4. Saves document record and vector index file on local disk under storage directory.
  5. When agent runs chat with attached Knowledge Base, queries vector store using user message embedding and injects top-K relevant chunks into prompt context.
- **Touches:** `backend/routers/knowledge_router.py`, `backend/rag_service.py`, `frontend/app/(authenticated)/knowledge/[id]/page.tsx`
- **Inputs/Outputs:**
  - *Input:* File upload or text content string.
  - *Output:* Indexed `KBDocument` record and created FAISS vector index files.
- **Side effects:** Writes index files to disk (`backend/data/rag_indices/`).

---

### 9. Prompt Auto-Optimizer & Eval Harness Validation
- **Trigger:** User triggers prompt optimization manually or weekly APScheduler cron fires.
- **Entry point:** `backend/routers/optimizer_router.py` → `trigger_optimization()`, `backend/optimizer.py`
- **What it does:**
  1. Fetches recent conversation trace sessions for target agent (requires minimum 5 sessions).
  2. Passes execution logs to analysis LLM to identify recurring failure patterns and severity.
  3. Generates proposed system prompt addressing identified patterns.
  4. If `eval_suite_id` is provided, runs current baseline prompt and proposed prompt through evaluation suite test cases using `eval_engine.py`.
  5. Evaluates test cases via exact match, substring, or LLM judge scoring.
  6. Displays proposed prompt diff and before/after score metrics to user.
  7. User can Accept (applies prompt and creates agent version snapshot), Reject, or Save to Prompt Vault.
- **Touches:** `backend/optimizer.py`, `backend/eval_engine.py`, `backend/routers/optimizer_router.py`, `backend/routers/eval_router.py`
- **Inputs/Outputs:**
  - *Input:* `agent_id`, optional `eval_suite_id`.
  - *Output:* `OptimizationRun` record containing failure patterns, proposed prompt diff, and score metrics.
- **Side effects:** Updates agent system prompt on acceptance; creates version snapshot in `agent_versions`.

---

### 10. Long-Term Agent Memory Reflection
- **Trigger:** First chat message of a new session on an agent with `memory_enabled=True`.
- **Entry point:** `backend/routers/chat_router.py` → `_process_session_memory_background()`, `backend/routers/memory_router.py`
- **What it does:**
  1. Runs as a non-blocking background task so response speed is unimpeded.
  2. Examines previous completed session messages between specific user and agent.
  3. Uses LLM reflection call to distill durable user facts into 4 categories (`preference`, `context`, `decision`, `correction`).
  4. Upserts extracted facts into `agent_memories` table (keyed by fact topic to overwrite stale information).
  5. Caps total memory entries per agent/user pair to 50, automatically evicting oldest low-confidence memories.
  6. Injects active memories into agent system prompt on subsequent sessions.
- **Touches:** `backend/routers/chat_router.py`, `backend/routers/memory_router.py`, `backend/models.py` (`AgentMemory`)
- **Inputs/Outputs:**
  - *Input:* `session_id`, `agent_id`, `user_id`.
  - *Output:* Extracted `AgentMemory` database records.
- **Side effects:** Inserts or updates `agent_memories` table; sets `memory_processed=True` on session.

---

### 11. Dynamic Tool Creation & Approval
- **Trigger:** Agent with `allow_tool_creation=True` emits a `propose_tool` tool call in chat.
- **Entry point:** `backend/routers/chat_router.py` → `_handle_tool_proposals()`, `backend/routers/tools_router.py` → `respond_tool_proposal()`
- **What it does:**
  1. Agent proposes a new HTTP or pure-Python tool mid-conversation.
  2. Server captures proposal, creates `pending` record in `tool_proposals`, and renders proposal review card inline in chat.
  3. User reviews generated Python code / parameter schema and clicks Approve or Reject.
  4. If approved:
     - Creates new permanent row in `tool_definitions` table.
     - Makes tool immediately executable in current chat session without page refresh.
  5. Unreviewed proposals auto-reject after 10 minutes timeout.
- **Touches:** `backend/routers/chat_router.py`, `backend/routers/tools_router.py`, `frontend/components/ai-elements/tool-proposal-card.tsx`
- **Inputs/Outputs:**
  - *Input:* Tool name, description, parameters JSON schema, code handler string.
  - *Output:* Created `ToolDefinition` record.
- **Side effects:** Writes to `tool_proposals` and `tool_definitions` database tables.

---

### 12. Agent Configuration Versioning & Rollback
- **Trigger:** User updates agent settings via `PUT /agents/{id}`.
- **Entry point:** `backend/routers/agents_router.py` → `update_agent()`, `backend/routers/versions_router.py` → `rollback_agent_version()`
- **What it does:**
  1. Before applying updates to `Agent`, serializes current configuration into JSON snapshot.
  2. Increments agent version counter and creates `AgentVersion` record in database.
  3. User can inspect side-by-side diffs of past versions in agent edit modal.
  4. On rollback trigger (`POST /versions/agents/{id}/{vid}/rollback`):
     - Restores historical configuration snapshot to `Agent`.
     - Automatically creates a new version snapshot for the rollback action itself.
- **Touches:** `backend/routers/agents_router.py`, `backend/routers/versions_router.py`, `backend/models.py` (`AgentVersion`)
- **Inputs/Outputs:**
  - *Input:* `agent_id`, `version_id`.
  - *Output:* Updated `Agent` record and created `AgentVersion` record.
- **Side effects:** Updates `agents` table; inserts snapshot into `agent_versions`.

---

## Interaction Map

```text
                                 [ User Browser / Client ]
                                             │
                                   HTTP / SSE Stream (Port 3000)
                                             │
                                             ▼
                                   [ Next.js Frontend ]
                                  (NextAuth v5 + Zustand)
                                             │
                                     Proxy Rewrite /api/*
                                             │
                                             ▼
                                  [ FastAPI Backend Engine ]
                                        (Port 8000)
                                             │
      ┌──────────────────┬───────────────────┼───────────────────┬──────────────────┐
      │                  │                   │                   │                  │
      ▼                  ▼                   ▼                   ▼                  ▼
[LLM Factory]      [Database Layer]     [RAG Engine]        [Sandbox Engine]    [APScheduler]
 (OpenAI,           (SQLite / Mongo)     (FAISS Vector       (Docker Host        (Cron Jobs &
 Anthropic,                              Indices)            Containers)         Background Tasks)
 Gemini, Ollama)         ▲
                         │ Local HTTP
                         ▼
                [wa-bridge Sidecar] (Port 3200)
                         │
                 WhatsApp WebSocket
                         │
                         ▼
                 [WhatsApp Network]
```

### Data Flow Summaries
1. **Chat Submission Flow:**
   `User submit` → `Playground UI` → `POST /chat` → `FastAPI Router` → `Fetch Agent & Context` → `Inject Memory/Skills` → `LLM Provider Call` → `SSE Token Stream` → `Tool Execution Loop` → `Artifact Tag Extractor` → `UI Re-render`.
2. **WhatsApp Inbound Message Flow:**
   `WhatsApp Contact` → `Baileys Socket` → `wa-bridge` → `POST /wa/incoming` → `FastAPI whatsapp_service` → `STT Transcription (if audio)` → `Headless Agent Run` → `TTS Synthesis (if enabled)` → `wa-bridge API` → `Outbound WhatsApp Message`.
3. **Workflow Execution Flow:**
   `Workflow Trigger` → `DAG Validation (DFS)` → `Topological Task Queue` → `Async Concurrent Node Execution` → `Parent Output -> Child Context Injection` → `Status Event Stream` → `Workflow Run Record`.

---

## Naming & Config Notes

| Context / Location | Internal Code Identifier | User-Facing Label | Gotchas / Load-Bearing Notes |
| :--- | :--- | :--- | :--- |
| LLM Provider Config | `secret_id` | Stored Secret Reference | References Fernet encrypted secret in `user_secrets`; if deleted, provider fails silently until key updated. |
| Agent Builder | `hitl_confirmation_tools_json` | "Require Approval For" | Agent-level array overrides tool-level `requires_confirmation` flags; match must be exact tool name string. |
| WhatsApp Integration | `allowed_jids` | Contact Whitelist | Expects full WhatsApp JID format (e.g. `1234567890@s.whatsapp.net`); comma-separated strings. |
| Skills Vault | `skill_ids_json` | Claude Skills | Selector only activates in UI when LLM provider is `anthropic` AND model ID starts with `claude`. |
| Docker Sandbox | `obsidian-webdev-base` | Sandbox Container Image | Docker image must be pre-built on host (`docker build -f backend/Dockerfile.base -t obsidian-webdev-base:latest backend/`). |
| Database Engine | `DATABASE_TYPE` | `sqlite` or `mongo` | Environment variable dictates database ORM routing; defaults to `sqlite` if unset. |
| Payload Encryption | `ENCRYPTION_KEY` | Public Encryption Key | AES payload key must match exactly between frontend `NEXT_PUBLIC_ENCRYPTION_KEY` and backend `ENCRYPTION_KEY`. |
| Database Migration | `ux_tool_definitions_user_name_active` | Unique Active Tool Constraint | Partial SQLite index on `(user_id, name)` where `is_active = 1` enforces unique tool names for active tools. |

---

## Open Questions / Needs Verification

1. **Legacy Auth Route Endpoints:**
   `backend/routers/auth_router.py` contains `POST /auth/legacy-token` alongside standard `POST /auth/login`. Verify if `legacy-token` is required for backwards compatibility with third-party extensions or can be safely pruned.
2. **Context Window Fallback Thresholds:**
   `backend/routers/chat_router.py` uses an 80% context window threshold for automatic conversation compaction. Confirm whether non-standard custom OpenAI-compatible endpoints properly expose maximum context limits or revert to the safe default cap (4,096 tokens).
3. **SoX Audio Processing Utility:**
   Pocket TTS audio fallback optionally utilizes the system `sox` package. Needs human verification whether `sox` must be installed on non-Debian host environments or if pure-Python fallback handles standard sample rates without error.
