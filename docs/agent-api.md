# External Agent API (v1)

The Agent API is an opt-in contract layer around the existing agent runtime.
Existing UI agents remain private until an owner configures and publishes an API
contract.

## Setup

1. Create an application with `POST /api/v1/applications` using a user bearer
   token.
2. Create a scoped key with `POST /api/v1/applications/{application_id}/keys`.
   The returned `api_key` is shown once. It has the form `oba_<prefix>.<secret>`
   and only a bcrypt hash is retained.
3. Create input and output JSON Schema contracts at `POST /api/v1/schemas`.
   Add a revision with `POST /api/v1/schemas/{id}/versions`; versions are
   immutable.
4. Configure an existing agent through
   `PUT /api/v1/agents/{agent_id}/api-config`, then publish it with
   `POST /api/v1/agents/{agent_id}/publish`.
5. Explicitly share an agent with another application through
   `POST /api/v1/applications/agents/{agent_id}/shares`.

## Invoke a published agent

```bash
curl -X POST "$OBSIDIAN_URL/api/v1/agent-invocations/123" \
  -H "Authorization: Bearer $OBSIDIAN_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"version": 4, "input": {"question": "Where is my order?"}}'
```

Note: The API accepts application API keys via either `Authorization: Bearer <token>` (recommended) or `X-API-Key: <token>`.

Responses include `request_id`, pinned agent/schema versions, a status, and a
validated JSON `output`. Inputs are validated before execution and output is
parsed and validated server-side. Invalid output returns the machine-readable
`OUTPUT_SCHEMA_VALIDATION_FAILED` code without provider internals or secrets.

## Build an external chat UI

Give the browser or external client a key with both `agent:invoke` and
`agent:read` scopes. Create a session once, retain its returned `id`, and send
that `session_id` on each invocation:

```bash
curl -X POST "$OBSIDIAN_URL/api/v1/agent-sessions/123" \
   -H "Authorization: Bearer $OBSIDIAN_API_KEY"

curl -X POST "$OBSIDIAN_URL/api/v1/agent-invocations/123" \
   -H "Authorization: Bearer $OBSIDIAN_API_KEY" \
   -H 'Content-Type: application/json' \
   -d '{"session_id": "SESSION_ID", "input": {"question": "What failed?"}}'
```

Sessions created through these endpoints are bound to the application that
owns the API key. A different application cannot read or append to the
session, even if it knows the session ID. History is available through
`GET /api/v1/agent-sessions/{session_id}` and
`GET /api/v1/agent-sessions/{session_id}/messages`.

Image input can be sent as a base64 data URI or as a remote URL in
`attachments`. URL images are passed to the configured model provider and the
URL is retained in session history for replay:

```json
{
   "session_id": "SESSION_ID",
   "input": {"title": "Checkout error", "steps": ["submit payment"]},
   "attachments": [{
      "filename": "checkout-error.png",
      "media_type": "image/png",
      "file_type": "image",
      "url": "https://cdn.example.com/checkout-error.png"
   }]
}
```

Use `data: "data:image/png;base64,..."` instead when the image is private or
not publicly reachable by the model provider. Document attachments must use
`data`; they are stored and indexed for the agent's knowledge retrieval path.
URL-backed documents are rejected because the server does not download remote
documents. Use `agent:read` only for clients that need conversation history;
invocation-only clients need only `agent:invoke`.

## Session-scoped Knowledge Bases

When multiple callers or users invoke the same published agent but require searching different knowledge bases, callers can pass `knowledge_base_ids` on the invocation request body. This overrides the default knowledge base list configured on the agent for that invocation and session turn:

```json
{
   "session_id": "SESSION_ID",
   "input": {"question": "How do I process a refund?"},
   "knowledge_base_ids": ["kb_12345"]
}
```

## Access controls

Authorization is evaluated as **Application → API key scopes → explicit agent
allowlist → agent contract**. An agent owner application can invoke its own
agent; other applications require a non-revoked share with `agent:invoke`.
Keys may be revoked immediately and may have expirations. API request metadata
is recorded without request or response payloads.
