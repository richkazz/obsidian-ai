"use client"

import { useState, useEffect } from "react"
import { BookOpen } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { apiClient } from "@/lib/api-client"

interface PublishedContract {
  agentId: string
  agentName: string
  description: string | undefined
  config: Record<string, unknown>
  inputSchema: Record<string, unknown> | undefined
  outputSchema: Record<string, unknown> | undefined
  inputSchemaVersion: number | undefined
  outputSchemaVersion: number | undefined
  agentVersion: number | undefined
}

export default function APIDocsPage() {
  const [contracts, setContracts] = useState<PublishedContract[]>([])

  useEffect(() => {
    fetchExposedAgents()
  }, [])

  const fetchExposedAgents = async () => {
    try {
      const data = await apiClient.listAgents()
      const published = await Promise.all(data.map(async (agent) => {
        try {
          const config = await apiClient.getAgentAPIConfig(agent.id)
          if (config.publication_state !== "published") return null
          const schemas = await apiClient.listSchemas()
          const input = schemas.find((schema) => String(schema.latest_version?.id) === String(config.input_schema_version_id))
          const output = schemas.find((schema) => String(schema.latest_version?.id) === String(config.output_schema_version_id))
          return {
            agentId: String(agent.id),
            agentName: agent.name,
            description: agent.description,
            config,
            inputSchema: input?.latest_version?.canonical_schema,
            outputSchema: output?.latest_version?.canonical_schema,
            inputSchemaVersion: input?.latest_version?.version_number,
            outputSchemaVersion: output?.latest_version?.version_number,
            agentVersion: config.agent_version,
          }
        } catch {
          return null
        }
      }))
      setContracts(published.filter((contract): contract is PublishedContract => contract !== null))
    } catch (err) {
      console.error("Failed to load agents:", err)
    }
  }

  const backendEndpoint = process.env.NEXT_PUBLIC_BACKEND_URL || (typeof window !== "undefined" ? window.location.origin : "")
  const invocationUrl = `${backendEndpoint}/api/v1/agent-invocations/<AGENT_ID>`
  const sessionUrl = `${backendEndpoint}/api/v1/agent-sessions/<AGENT_ID>`
  const curlExample = `curl -X POST "${invocationUrl}" \\
  -H "Authorization: Bearer oba_<prefix>.<secret>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "input": {
      "query": "Hello Obsidian AI"
    },
    "session_id": "<SESSION_ID>"
  }'`

  const sessionExample = `curl -X POST "${sessionUrl}" \\
  -H "Authorization: Bearer oba_<prefix>.<secret>"

# Continue the same application-scoped conversation
curl -X POST "${invocationUrl}" \\
  -H "Authorization: Bearer oba_<prefix>.<secret>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "session_id": "<SESSION_ID>",
    "input": {"title": "Checkout error", "steps": ["submit payment"]},
    "attachments": [{
      "filename": "checkout-error.png",
      "media_type": "image/png",
      "file_type": "image",
      "url": "https://cdn.example.com/checkout-error.png"
    }]
  }'

# Read history (requires the agent:read scope)
GET ${backendEndpoint}/api/v1/agent-sessions/<SESSION_ID>/messages`

  const jsExample = `const response = await fetch("${invocationUrl}", {
  method: "POST",
  headers: {
    "Authorization": "Bearer oba_<prefix>.<secret>",
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    input: { query: "Hello Obsidian AI" },
    session_id: "<SESSION_ID>"
  })
});
const data = await response.json();`

  const pythonExample = `import requests

response = requests.post(
    "${invocationUrl}",
    headers={"Authorization": "Bearer oba_<prefix>.<secret>"},
    json={"input": {"query": "Hello Obsidian AI"}, "session_id": "<SESSION_ID>"},
)
print(response.json())`

  return (
    <div className="flex flex-col gap-6 p-8 max-w-7xl mx-auto">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">In-App API Documentation</h1>
        <p className="text-muted-foreground mt-1">
          Interactive developer reference for invoking published agent contracts via the External Agent API Platform.
        </p>
      </div>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Authentication</CardTitle>
            <CardDescription>
              All requests to <code className="text-xs font-mono bg-muted px-1 py-0.5 rounded">/api/v1/agent-invocations/*</code> require a valid Bearer key prefix (oba_prefix.secret).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Use an application key with <code className="font-mono">agent:invoke</code> to chat and add <code className="font-mono">agent:read</code> to read history. Create a session with <code className="font-mono">POST /api/v1/agent-sessions/&lt;AGENT_ID&gt;</code>; reuse its ID on later invocations. Sessions are isolated to the application that created them.
            </p>
            <div className="space-y-2">
              <h3 className="text-sm font-semibold">Sessions, history, and image URLs</h3>
              <pre className="p-4 bg-muted rounded-lg text-xs font-mono overflow-x-auto">{sessionExample}</pre>
              <p className="text-xs text-muted-foreground">
                Images may use either a public <code className="font-mono">url</code> or a private base64 <code className="font-mono">data</code> URI. Provide exactly one. Document attachments must use <code className="font-mono">data</code> so they can be stored and indexed.
              </p>
            </div>
            <div className="space-y-2">
              <h3 className="text-sm font-semibold">cURL Request Example</h3>
              <pre className="p-4 bg-muted rounded-lg text-xs font-mono overflow-x-auto">
                {curlExample}
              </pre>
            </div>

            <div className="space-y-2">
              <h3 className="text-sm font-semibold">Python Example</h3>
              <pre className="p-4 bg-muted rounded-lg text-xs font-mono overflow-x-auto">{pythonExample}</pre>
            </div>

            <div className="space-y-2">
              <h3 className="text-sm font-semibold">JavaScript / Fetch Example</h3>
              <pre className="p-4 bg-muted rounded-lg text-xs font-mono overflow-x-auto">
                {jsExample}
              </pre>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Published Agents</CardTitle>
            <CardDescription>Contracts below are loaded from published API configurations and pinned schema versions.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {contracts.length === 0 ? (
              <p className="text-sm text-muted-foreground">No published API agents are available.</p>
            ) : contracts.map((contract) => (
              <div key={contract.agentId} className="border p-4 space-y-3">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <h3 className="font-semibold">{contract.agentName}</h3>
                    {contract.description && <p className="text-sm text-muted-foreground">{contract.description}</p>}
                  </div>
                  <Badge>published</Badge>
                </div>
                <p className="text-xs font-mono break-all">POST /api/v1/agent-invocations/{contract.agentId}</p>
                <div className="grid gap-1 text-xs text-muted-foreground sm:grid-cols-3">
                  <span>Agent ID: <strong className="font-mono text-foreground">{contract.agentId}</strong></span>
                  <span>Agent version: <strong className="text-foreground">v{contract.agentVersion ?? "-"}</strong></span>
                  <span>Scopes: <strong className="font-mono text-foreground">{Array.isArray(contract.config.required_scopes) ? contract.config.required_scopes.join(" ") : "agent:invoke"}</strong></span>
                </div>
                <p className="text-xs text-muted-foreground">Pinned schemas: input v{contract.inputSchemaVersion ?? "-"}, output v{contract.outputSchemaVersion ?? "-"}. Responses include a session ID for continuing history.</p>
                <div className="grid gap-3 md:grid-cols-2">
                  <pre className="p-3 bg-muted text-xs overflow-x-auto">{JSON.stringify(contract.inputSchema || {}, null, 2)}</pre>
                  <pre className="p-3 bg-muted text-xs overflow-x-auto">{JSON.stringify(contract.outputSchema || {}, null, 2)}</pre>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Error Catalog</CardTitle>
            <CardDescription>
              Standard error responses returned by the contract validation layer.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="p-3 border rounded-md">
                <p className="font-mono text-xs font-semibold text-rose-500">INPUT_SCHEMA_VALIDATION_FAILED (422)</p>
                <p className="text-xs text-muted-foreground mt-1">The request body input did not conform to the agent&apos;s pinned input schema.</p>
              </div>
              <div className="p-3 border rounded-md">
                <p className="font-mono text-xs font-semibold text-rose-500">OUTPUT_SCHEMA_VALIDATION_FAILED (502)</p>
                <p className="text-xs text-muted-foreground mt-1">The agent execution or repair attempt failed to produce output matching the output schema.</p>
              </div>
              <div className="p-3 border rounded-md">
                <p className="font-mono text-xs font-semibold text-rose-500">AGENT_NOT_AVAILABLE (409)</p>
                <p className="text-xs text-muted-foreground mt-1">The agent is not currently in testing or published publication state.</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
