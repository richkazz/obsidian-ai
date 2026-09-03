# Migration Guide: External Agent API Platform (Obsidian AI)

## Objective
Bring the already-started Obsidian AI Agent API Platform (application registration, scoped API keys, agent publishing, and schema-validated invocation) to the MVP boundary defined in the change request — closing the test-coverage, MongoDB-parity, and frontend gaps left by the initial (backend-only) implementation pass, including a Developer/Integrations UI for managing applications, API keys, agent exposure/sharing, and schemas, plus an in-app developer documentation page — while leaving all existing UI-driven agent, team, workflow, and WhatsApp behavior unchanged.

## Pre-Flight Checklist (resolve before dispatch)
- [ ] `<REPO_URL>` set
- [ ] `<BASE_BRANCH>` confirmed
- [ ] `<BACKEND_DEPS_INSTALL_COMMAND>` verified (the prior implementation pass failed `pytest` collection due to missing FastAPI/Crypto dependencies — confirm the exact install command for this repo, e.g. `pip install -r backend/requirements.txt`, before dispatch)
- [ ] `<TEST_COMMAND>` verified runnable (backend test command, e.g. `cd backend && pytest -q`)
- [ ] `<MONGO_TEST_URI>` set (a reachable MongoDB instance/URI for the `DATABASE_TYPE=mongo` test pass)
- [ ] `<SQLITE_TEST_DATABASE_URL>` set (e.g. `sqlite:////app/data/test.db`, isolated from any dev/prod DB)
- [ ] `<TEST_ENCRYPTION_KEY>` / `<TEST_PROVIDER_KEY_SECRET>` set (valid Fernet key; the codebase crashes on startup with an invalid one)
- [ ] `<FRONTEND_DEPS_INSTALL_COMMAND>` / `<FRONTEND_BUILD_COMMAND>` verified (e.g. `cd frontend && npm install`, `npm run build`)

## Environment & Access
- Repository: `<REPO_URL>`
- Base Branch: `<BASE_BRANCH>`
- Working Branch: `migration/agent-api-platform`
- Backend install: `<BACKEND_DEPS_INSTALL_COMMAND>`
- Backend test command: `<TEST_COMMAND>`
- Frontend install/build: `<FRONTEND_DEPS_INSTALL_COMMAND>` / `<FRONTEND_BUILD_COMMAND>`
- Required env vars for test runs: `DATABASE_TYPE` (`sqlite` | `mongo`), `DATABASE_URL`=`<SQLITE_TEST_DATABASE_URL>`, `MONGO_URI`=`<MONGO_TEST_URI>`, `ENCRYPTION_KEY`/`NEXT_PUBLIC_ENCRYPTION_KEY`=`<TEST_ENCRYPTION_KEY>`, `PROVIDER_KEY_SECRET`=`<TEST_PROVIDER_KEY_SECRET>`

## Context & Starting Point

**Already completed in a prior pass (treat as the current baseline, not as work to redo):**
- New persistence models: `Application`, `APIKey`, `ApplicationAgentAccess`, `AgentAPIConfig`, `Schema`, `SchemaVersion`, `APIRequest` in `backend/models.py`; `AgentVersion` extended to reference pinned schema versions.
- Routers: `backend/routers/applications_router.py` (app registration, API-key CRUD/revocation, agent sharing), `backend/routers/schemas_router.py` (schema create/version/validate), `backend/routers/agent_api_router.py` (API exposure config, publish/lifecycle transitions, invocation).
- Services: `backend/services/schema_validation_service.py` (minimal JSON Schema validator), `backend/services/api_key_service.py` (prefixed key generation/hashing/verification).
- `backend/auth.py` extended with `get_application_api_key` for application-key auth.
- `backend/main.py` updated to register the new routers and create the new tables via `Base.metadata.create_all(engine)`.
- `docs/agent-api.md` created as an initial integration guide.
- Verified: `python -m compileall -q backend` passes; ad hoc script checks of `validate_json_schema` and API-key generation/hashing/verification passed; SQLAlchemy table creation for all six new tables confirmed.
- **Not verified:** a full `pytest -q` run in `backend/` never completed successfully (collection failed on missing dependencies; after installing dependencies, no full run was completed in that session).

**Entry Points (existing, extended by the above):**
- `backend/main.py` — FastAPI lifespan, router registration, table creation.
- `backend/auth.py` — JWT issuance, TOTP, existing API-client verification, now also `get_application_api_key`.
- `backend/routers/agents_router.py`, `backend/routers/versions_router.py` — existing agent CRUD and version-snapshot-on-update behavior that the API layer must not bypass.
- `backend/services/agent_runner.py` — the single shared execution engine; also the entry point for `chat_router.stream_chat()`, `teams_router` orchestration, `scheduler_executor.py` headless scheduled runs, and `whatsapp_service.py`.
- `backend/rate_limiter.py` (SlowAPI) — existing rate-limiting middleware, not yet wired to the new hierarchical Application → API Key → Agent model.
- `backend/encryption.py` (Fernet, `PROVIDER_KEY_SECRET`) — existing at-rest secret encryption for provider keys/user secrets.

**Not yet created (referenced by the change request's blast-radius plan but absent from the completed pass — do not assume they exist):**
`backend/services/authorization_service.py`, `backend/services/application_service.py`, `backend/services/agent_api_service.py`, `backend/services/schema_adapter_service.py`, `backend/services/secret_provider_service.py`, `backend/services/observability_service.py`, `backend/services/api_documentation_service.py`, `backend/schema_adapters/*`, `backend/secret_providers/*`, `backend/routers/api_keys_router.py`, `backend/routers/integrations_router.py`, `backend/routers/observability_router.py`, `backend/models_mongo.py` additions for the six new entities. **All frontend work is also still outstanding** — the completed pass touched backend files only: a Developer/Integrations navigation area, Applications and API Keys management pages, an "API / Deployment" section on the agent dialog, Exposed/Shared/Published-Versions views, the Schemas builder (visual + code), and an in-app API Documentation page all remain to be built.

**Call Chain (invocation path, already implemented, to be hardened in this guide):**
External app → API key → `agent_api_router` invocation endpoint → (should call, verify it does) `backend/services/agent_runner.py` headless execution → `schema_validation_service` → `APIRequest` telemetry write → JSON response.

## Scope & Named Constraints

**Out of scope** (explicitly deferred by the change request's own MVP boundary — do not implement in this pass): Pydantic / TypeScript-Zod / OpenAPI schema adapters; application-managed and external secret providers (AWS/Azure/GCP/Vault); asynchronous job polling and signed webhooks; generated SDKs; IP/network restrictions on API keys; advanced observability capture-policy UI beyond basic redaction. If any of these are encountered as a hard prerequisite for an in-scope item, stop that phase and log it — do not implement the out-of-scope item to unblock it.

**Named constraints (traced to specific gaps/rules in the source documents):**
1. **Untested code.** The prior pass never completed a full `pytest -q` run. Every file listed under "Already completed" above must be treated as unverified until Phase 1 of this guide passes. No later phase's changes may be considered complete while backend tests are red.
2. **Missing MongoDB parity.** The feature report states the codebase "contains duplicate ORM/ODM models (`models.py` vs `models_mongo.py`) and explicit router branching" on `DATABASE_TYPE`. The prior pass only touched `models.py`. The change request (Migration Plan, Applications/API Keys/Agent API Configuration/Schemas/Application-Agent Permissions sections) requires a Mongo representation for every new entity. This is a named gap, not an inference to skip.
3. **Missing central authorization service.** The change request requires a dedicated authorization resolver (`authenticate → application → scopes → agent access → resource permissions → most-restrictive-wins`) rather than checks scattered across routers. No such service exists in the completed pass; treat any authorization logic currently inline in `applications_router.py` / `schemas_router.py` / `agent_api_router.py` as provisional and unconsolidated.
4. **Highest-blast-radius file: `backend/services/agent_runner.py`.** It is the shared execution engine for chat, teams, scheduled workflows, and WhatsApp — all pre-existing, live features. The change request is explicit that the external API must be "a secure contract layer around the existing agent execution platform, not a second agent runtime." Any change here must be additive and must not alter behavior for non-API-invoked sessions.
5. **Secret non-leakage.** Secret values must never appear in agent definitions, exports, logs, traces, or API responses. `backend/encryption.py` / `PROVIDER_KEY_SECRET` is the only secret mechanism currently in scope (external providers are out of scope). Any new telemetry or audit-log code touching agent configs must redact secret-provider fields.
6. **Skills-vault gating must not regress.** The skills selector (`skill_ids`) is gated to provider `anthropic` with a `claude`-prefixed model. Self-contained agent provisioning through the new API must preserve this gate rather than allow arbitrary skill attachment.
7. **Version-snapshot behavior must remain intact.** `agents_router.py` / `versions_router.py` already create an `agent_versions` snapshot on every agent update. API-exposed agents must go through the same snapshot mechanism — the change request explicitly says the API model should "add API exposure rather than create a second incompatible agent type."
8. **No visual baseline for the new frontend work.** The feature report contains no screenshot paths or breakpoint matrix for any Developer/Integrations UI — Applications, API Keys, the agent "API / Deployment" tab, and the Schema builder are all new; none existed before this feature. Phases 8–11 therefore cannot do pixel-parity verification; they proceed under the named assumption that visual consistency is achieved by reusing the existing dialog pattern (`frontend/components/dialogs/mcp-dialog.tsx`) and vault-page pattern (`frontend/app/(authenticated)/skills/page.tsx`), not by diffing against prior screenshots.
9. **Full UI configuration is required scope, not optional polish.** The change request's UI Changes section explicitly specifies a Developer/Integrations navigation area (Applications, API Keys, Agents, Schemas, Secret Providers, Observability, API Documentation, Usage/Quotas) and an "API / Deployment" section on the existing agent dialog, and its documentation section calls for readable documentation "inside the Obsidian site." The completed pass was backend-only. Phases 8–11 close this gap and are part of the MVP boundary this guide targets, not a stretch goal to defer.

## Plan

### Phase 1: Close the Test-Coverage Gap (blocking prerequisite)
- Install backend dependencies with `<BACKEND_DEPS_INSTALL_COMMAND>` in a clean environment.
- Run `<TEST_COMMAND>` with `DATABASE_TYPE=sqlite` and capture full output.
- Fix failures strictly scoped to the files listed under "Already completed" in Context & Starting Point. Do not alter unrelated existing tests to force a pass.
- If a fix would require touching a named-constraint file (`agent_runner.py`, `versions_router.py`) beyond what later phases already plan, stop this phase for that specific failure, log it as an open question, and continue with the remaining independent failures.
- Do not proceed past Phase 1 until the suite is green under `DATABASE_TYPE=sqlite`, except for failures explicitly logged as open questions per the rule above.

### Phase 2: MongoDB Parity for New Persistence Models
- Add Mongo collection wrappers in `backend/models_mongo.py` (or the file the repo's existing pattern uses) for `Application`, `APIKey`, `ApplicationAgentAccess`, `AgentAPIConfig`, `Schema`, `SchemaVersion`, `APIRequest`, mirroring the field sets already implemented in `backend/models.py`.
- Add the indexes named in the change request: `application_id`, `key_prefix`, `revoked_at`, `expires_at` on API keys; composite uniqueness `(application_id, agent_id)` on application-agent access.
- Branch the three routers (`applications_router.py`, `schemas_router.py`, `agent_api_router.py`) on `DATABASE_TYPE` following the existing branching convention used elsewhere in the codebase (e.g. `database.py` vs `database_mongo.py`).
- Re-run `<TEST_COMMAND>` with `DATABASE_TYPE=mongo` and `MONGO_URI=<MONGO_TEST_URI>`. Both database backends must pass before continuing.

### Phase 3: Central Authorization Service & Resource Authorization
- Create `backend/services/authorization_service.py` implementing the chain: authenticate API key → resolve application → resolve API-key scopes → resolve `ApplicationAgentAccess` permissions → resolve resource permissions → apply most-restrictive-applicable policy.
- Refactor `applications_router.py`, `schemas_router.py`, and `agent_api_router.py` to call this service instead of any inline checks currently present.
- Implement the resource authorization resolver so self-contained agent provisioning (Mode 2) validates every referenced tool, MCP server, knowledge base, and secret reference against the application's granted permissions before the agent is created — an application must not be able to create an agent referencing a resource it cannot access.
- Explicitly preserve the skills-vault Claude-only gate (Named Constraint 6) inside this resolver rather than bypassing it for API-created agents.
- Add/extend tests: allowed application, denied application, shared agent, revoked share, cross-workspace access, restricted resource, restricted secret.

### Phase 4: Strict JSON Output Contract Hardening
- Inspect the existing `agent_api_router` invocation path. Determine whether it currently only validates output against the schema, or also performs a bounded repair attempt on failure.
- If no repair step exists, add exactly one bounded repair attempt: on validation failure, re-invoke the model once with the validation errors appended to context, then re-validate. Never loop beyond this single retry.
- If repair still fails, return the deterministic error contract from the change request (`{"error": {"code": "OUTPUT_SCHEMA_VALIDATION_FAILED", "message": ..., "request_id": ..., "details": [...]}}`) — never an internal stack trace or raw provider error.
- Confirm the success response includes `request_id`, `agent_id`, `agent_version`, `schema_version`, `status`, `output`.
- Add tests: valid output passes through unchanged; invalid output triggers exactly one repair attempt; output still invalid after repair returns the structured error and does not retry further.

### Phase 5: Hierarchical Rate Limiting & Idempotency Keys
- Wire `backend/rate_limiter.py` (SlowAPI) into the new invocation and mutation endpoints with three tiers: Application limit, API-Key limit, Agent limit. The effective limit is the most restrictive of the three.
- Add Idempotency-Key handling for `POST /agents`, `POST /agents/{id}/versions`, and the invoke endpoint: store the response for a configurable retention period keyed by the idempotency key + application, and return the stored response on a duplicate request instead of re-executing.
- Add tests: duplicate request with the same idempotency key returns the same result without a second execution; requests exceeding each tier's limit are rejected with a machine-readable error.

### Phase 6: Audit Log
- Add an `audit_events` table/collection (SQLite and Mongo, per Phase 2's pattern) with indexes on `actor`, `application_id`, `resource_id`, `event_type`, `created_at`.
- Write append-only audit records from the mutation endpoints already present in `applications_router.py` / `schemas_router.py` / `agent_api_router.py` for: application created/updated, API key created/revoked/rotated, agent shared, agent access revoked, agent published/deprecated, schema published.
- Confirm no secret values are ever written into an audit record (Named Constraint 5) — redact before writing.

### Phase 7: Publication Lifecycle & Version-Pinning Verification
- Confirm `AgentAPIConfig` (or equivalent) supports the full state machine `draft → testing → published → deprecated → retired`. Add any missing transition endpoints/guards.
- Confirm production invocation requires `agent_id` + an explicit published version, and that a new publish does not break a consumer already pinned to a prior published version.
- Confirm updating an agent still fires the existing `agent_versions` snapshot (Named Constraint 7) and that this snapshot correctly records the input/output schema versions in effect at that point.
- Add tests covering the full lifecycle sequence: create → test → version → publish → invoke → update → publish new version → deprecate old version while confirming the old version still serves existing pinned consumers.

### Phase 8: Frontend — Applications & API Keys Management UI
- Add a Developer/Integrations navigation area (e.g. `frontend/app/(authenticated)/developer/`), following the existing `frontend/app/(authenticated)/skills/page.tsx` page pattern, with an "Applications" page: list, create, edit, and view status of registered applications.
- Add an "API Keys" page/tab per application: create a key (name + scopes), reveal the plaintext secret exactly once at creation/rotation with a clear one-time-only warning, list existing keys with prefix/last-used/expiry, and revoke/rotate actions. Never re-render a previously issued secret after the creation/rotation response has been shown once.
- Add a Zustand store (modeled on `frontend/stores/admin-store.ts`) to hold applications/API-key list state, and reuse `frontend/lib/api-client.ts` for authenticated requests to the `applications_router` endpoints.
- Reuse the existing dialog pattern (`frontend/components/dialogs/mcp-dialog.tsx`) for the create/edit/rotate modals.

### Phase 9: Frontend — Agent "API / Deployment" Tab, Sharing & Publication UI
- Add an "API / Deployment" section to the existing agent configuration dialog (`frontend/components/playground/agent-dialog.tsx`): API exposure toggle, ownership, allowed-applications allowlist, scopes, input schema selector, output schema selector, publication state, rate limits, observability policy.
- Add "Exposed Agents", "Shared Agents", and "Published Versions" list views under the Developer/Integrations navigation area, showing each agent's lifecycle state (`draft → testing → published → deprecated → retired`) with publish/deprecate/retire actions wired to the Phase 7 lifecycle endpoints.
- Add an application-allowlist UI for granting/revoking a given application's access to a given agent, calling the `ApplicationAgentAccess` endpoints.
- This UI must call the same authorized endpoints a direct API caller would use — it must not bypass the authorization checks added in Phase 3 via a privileged internal path.

### Phase 10: Frontend — Schema Authoring UI (Visual + Code modes)
- Add a "Schemas" page under the Developer/Integrations navigation area.
- Build the schema builder with two modes: a visual field-by-field editor (string/number/integer/boolean/array/object/enum, nullable, required, defaults, descriptions, constraints, nesting) and a code mode that accepts a raw JSON Schema definition and posts it to `schemas_router`'s validation endpoint, rendering field path / expected type / received type / constraint failure inline.
- Reuse the existing dialog pattern (`frontend/components/dialogs/mcp-dialog.tsx`) for creation/edit modals and the Zustand store from Phase 8 for state.
- Per Named Constraint 8, no pixel-parity screenshot check applies to this phase — verify only functional correctness and consistency with the existing dialog/vault-page visual language.

### Phase 11: API Documentation — Content Completion & In-App Developer Docs
- Expand `docs/agent-api.md` to cover, per published agent: description, version, authentication requirements, required scopes, endpoint, input schema, output schema, example request/response, error catalog, rate limits, and explicit notes that async execution and webhooks are not yet supported (rather than omitting them silently). Add copy/paste examples in cURL, JavaScript/TypeScript, and Python.
- Add an "API Documentation" page under the Developer/Integrations navigation area (e.g. `frontend/app/(authenticated)/developer/docs/page.tsx`) that renders this documentation inside the app itself, per the change request's call for documentation "inside the Obsidian site" — this must not remain a repo-only markdown file.
- Generate the per-agent portion of this page (endpoint, input/output schema, examples) from the agent's actual `AgentAPIConfig` and published schema versions rather than hand-duplicating content, so the in-app docs cannot drift from the real published contract.
- If a machine-readable OpenAPI representation doesn't fit in this phase, log it as a deferred item rather than fabricating an incomplete one.

### Phase 12: Full MVP Acceptance Walkthrough
- Implement an integration/smoke-test script (pytest or shell+curl) that executes the full journey: register application → create API key → assign scopes → create/configure agent → define input schema (visual or code) → define output schema → test example input → test full agent execution → validate output against schema → publish agent version → grant a second application access → invoke from that second application → receive strict JSON → inspect request/execution telemetry → rotate/revoke API key → update the agent → publish a new version → confirm the old version still works → deprecate the old version → confirm the in-app API Documentation page for the published agent reflects its actual schema/config.
- Any step that fails must be logged as an open question in the completion report, not silently skipped or force-passed.

## Acceptance Criteria
- [ ] `<TEST_COMMAND>` passes fully under both `DATABASE_TYPE=sqlite` and `DATABASE_TYPE=mongo`.
- [ ] Every new entity from the completed pass (`Application`, `APIKey`, `ApplicationAgentAccess`, `AgentAPIConfig`, `Schema`, `SchemaVersion`, `APIRequest`) has a working Mongo representation with the required indexes.
- [ ] All authorization decisions for the new API surface route through `authorization_service.py`, applying most-restrictive-wins.
- [ ] Self-contained agent provisioning rejects any resource the calling application isn't authorized for, and preserves the Claude-only skills gate.
- [ ] Invocation enforces a single bounded repair attempt on output-schema failure, then returns the deterministic error contract — never an unbounded retry loop, never a raw stack trace.
- [ ] Rate limits are enforced at Application, API Key, and Agent tiers with the most restrictive applying.
- [ ] Idempotency keys prevent duplicate execution for `POST /agents`, `POST /agents/{id}/versions`, and invocation.
- [ ] Audit events are written for every listed mutation, with no secret values present in any record.
- [ ] The full lifecycle (`draft → testing → published → deprecated → retired`) works, and publishing a new agent version does not break consumers pinned to a prior published version.
- [ ] Existing agent creation/update, version snapshots, import/export, chat, team, workflow, scheduled-workflow, and WhatsApp behavior is unchanged (no regression in pre-existing tests).
- [ ] `docs/agent-api.md` contains all fields listed in Phase 11, with examples in cURL/JS/Python.
- [ ] Applications, API Keys (with one-time secret reveal), agent sharing/allowlists, and publication-state transitions are all fully manageable from the frontend UI — not only via direct API calls.
- [ ] The agent configuration dialog exposes an "API / Deployment" section covering exposure, allowlist, scopes, schemas, publication state, rate limits, and observability policy.
- [ ] An in-app API Documentation page exists and is generated from each published agent's actual config/schema versions rather than duplicated by hand.
- [ ] The 20-step Definition-of-Done journey (Phase 12) completes with no un-logged failures.

## Verification Instructions
1. Run the full backend test suite: `<TEST_COMMAND>` (once with `DATABASE_TYPE=sqlite`, once with `DATABASE_TYPE=mongo` and `MONGO_URI=<MONGO_TEST_URI>`).
2. Run the frontend build/lint: `<FRONTEND_BUILD_COMMAND>` for the new Developer/Integrations pages added in Phases 8–11.
3. Execute the Phase 12 end-to-end smoke script and confirm every one of the 20 journey steps completes or is explicitly logged.
4. Visual parity check: not applicable — no screenshot/breakpoint baseline exists for this new UI (Named Constraint 8). Confirm instead that the new pages visually match the existing dialog and vault-page components they were modeled on.

## Tools & Permissions
The agent may install dependencies, read/write files under `backend/`, `frontend/`, and `docs/`, run the backend and frontend test/build commands, and create new files following the "Not yet created" list above. The agent must not: modify `wa-bridge/`, `sandbox_tools.py`, or Docker/Nginx configuration; implement any item listed under "Out of scope"; commit real secret values, API keys, or `.env` files; force-push or rewrite existing git history; or delete/alter pre-existing tests to force a pass.

## Edge Cases, Guardrails & When Blocked
- Default behavior: when an ambiguity is encountered that isn't covered by a named constraint above, document the specific assumption made inline in code comments and in the completion report, then continue.
- If a change would require touching `backend/services/agent_runner.py` in a way that isn't already scoped by Phase 3/4 of this plan, or would alter behavior for non-API-invoked sessions: stop that phase, do not proceed to phases depending on it, and log it as an open question in the completion report.
- If a change would require implementing anything listed under "Out of scope" as a hard prerequisite: stop that phase and log it rather than implementing the out-of-scope item.
- Rollback trigger: any regression in a pre-existing (non-Agent-API) test — chat, teams, workflows, scheduled execution, WhatsApp, auth, secrets — at any phase. On trigger: revert the changes made in that phase only, leave the last known-green state on the working branch, and log the regression and the phase at which it occurred in the completion report. Do not attempt further phases building on the reverted work until a human resolves it.

## Completion Report Handoff
On completion, write `/doc/migrations/agent-api-platform-<YYYY-MM-DD>-report.md` containing:
1. Files modified and phases completed.
2. Verification evidence per acceptance criterion.
3. Deviations from the plan and why.
4. Usage sites/dependencies that could not be fully migrated.
5. Before/after visual comparison results (if UI-facing) — note explicitly that no pre-existing baseline was available for the new frontend work (Phases 8–11), per Named Constraint 8.
