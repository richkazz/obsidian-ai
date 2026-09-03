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
  -H "X-API-Key: $OBSIDIAN_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"version": 4, "input": {"question": "Where is my order?"}}'
```

Responses include `request_id`, pinned agent/schema versions, a status, and a
validated JSON `output`. Inputs are validated before execution and output is
parsed and validated server-side. Invalid output returns the machine-readable
`OUTPUT_SCHEMA_VALIDATION_FAILED` code without provider internals or secrets.

## Access controls

Authorization is evaluated as **Application → API key scopes → explicit agent
allowlist → agent contract**. An agent owner application can invoke its own
agent; other applications require a non-revoked share with `agent:invoke`.
Keys may be revoked immediately and may have expirations. API request metadata
is recorded without request or response payloads.
