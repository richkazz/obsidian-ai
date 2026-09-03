"use client"

import { useState, useEffect } from "react"
import { BookOpen, Copy, Check, Code, Terminal, Layers } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { apiClient } from "@/lib/api-client"

export default function APIDocsPage() {
  const [agents, setAgents] = useState<any[]>([])
  const [copiedCode, setCopiedKey] = useState(false)

  useEffect(() => {
    fetchExposedAgents()
  }, [])

  const fetchExposedAgents = async () => {
    try {
      const data = await apiClient.listAgents()
      setAgents(data || [])
    } catch (err) {
      console.error("Failed to load agents:", err)
    }
  }

  const curlExample = `curl -X POST "https://your-domain.com/api/v1/agent-invocations/<AGENT_ID>" \\
  -H "Authorization: Bearer oba_<prefix>.<secret>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "input": {
      "query": "Hello Obsidian AI"
    }
  }'`

  const jsExample = `const response = await fetch("https://your-domain.com/api/v1/agent-invocations/<AGENT_ID>", {
  method: "POST",
  headers: {
    "Authorization": "Bearer oba_<prefix>.<secret>",
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    input: { query: "Hello Obsidian AI" }
  })
});
const data = await response.json();`

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
            <div className="space-y-2">
              <h3 className="text-sm font-semibold">cURL Request Example</h3>
              <pre className="p-4 bg-muted rounded-lg text-xs font-mono overflow-x-auto">
                {curlExample}
              </pre>
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
            <CardTitle>Error Catalog</CardTitle>
            <CardDescription>
              Standard error responses returned by the contract validation layer.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="p-3 border rounded-md">
                <p className="font-mono text-xs font-semibold text-rose-500">INPUT_SCHEMA_VALIDATION_FAILED (422)</p>
                <p className="text-xs text-muted-foreground mt-1">The request body input did not conform to the agent's pinned input schema.</p>
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
