# External Agent API Integration Guide (v1)

The External Agent API is a secure, schema-validated contract layer around the Obsidian AI agent platform. Normal agents remain private until an owner explicitly configures and publishes an API contract.

---

## Authentication & Authorization

All API calls must include the application API key in the `X-API-Key` header:

```http
X-API-Key: oba_prefix.secret
```

- Keys use the prefixed format `oba_<prefix>.<secret>`. Plaintext keys are revealed **exactly once** at creation/rotation.
- Authorization follows the most-restrictive policy chain:
  `Authentication -> Application status -> Key scopes -> ApplicationAgentAccess grant -> Resource permissions`.

---

## Code Examples

### cURL

```bash
curl -X POST "https://your-obsidian-domain.com/api/v1/agent-invocations/AGENT_ID" \
  -H "X-API-Key: oba_12345678.secret_value_here" \
  -H "Idempotency-Key: idemp_1002" \
  -H "Content-Type: application/json" \
  -d '{
    "version": 1,
    "input": {
      "query": "Summarize latest sales"
    }
  }'
```

### JavaScript / TypeScript

```typescript
const response = await fetch("https://your-obsidian-domain.com/api/v1/agent-invocations/AGENT_ID", {
  method: "POST",
  headers: {
    "X-API-Key": "oba_12345678.secret_value_here",
    "Idempotency-Key": "idemp_1002",
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    version: 1,
    input: { query: "Summarize latest sales" },
  }),
});

const data = await response.json();
console.log(data.output);
```

### Python

```python
import requests

url = "https://your-obsidian-domain.com/api/v1/agent-invocations/AGENT_ID"
headers = {
    "X-API-Key": "oba_12345678.secret_value_here",
    "Idempotency-Key": "idemp_1002",
    "Content-Type": "application/json",
}
payload = {
    "version": 1,
    "input": {"query": "Summarize latest sales"},
}

response = requests.post(url, headers=headers, json=payload)
print(response.json())
```

---

## Response Structure

Success Response (`200 OK`):

```json
{
  "request_id": "8f3d8a01-2b4e-4f12-9c3a-93a8e0f11b22",
  "agent_id": "12",
  "agent_version": 1,
  "input_schema_version": 1,
  "output_schema_version": 1,
  "status": "completed",
  "output": {
    "summary": "Sales increased by 15% this quarter.",
    "confidence": 0.95
  }
}
```

---

## Error Catalog

| Status Code | Error Code | Description |
| ----------- | ---------- | ----------- |
| `401` | `UNAUTHORIZED` | Invalid, expired, or revoked API key. |
| `403` | `INSUFFICIENT_SCOPE` | API key lacks required scope (e.g. `agent:invoke`). |
| `403` | `AGENT_ACCESS_DENIED` | Application is not granted access to the requested agent. |
| `404` | `PUBLISHED_VERSION_NOT_FOUND` | Pinned version requested does not exist for this agent. |
| `409` | `AGENT_NOT_AVAILABLE` | Agent is in `draft`, `deprecated`, or `retired` state. |
| `422` | `INPUT_SCHEMA_VALIDATION_FAILED` | Input payload failed validation against input JSON schema. |
| `429` | `RATE_LIMIT_EXCEEDED` | Request rate limit exceeded. |
| `502` | `OUTPUT_SCHEMA_VALIDATION_FAILED` | Agent output failed JSON schema validation after repair attempt. |

---

## Rate Limits & Idempotency

- Rate limits are enforced hierarchically across **Application**, **API Key**, and **Agent** tiers, applying the most restrictive policy.
- Replaying requests with an `Idempotency-Key` header returns cached responses for duplicate requests without re-executing LLM turns.

---

## Scope & MVP Limitations Notice

- **Async Polling & Webhooks:** Asynchronous job polling and signed webhooks are deferred for future releases. Invocation calls execute synchronously in MVP.
- **SDK Generators:** Client SDK generation (TypeScript Zod / Pydantic) is not yet supported in MVP.
