# Codebase Documentation — Obsidian AI
Generated: 2026-09-02

## Overview

Obsidian AI is an open-source AI agent management and orchestration platform that enables users to build, deploy, and execute multi-agent teams and automated visual workflows. The architecture follows a client-server model with a Next.js 16 (React 19) frontend, a FastAPI (Python 3.12) backend, and a Node.js Baileys sidecar (`wa-bridge`) for native WhatsApp channel integration. Execution starts at `backend/main.py` for API services and background schedulers, `frontend/auth.ts` / `frontend/app/layout.tsx` for client-side routing and session management, and `wa-bridge/index.js` for WhatsApp Web socket management. The platform features dual-database runtime support (SQLite via SQLAlchemy ORM or MongoDB via Motor ODM), end-to-end AES payload encryption, Fernet secret storage at rest, visual DAG execution with parallel Topological Sort, Human-in-the-Loop (HITL) approval gates, MCP protocol client integration, RAG vector indexing via FAISS, long-term memory reflection, and an isolated Docker execution sandbox.

---

## Directory Map

```text
obsidian-ai/
├── package.json                         # Monorepo root concurrency runner ("npm run dev")
├── docker-compose.yml                   # Docker Compose deployment setup with Nginx reverse proxy
├── backend/                             # FastAPI Python backend service
│   ├── main.py                          # FastAPI entrypoint, lifespan events, database migrations, APScheduler setup
│   ├── config.py                        # Environment configuration and dual-database selector
│   ├── database.py                      # SQLAlchemy engine and session factory (SQLite)
│   ├── database_mongo.py                # Motor async MongoDB client connection and helper
│   ├── models.py                        # SQLAlchemy ORM models
│   ├── models_mongo.py                  # Motor ODM collection wrappers and index definitions
│   ├── schemas.py                       # Pydantic request/response validation schemas
│   ├── auth.py                          # JWT token issuance, password hashing, TOTP 2FA, API client verification
│   ├── crypto_utils.py                  # Client-backend AES-256-CBC request/response payload encryption
│   ├── encryption.py                    # Fernet symmetric encryption for secrets at rest
│   ├── rate_limiter.py                  # SlowAPI rate limiting middleware
│   ├── mcp_client.py                    # Model Context Protocol stdio/SSE transport and tool discovery
│   ├── rag_service.py                   # Document chunking and FAISS vector similarity search
│   ├── file_storage.py                  # File attachment upload/download management
│   ├── scheduler.py                     # APScheduler global instance and cron triggers
│   ├── scheduler_executor.py            # Headless background execution engine for scheduled workflows
│   ├── dag_executor.py                  # Visual DAG topological sort executor with cycle detection
│   ├── eval_engine.py                   # Eval test suite grading engine (exact match, contains, LLM judge)
│   ├── optimizer.py                     # System prompt auto-optimizer and failure pattern extractor
│   ├── sandbox_tools.py                 # Docker container creation and tool injection (`sandbox_bash`, `sandbox_python`, etc.)
│   ├── llm/                             # Multi-provider LLM integrations
│   │   ├── base.py                      # Abstract BaseLLMProvider interface
│   │   ├── provider_factory.py          # Provider factory instantiator
│   │   ├── openai_provider.py           # OpenAI, OpenRouter, and custom OpenAI-compatible handler
│   │   ├── anthropic_provider.py        # Anthropic Claude provider handler
│   │   ├── google_provider.py           # Google Gemini provider handler
│   │   └── ollama_provider.py           # Local Ollama provider handler
│   ├── services/                        # Core backend business logic services
│   │   ├── agent_runner.py              # Real-time agent chat loop, tool execution, HITL eventing, memory reflection
│   │   ├── whatsapp_service.py          # WhatsApp message handler, session mapping, voice response dispatch
│   │   ├── stt_service.py               # Groq Whisper API audio transcription
│   │   └── tts_service.py               # TTS synthesis pipeline (Qwen3-TTS / Pocket TTS / Kokoro)
│   └── routers/                         # FastAPI REST and SSE route handlers
│       ├── auth_router.py               # Authentication, registration, 2FA, API clients
│       ├── user_router.py               # User profile settings
│       ├── providers_router.py          # LLM provider CRUD and connection testing
│       ├── secrets_router.py            # Encrypted secrets vault CRUD
│       ├── agents_router.py             # Agent CRUD, export/import, sandbox controls
│       ├── versions_router.py           # Agent configuration versioning and rollbacks
│       ├── teams_router.py              # Multi-agent team CRUD and sandbox controls
│       ├── workflows_router.py          # Workflow CRUD, DAG validation, manual execution
│       ├── workflow_runs_router.py     # Workflow execution history and SSE streaming
│       ├── schedule_router.py           # Cron schedule CRUD and APScheduler synchronization
│       ├── chat_router.py             # Real-time SSE chat streaming, HITL approvals, tool proposals
│       ├── sessions_router.py           # Session history, message retrieval, ratings
│       ├── tools_router.py              # Tool definition CRUD and dynamic tool creation
│       ├── mcp_servers_router.py        # MCP server connection testing and tool discovery
│       ├── files_router.py              # File attachment uploads
│       ├── knowledge_router.py          # Knowledge base CRUD and document indexing
│       ├── memory_router.py             # Agent long-term memory retrieval and management
│       ├── traces_router.py             # Execution trace spans for sessions and workflow runs
│       ├── eval_router.py             # Eval suite CRUD and test run execution
│       ├── optimizer_router.py        # Prompt optimizer triggering, accept/reject, vault saving
│       ├── prompt_vault_router.py     # System prompt vault CRUD
│       ├── skills_router.py           # Skills vault CRUD (Claude agents)
│       ├── whatsapp_router.py         # WhatsApp channels, QR stream, voice samples, incoming webhook
│       ├── settings_router.py         # System application settings
│       ├── sandbox_router.py          # Docker sandbox container status
│       ├── analytics_router.py        # Observability metrics, token counts, cost tracking
│       ├── dashboard_router.py        # Dashboard summary statistics
│       └── admin_router.py            # System administration and RBAC user management
├── frontend/                            # Next.js 16 React frontend app
│   ├── auth.ts                          # NextAuth v5 credentials provider configuration
│   ├── next.config.ts                   # Next.js rewrite rules (proxying `/api/*` to FastAPI backend)
│   ├── app/                             # Next.js App Router pages
│   │   ├── layout.tsx                   # Root HTML layout, ThemeProvider, Toast notifications
│   │   ├── login/page.tsx               # Login page with TOTP 2FA step
│   │   ├── register/page.tsx            # User registration page
│   │   └── (authenticated)/             # Protected layout requiring valid NextAuth session
│   │       ├── home/page.tsx            # Dashboard overview page
│   │       ├── playground/page.tsx      # Main Chat Playground (agents, teams, workflows)
│   │       ├── sessions/page.tsx        # Conversation session history and execution trace viewer
│   │       ├── settings/page.tsx        # User profile, 2FA setup, secrets vault
│   │       ├── knowledge/page.tsx       # Knowledge base list and document manager
│   │       ├── evals/page.tsx           # Eval suite runner and results dashboard
│   │       ├── prompts/page.tsx         # Prompt Vault manager
│   │       ├── skills/page.tsx          # Skills Vault manager
│   │       ├── channels/page.tsx        # WhatsApp channel manager and QR pairing modal
│   │       ├── observability/page.tsx   # Token usage and cost tracking dashboard
│   │       └── admin/page.tsx           # Admin user management and permission flags
│   ├── components/                      # React components
│   │   ├── app-shell.tsx                # Main authenticated application shell
│   │   ├── app-sidebar.tsx              # Dynamic navigation sidebar
│   │   ├── header.tsx                   # Top navigation header with HITL notification badge
│   │   ├── playground/                  # Chat components, artifact panel, agent/team/workflow dialogs
│   │   ├── ai-elements/                 # Markdown, Shiki syntax highlighter, KaTeX, Mermaid diagrams
│   │   └── dialogs/                     # Tool, MCP, secret, provider, schedule modals
│   ├── lib/                             # Frontend utility functions
│   │   ├── api-client.ts                # Axios/fetch wrapper with JWT header injection
│   │   ├── crypto.ts                    # Client-side CryptoJS AES payload encryption
│   │   └── stream.ts                    # Server-Sent Events parser and stream reader
│   └── stores/                          # Zustand state management
│       ├── playground-store.ts          # Chat state, active session, artifacts, HITL pending list
│       ├── dashboard-store.ts           # Dashboard statistics state
│       ├── permissions-store.ts         # User permission flags
│       └── admin-store.ts             # Admin panel user list state
└── wa-bridge/                           # Node.js Baileys WhatsApp Web sidecar
    └── index.js                         # Baileys socket connection manager, QR code renderer, webhook poster
```

---

## Functionality Reference

### Authentication & User Management

#### User Registration
- **Trigger:** User fills out registration form and submits on `/register`.
- **Entry point:** `frontend/app/register/page.tsx` → `handleRegister()` → `backend/routers/auth_router.py` → `register_user()`
- **What it does:** Encrypts user credentials client-side using AES-256-CBC with `NEXT_PUBLIC_ENCRYPTION_KEY`. Backend decrypts the payload, checks for existing username/email, hashes the password with `bcrypt`, assigns the default role (`guest` or `admin` if first user), and creates a user record in SQLite/MongoDB.
- **Touches:** `frontend/lib/crypto.ts`, `backend/crypto_utils.py`, `backend/auth.py`, `users` table / `UserCollection`.
- **Inputs/Outputs:** Inputs: `{username, email, password}` (AES encrypted payload). Outputs: `UserResponse` JSON object containing `id`, `username`, `email`, `role`, `permissions`.
- **Side effects:** Writes new user record to database.

#### User Login
- **Trigger:** User submits credentials on `/login`.
- **Entry point:** `frontend/app/login/page.tsx` → `handleLogin()` → `frontend/auth.ts` → `backend/routers/auth_router.py` → `login_user()`
- **What it does:** Encrypts login payload client-side. Backend decrypts, verifies username and password with `bcrypt`. If 2FA is enabled for the account, returns `requires_2fa: true`. Otherwise, generates an HS256 JWT access token and returns it to NextAuth to establish session cookie.
- **Touches:** `frontend/auth.ts`, `backend/auth.py`, `users` table / `UserCollection`.
- **Inputs/Outputs:** Inputs: `{username, password}`. Outputs: `{access_token, token_type, requires_2fa}`.
- **Side effects:** Logs user session in NextAuth.

#### Two-Factor Authentication Setup & Verification
- **Trigger:** User clicks "Enable 2FA" in `/settings`.
- **Entry point:** `frontend/app/(authenticated)/settings/page.tsx` → `backend/routers/auth_router.py` → `setup_2fa()` / `verify_2fa()`
- **What it does:** `setup_2fa()` generates a random TOTP secret via `pyotp`, creates a provisioning URI, and returns a QR code data URL. `verify_2fa()` validates a 6-digit TOTP token against the secret and sets `totp_enabled = True` in the database.
- **Touches:** `backend/auth.py`, `pyotp`, `qrcode`, `users` table.
- **Inputs/Outputs:** Inputs: `{code}` for verification. Outputs: QR image string and success status.
- **Side effects:** Updates user's `totp_secret` and `totp_enabled` status in database.

#### API Client Credentials
- **Trigger:** User creates API client credentials in `/settings`.
- **Entry point:** `backend/routers/auth_router.py` → `create_api_client()`
- **What it does:** Generates a random `client_id` (`client_...`) and `client_secret` (`secret_...`). Hashes the secret with `bcrypt` for database storage and returns the plain secret to the user once.
- **Touches:** `backend/auth.py`, `api_clients` table / `APIClientCollection`.
- **Inputs/Outputs:** Inputs: `{name, description}`. Outputs: `{client_id, client_secret}`.
- **Side effects:** Writes API client record to database.

---

### LLM Provider & Secret Management

#### Configure LLM Provider
- **Trigger:** User creates or edits an LLM Provider in sidebar / provider dialog.
- **Entry point:** `frontend/components/dialogs/provider-dialog.tsx` → `backend/routers/providers_router.py` → `create_provider()` / `update_provider()`
- **What it does:** Accepts provider type (`openai`, `anthropic`, `google`, `ollama`, `custom`), API key or secret ID reference, base URL, and default model ID. If API key is provided directly, encrypts key using Fernet key (`PROVIDER_KEY_SECRET`).
- **Touches:** `backend/encryption.py`, `backend/llm/provider_factory.py`, `llm_providers` table.
- **Inputs/Outputs:** Inputs: `ProviderCreate` schema. Outputs: `LLMProviderResponse` (masking API key).
- **Side effects:** Writes encrypted provider configuration to database.

#### Store Secret in Secrets Vault
- **Trigger:** User adds a secret key in `/settings` (Secrets tab).
- **Entry point:** `frontend/app/(authenticated)/settings/page.tsx` → `backend/routers/secrets_router.py` → `create_secret()`
- **What it does:** Encrypts user-provided secret value (e.g. API keys) at rest using Fernet symmetric encryption with `PROVIDER_KEY_SECRET`.
- **Touches:** `backend/encryption.py`, `user_secrets` table / `UserSecretCollection`.
- **Inputs/Outputs:** Inputs: `{name, value, description}`. Outputs: `SecretResponse`.
- **Side effects:** Stores encrypted key in database.

---

### Agent Builder & Version Control

#### Agent Creation & Update
- **Trigger:** User saves agent configuration in Agent Dialog.
- **Entry point:** `frontend/components/playground/agent-dialog.tsx` → `backend/routers/agents_router.py` → `create_agent()` / `update_agent()`
- **What it does:** Saves agent configuration including system prompt, provider ID, model ID, tools, MCP servers, knowledge bases, skills, HITL tool overrides, prompt vault reference, and sandbox flags. On update, automatically creates a version snapshot in `agent_versions` table before applying changes.
- **Touches:** `backend/routers/versions_router.py`, `agents` table, `agent_versions` table.
- **Inputs/Outputs:** Inputs: `AgentCreate` / `AgentUpdate` schema. Outputs: `AgentResponse`.
- **Side effects:** Inserts new version record into `agent_versions` table.

#### Agent Version Rollback
- **Trigger:** User selects a previous version in Version History panel and clicks "Rollback".
- **Entry point:** `backend/routers/versions_router.py` → `rollback_agent_version()`
- **What it does:** Fetches target `config_snapshot` from `agent_versions`, creates a new version snapshot of current state for safety, and restores agent configuration fields to target version state.
- **Touches:** `backend/routers/agents_router.py`, `agents` table, `agent_versions` table.
- **Inputs/Outputs:** Inputs: `agent_id`, `version_id`. Outputs: Updated `AgentResponse`.
- **Side effects:** Reverts agent record in database and creates a new rollback version snapshot.

#### Agent Import / Export
- **Trigger:** User clicks "Export" on agent menu or uploads JSON in "Import Agent".
- **Entry point:** `backend/routers/agents_router.py` → `export_agent()` / `import_agent()`
- **What it does:** Export resolves internal database IDs (tools, MCP servers, KBs) into human-readable names and outputs a self-contained JSON file. Import matches names back to current user resources, skips missing dependencies with warnings, and constructs a new agent.
- **Touches:** `agents`, `tool_definitions`, `mcp_servers`, `knowledge_bases` tables.
- **Inputs/Outputs:** Inputs: Agent JSON file. Outputs: Imported `AgentResponse` and warnings array.
- **Side effects:** Creates new agent record.

---

### Multi-Agent Teams

#### Team Orchestration
- **Trigger:** User creates a team and starts a conversation in Playground (Teams tab).
- **Entry point:** `frontend/components/playground/team-dialog.tsx` → `backend/routers/teams_router.py` → `create_team()` / `backend/routers/chat_router.py` → `stream_chat()`
- **What it does:** Supports three coordination modes:
  1. `Coordinate`: Lead agent receives user query and uses `team_delegation_tools` (`delegate_task`, `summarize_team_outputs`) to delegate subtasks to team member agents.
  2. `Route`: Lead agent evaluates prompt and routes request directly to single best member agent.
  3. `Collaborate`: Agents execute sequentially in defined sequence, passing cumulative outputs down the chain.
- **Touches:** `backend/team_delegation_tools.py`, `backend/services/agent_runner.py`, `teams` table.
- **Inputs/Outputs:** Inputs: Team configuration with member agent IDs and mode. Outputs: Streamed SSE team response.
- **Side effects:** Creates session history for team execution.

---

### Visual Workflow Automation & Visual DAG Execution

#### Visual DAG Workflow Definition & Saving
- **Trigger:** User builds visual pipeline on canvas (`@xyflow/react`) and clicks "Save Workflow".
- **Entry point:** `frontend/components/playground/workflow-dialog.tsx` → `backend/routers/workflows_router.py` → `create_workflow()` / `update_workflow()`
- **What it does:** Validates workflow structure against cycle detection using Depth-First Search (DFS) topological sort in `backend/dag_executor.py`. Rejects cyclic graphs with HTTP 400 error. Stores nodes, edges, agent assignments, and canvas layout JSON.
- **Touches:** `backend/dag_executor.py`, `workflows` table / `WorkflowCollection`.
- **Inputs/Outputs:** Inputs: `{name, description, nodes, edges}`. Outputs: `WorkflowResponse`.
- **Side effects:** Saves definition in database.

#### Real-Time SSE DAG Execution
- **Trigger:** User clicks "Run Workflow" in Playground or Dashboard.
- **Entry point:** `backend/routers/workflows_router.py` → `run_workflow()` → `backend/dag_executor.py` → `execute_dag_stream()`
- **What it does:** Performs topological sort on DAG nodes. Identifies independent parallel branches and executes nodes concurrently via `asyncio.gather()`. Streams SSE execution events (`node_start`, `node_output`, `node_complete`, `node_failed`) keyed by node ID, causing UI canvas nodes to pulse colors in real-time.
- **Touches:** `backend/dag_executor.py`, `backend/services/agent_runner.py`, `workflow_runs` table.
- **Inputs/Outputs:** Inputs: `{input_text}`. Outputs: Real-time SSE event stream.
- **Side effects:** Writes `WorkflowRun` record with full node execution output and status.

#### Scheduled Workflows (Cron Execution)
- **Trigger:** APScheduler background trigger fires based on cron expression.
- **Entry point:** `backend/main.py` → `_load_active_schedules()` → `backend/scheduler_executor.py` → `run_scheduled_workflow_sqlite()` / `run_scheduled_workflow_mongo()`
- **What it does:** Runs headless workflow execution server-side without an active browser session. Feeds initial `input_text` into first workflow step, executes steps sequentially or via DAG executor, records run output in `workflow_runs`, and updates `last_run_at` / `next_run_at`.
- **Touches:** `backend/scheduler.py`, `workflow_schedules` table, `workflow_runs` table.
- **Inputs/Outputs:** Inputs: Scheduled trigger args (`schedule_id`). Outputs: New `WorkflowRun` record.
- **Side effects:** Writes execution results to database and execution trace spans.

---

### Real-Time Chat Playground & Artifacts

#### Streaming Chat Response
- **Trigger:** User sends a message in Chat Playground.
- **Entry point:** `frontend/components/playground/chat-playground.tsx` → `frontend/lib/stream.ts` → `backend/routers/chat_router.py` → `stream_chat()` → `backend/services/agent_runner.py`
- **What it does:** Assembles conversation context: fetches long-term agent memories, retrieves relevant RAG chunks from knowledge bases/session attachments, injects attached Claude skills. Passes prompt to provider driver (`llm/`). Executes tool call loop (up to 10 iterations). Streams response tokens, tool call parameters, tool outputs, chain-of-thought reasoning, and artifact tags via SSE.
- **Touches:** `backend/services/agent_runner.py`, `backend/llm/`, `sessions` table, `messages` table, `trace_spans` table.
- **Inputs/Outputs:** Inputs: `{message, session_id, agent_id|team_id|workflow_id}`. Outputs: SSE stream of token/tool/artifact chunks.
- **Side effects:** Saves user message, assistant response messages, token counts, and execution trace spans.

#### Automatic Context Compaction
- **Trigger:** Session history length exceeds 80% of model context window token limit during `stream_chat()`.
- **Entry point:** `backend/services/agent_runner.py` → `compact_context_if_needed()`
- **What it does:** Retains the last 10 messages verbatim. Summarizes all older messages into a concise summary using the agent's LLM model, replaces older message records in session history with summary message, and emits a `context_compacted` SSE event to frontend.
- **Touches:** `backend/services/agent_runner.py`, `messages` table.
- **Inputs/Outputs:** Inputs: Current session messages. Outputs: Compacted message list.
- **Side effects:** Updates message records in database.

#### Interactive Artifact Panel
- **Trigger:** Agent emits `<artifact id="..." title="..." type="...">...</artifact>` tag in response stream.
- **Entry point:** `frontend/components/playground/artifact-panel.tsx` → `playground-store.ts`
- **What it does:** Intercepts `<artifact>` XML tags in real time and strips them from raw chat text, displaying an inline reference chip instead. Opens side-panel tab showing live rendered preview (HTML, JSX, SVG in sandboxed iframe) or Shiki syntax-highlighted code editor.
- **Touches:** `frontend/components/playground/artifact-panel.tsx`, `frontend/components/playground/chat-playground.tsx`.
- **Inputs/Outputs:** Inputs: Artifact content string. Outputs: Rendered preview/editor view.
- **Side effects:** Updates Zustand `playground-store` state.

---

### Dynamic Tool Creation & Human-in-the-Loop (HITL)

#### Dynamic Tool Creation & Review Proposal
- **Trigger:** Agent with `allow_tool_creation = True` proposes a new tool during conversation loop.
- **Entry point:** `backend/services/agent_runner.py` → `backend/routers/chat_router.py` → `approve_tool_proposal()` / `reject_tool_proposal()`
- **What it does:** Agent calls internal tool proposal function when facing a missing capability. Backend suspends execution, yields `tool_proposal` SSE event, and creates `tool_proposals` record. An inline review card appears in chat. Upon user approval, backend creates `tool_definitions` row, makes tool immediately available in current session, and triggers silent sidebar refresh. Auto-rejects after 10 minutes.
- **Touches:** `backend/services/agent_runner.py`, `tool_proposals` table, `tool_definitions` table.
- **Inputs/Outputs:** Inputs: `{proposal_id, action}`. Outputs: Status confirmation and created tool ID.
- **Side effects:** Inserts new tool definition in database.

#### Human-in-the-Loop (HITL) Tool Approval
- **Trigger:** Agent attempts tool call on a tool flagged as `requires_confirmation = True` or listed in agent's `hitl_confirmation_tools`.
- **Entry point:** `backend/services/agent_runner.py` → `backend/routers/chat_router.py` → `approve_hitl()` / `reject_hitl()`
- **What it does:** Agent streaming generator pauses tool execution, creates `hitl_approvals` record with status `pending`, streams `hitl_approval_required` event, and waits on `asyncio.Event`. An amber approval card appears in chat and global header bell badge. When user clicks Approve/Deny, HTTP request sets `asyncio.Event`, unblocking generator to execute tool or return denial error. Auto-denies on server restart or 10-minute timeout.
- **Touches:** `backend/services/agent_runner.py`, `hitl_approvals` table.
- **Inputs/Outputs:** Inputs: `{approval_id, action}`. Outputs: Unblocked tool execution output.
- **Side effects:** Updates `hitl_approvals` table status (`approved` / `denied`).

---

### Model Context Protocol (MCP) Integration

#### MCP Server Binding & Tool Discovery
- **Trigger:** User adds MCP server configuration and tests connection in MCP Dialog.
- **Entry point:** `frontend/components/dialogs/mcp-dialog.tsx` → `backend/routers/mcp_servers_router.py` → `test_mcp_server()` / `create_mcp_server()`
- **What it does:** Supports `stdio` transport (launching local Docker/npx/python subprocess) and `sse` transport (connecting over HTTP/SSE). `mcp_client.py` initializes protocol handshake, queries `tools/list`, and discovers available tool definitions. Attached MCP servers expose tools dynamically to agents.
- **Touches:** `backend/mcp_client.py`, `mcp_servers` table / `MCPServerCollection`.
- **Inputs/Outputs:** Inputs: `{name, transport_type, command, args, url, env}`. Outputs: List of discovered MCP tools.
- **Side effects:** Persists server configuration in database.

---

### Knowledge Bases & RAG

#### Knowledge Base File/Text Indexing
- **Trigger:** User creates knowledge base and uploads document on `/knowledge/[id]`.
- **Entry point:** `frontend/app/(authenticated)/knowledge/[id]/page.tsx` → `backend/routers/knowledge_router.py` → `add_kb_document()`
- **What it does:** Accepts plain text or file upload (PDF, DOCX, TXT, Markdown). Parses document text, splits content into overlapping chunks using `RecursiveCharacterTextSplitter`, generates vector embeddings via Vertex AI/FAISS, and persists index files in storage directory.
- **Touches:** `backend/rag_service.py`, `knowledge_bases` table, `kb_documents` table.
- **Inputs/Outputs:** Inputs: `{doc_type, name, content_text|file}`. Outputs: `KBDocumentResponse` with `indexed = True`.
- **Side effects:** Writes document record and vector store index files to disk.

---

### Long-Term Agent Memory & Reflection

#### Background Memory Reflection
- **Trigger:** First message of a new session for an agent with `memory_enabled = True`.
- **Entry point:** `backend/routers/chat_router.py` → `backend/services/agent_runner.py` → `extract_memories_background()`
- **What it does:** Launches a background task (zero user delay) that passes previous session history to agent's LLM model. Extracts durable facts categorized into `preference`, `context`, `decision`, and `correction`. Stores key-value facts in `agent_memories` table (capped at 50 memories per user/agent pair). Injects all stored facts into system prompts of subsequent sessions.
- **Touches:** `backend/services/agent_runner.py`, `agent_memories` table / `AgentMemoryCollection`.
- **Inputs/Outputs:** Inputs: Previous session message list. Outputs: Extracted key-value facts.
- **Side effects:** Writes/updates rows in `agent_memories` table.

---

### Eval Harness & Regression Testing

#### Eval Suite Execution
- **Trigger:** User triggers eval suite run on `/evals`.
- **Entry point:** `frontend/app/(authenticated)/evals/page.tsx` → `backend/routers/eval_router.py` → `run_eval_suite()` → `backend/eval_engine.py` → `run_eval_suite_background()`
- **What it does:** Executes test cases against agent configuration in background. Supports three grading methods: `exact_match` (string equality), `contains` (substring search), and `llm_judge` (secondary LLM call scoring output and providing reasoning). Scores run percentage pass/fail and persists run results.
- **Touches:** `backend/eval_engine.py`, `eval_suites` table, `eval_runs` table.
- **Inputs/Outputs:** Inputs: `suite_id`. Outputs: `EvalRunResponse` with score and detailed case results.
- **Side effects:** Writes `eval_runs` record in database.

---

### Prompt Auto-Optimizer & Vaults

#### System Prompt Auto-Optimization
- **Trigger:** User triggers optimizer on `/prompts` or APScheduler weekly auto-sweep fires.
- **Entry point:** `backend/routers/optimizer_router.py` → `trigger_optimizer()` → `backend/optimizer.py` → `start_optimization_sqlite()` / `start_optimization_mongo()`
- **What it does:** Collects recent session execution traces for target agent. First LLM pass identifies failure patterns and categorizes them by severity. Second LLM pass rewrites system prompt to fix issues. Optional eval suite validation compares baseline score vs proposed prompt score. User accepts or rejects proposed prompt; accepting creates a version snapshot before updating agent.
- **Touches:** `backend/optimizer.py`, `backend/eval_engine.py`, `optimization_runs` table, `agent_versions` table.
- **Inputs/Outputs:** Inputs: `{agent_id, eval_suite_id, min_traces}`. Outputs: `OptimizationRunResponse` with diff and scores.
- **Side effects:** Updates agent system prompt and stores run record.

#### Skills Vault (Claude Agents Only)
- **Trigger:** User manages skills on `/skills` or attaches skills in Agent Dialog.
- **Entry point:** `frontend/app/(authenticated)/skills/page.tsx` → `backend/routers/skills_router.py` → `create_skill()` / `update_skill()`
- **What it does:** Creates reusable instruction bundles. Selector in agent dialog is gated to activate only when provider is Anthropic and model ID starts with `claude`. Attached skills are injected into system prompt during conversation assembly.
- **Touches:** `backend/routers/skills_router.py`, `skills` table / `SkillCollection`.
- **Inputs/Outputs:** Inputs: `{name, description, content}`. Outputs: `SkillResponse`.
- **Side effects:** Writes skill definition to database.

---

### WhatsApp Channel Integration & Voice Services

#### WhatsApp Channel Pairing & Incoming Message Handling
- **Trigger:** User connects channel on `/channels` and scans QR code. External contact sends WhatsApp message.
- **Entry point:** `wa-bridge/index.js` → `backend/routers/whatsapp_router.py` → `stream_channel_qr()` / `handle_incoming_wa_message()` → `backend/services/whatsapp_service.py`
- **What it does:** `wa-bridge` initializes Baileys Web socket, generates QR data URL via SSE stream. Upon QR scan, session connects and stores auth credentials in `wa-bridge/auth/`. Incoming messages hit `POST /wa/incoming`. If voice note, transcribed via Groq Whisper API (`stt_service.py`). Message maps to persistent `Session`, runs agent headlessly. If voice reply enabled, response synthesised via `tts_service.py` (Qwen3-TTS / Pocket TTS / Kokoro) and converted to WhatsApp OGG Opus via `ffmpeg`. Audio or text posted back to sidecar for delivery.
- **Touches:** `wa-bridge/index.js`, `backend/services/whatsapp_service.py`, `backend/services/stt_service.py`, `backend/services/tts_service.py`, `whatsapp_channels` table, `wa_contact_sessions` table.
- **Inputs/Outputs:** Inputs: Incoming Baileys JSON payload. Outputs: Sent WhatsApp text or audio message response.
- **Side effects:** Creates message records, session entries, and writes temporary TTS audio files.

#### Voice Cloning Sample Upload
- **Trigger:** User records or uploads voice sample in WhatsApp Channel settings (`/channels/[id]`).
- **Entry point:** `backend/routers/whatsapp_router.py` → `upload_voice_sample()`
- **What it does:** Validates audio file length (min 3s), converts sample to 16kHz mono WAV via `ffmpeg`, saves file to `voice_samples/` directory, and updates channel record. When Qwen3-TTS is active, voice clone prompt is computed once from reference audio and cached in memory for subsequent replies.
- **Touches:** `backend/services/tts_service.py`, `whatsapp_channels` table, disk storage.
- **Inputs/Outputs:** Inputs: Audio file upload. Outputs: Updated channel configuration.
- **Side effects:** Writes WAV file to disk and updates database path.

---

### Docker Sandbox Execution

#### Sandbox Lifecycle & Container Tools
- **Trigger:** User enables Docker Sandbox on agent or team and clicks "Start Sandbox".
- **Entry point:** `backend/routers/agents_router.py` → `start_agent_sandbox()` → `backend/sandbox_tools.py` → `start_sandbox_container()`
- **What it does:** Launches isolated container from `obsidian-webdev-base:latest` image with 512 MB memory limit, 1 CPU limit, and `/workspace` working directory. Injects 9 built-in tools (`sandbox_bash`, `sandbox_write`, `sandbox_read`, `sandbox_ls`, `sandbox_glob`, `sandbox_grep`, `sandbox_delete`, `sandbox_python`, `sandbox_node`) into agent toolset. Injected system prompt directs agent to run `sandbox_read` on created files, surfacing them automatically as rendered `<artifact>` components.
- **Touches:** `backend/sandbox_tools.py`, Docker Engine API, `agents` / `teams` table.
- **Inputs/Outputs:** Inputs: `agent_id` or `team_id`. Outputs: Container ID and status.
- **Side effects:** Creates and runs Docker container on host system.

---

### Observability & Traces

#### Execution Spans & Cost Tracking
- **Trigger:** Agent execution or workflow run generates spans during LLM and tool calls.
- **Entry point:** `backend/services/agent_runner.py` → `backend/routers/traces_router.py` → `get_session_trace()`
- **What it does:** Records timing, input/output tokens, cache read/creation tokens, USD cost estimation (based on per-model pricing table), and span sequence in `trace_spans` table. Surfaces detailed breakdown tree in `/sessions` activity drawer and `/observability` dashboard.
- **Touches:** `backend/routers/traces_router.py`, `trace_spans` table / `TraceSpanCollection`.
- **Inputs/Outputs:** Inputs: `session_id` or `workflow_run_id`. Outputs: List of execution `TraceSpanResponse` items.
- **Side effects:** Writes trace spans to database.

---

## Interaction Map

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│                               Next.js 16 Frontend                                │
│   (App Router, NextAuth v5, Zustand Stores, CryptoJS AES Encryption, xyflow DAG) │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │ HTTP REST / SSE Streams (/api proxy)
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                                FastAPI Backend                                   │
│  (main.py lifespan, CORS, RateLimiter, Crypto Utils, JWT, Fernet Secret Vault)   │
└──────┬───────────────────┬──────────────────────┬───────────────────┬────────────┘
       │                   │                      │                   │
       ▼                   ▼                      ▼                   ▼
┌──────────────┐   ┌───────────────┐      ┌───────────────┐   ┌───────────────┐
│ SQLite ORM / │   │ LLM Providers │      │ Docker Daemon │   │  wa-bridge    │
│ MongoDB ODM  │   │ (OpenAI,      │      │ (Sandbox      │   │ (Node Baileys │
│  Database    │   │  Anthropic,   │      │  Containers)  │   │  WhatsApp)    │
│  Storage     │   │  Gemini, etc) │      └───────────────┘   └───────────────┘
└──────────────┘   └───────────────┘
```

### End-to-End Data Flow Patterns

1. **User Chat Execution Flow:**
   `User Submit Message` → `CryptoJS AES Encrypt (Optional)` → `POST /chat (SSE)` → `FastAPI Decrypt` → `Load Long-Term Memory & KB FAISS Chunks` → `LLM Provider Stream` → `Tool Execution Loop` → `HITL Suspension (if required)` → `Stream Tokens/Artifacts` → `Write Trace Spans & Message History`.

2. **WhatsApp Message Flow:**
   `WhatsApp Client Message` → `wa-bridge Baileys Socket` → `POST /wa/incoming Webhook` → `Whisper STT (if voice note)` → `Map Sender Session` → `Headless Agent Execution` → `TTS Synthesis & ffmpeg OGG conversion (if voice reply)` → `POST wa-bridge /api/send` → `WhatsApp Client Delivery`.

3. **Scheduled Workflow Execution Flow:**
   `APScheduler Cron Trigger` → `Load Schedule Input Text` → `Topological Sort DAG Executor` → `Parallel Step Execution` → `Record WorkflowRun Record & Trace Spans`.

---

## Naming & Config Notes

| Entity / Functionality | UI / User-Facing Label | Code / Internal Variable Name | Configuration / Magic String | Notes / Potential Gotcha |
|---|---|---|---|---|
| AES Payload Encryption | E2E Payload Encryption | `ENCRYPTION_KEY` / `NEXT_PUBLIC_ENCRYPTION_KEY` | Must match across frontend and backend | If mismatched, request decryption fails with raw AES exception. |
| Fernet Secret Storage | Stored Secrets | `PROVIDER_KEY_SECRET` | 32 URL-safe base64-encoded bytes | Must be a valid Fernet key; plain strings crash server startup. |
| Database Engine Switch | Database Selector | `DATABASE_TYPE` | `"sqlite"` or `"mongo"` | Code contains duplicate ORM/ODM models (`models.py` vs `models_mongo.py`) and explicit router branching. |
| Skills Vault Gating | Skills Selector | `skill_ids` | Provider `anthropic` & model starting with `claude` | Skills selector is disabled for non-Claude models in UI (`skills-selector.tsx`). |
| Tool Name Uniqueness | Tool Name | `ux_tool_definitions_user_name_active` | Scoped to `user_id` and `is_active = 1` | Soft-deleted tools do not conflict; active duplicate creation attempts return HTTP 409. |
| Database Path Docker | Persistent Storage | `DATABASE_URL` | `sqlite:////app/data/app.db` | Storage must be inside `/app/data` volume in Docker Compose; pointing elsewhere resets DB on restart. |
| Docker Sandbox Base Image | Docker Sandbox | `obsidian-webdev-base:latest` | Pre-built from `backend/Dockerfile.base` | Requires manual image build before sandbox containers can be launched. |
| HITL Zero-Busy-Wait Event | HITL Approval Card | `_pending_approvals` map | `asyncio.Event` | Server restart automatically auto-denies stale pending approvals in database. |

---

## Open Questions / Needs Verification

1. **Deprecated Pydantic V2 Warning Warnings:**
   - *Observation:* Running backend tests emits Pydantic V2 deprecation warnings regarding `class Config:` usage across `schemas.py`.
   - *Impact:* Functional behaviour is unaffected in Pydantic 2.x, but updating to Pydantic V3 in the future will require migrating to `model_config = ConfigDict(...)`.
   - *Action:* Flagged for human developer verification during future dependency upgrades.

2. **Unused / Legacy Vector Index Files Clean-Up:**
   - *Observation:* Deleting a `KnowledgeBase` or `KBDocument` deletes database records, but residual FAISS vector index files on disk (`faiss_index/`) may remain orphan depending on file storage permissions.
   - *Action:* Needs verification whether an automated disk cleanup job should be added.
