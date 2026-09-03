"use client"

import { useState, useEffect } from "react"
import { BookOpen, Copy, Check, Terminal, Code, Sparkles, Shield, Cpu, AlertTriangle } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { apiClient } from "@/lib/api-client"
import type { Agent, AgentSchema } from "@/types/playground"

export default function DeveloperDocsPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)
  const [schemas, setSchemas] = useState<AgentSchema[]>([])
  const [activeTab, setActiveTab] = useState<"curl" | "ts" | "python">("curl")
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    apiClient.listAgents().then((res) => {
      setAgents(res)
      if (res.length > 0) setSelectedAgent(res[0])
    }).catch(() => {})
    apiClient.listSchemas().then(setSchemas).catch(() => {})
  }, [])

  const origin = typeof window !== "undefined" ? window.location.origin : "https://your-obsidian-domain.com"
  const agentId = selectedAgent?.id || "AGENT_ID"

  const curlCode = `curl -X POST "${origin}/api/v1/agent-invocations/${agentId}" \\
  -H "X-API-Key: oba_your_key_prefix.secret_key_here" \\
  -H "Idempotency-Key: idemp_${Date.now()}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "version": 1,
    "input": {
      "query": "Your input query here"
    }
  }'`

  const tsCode = `const response = await fetch("${origin}/api/v1/agent-invocations/${agentId}", {
  method: "POST",
  headers: {
    "X-API-Key": "oba_your_key_prefix.secret_key_here",
    "Idempotency-Key": "idemp_${Date.now()}",
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    version: 1,
    input: { query: "Your input query here" },
  }),
});

const data = await response.json();
console.log("Agent output:", data.output);`

  const pythonCode = `import requests

url = "${origin}/api/v1/agent-invocations/${agentId}"
headers = {
    "X-API-Key": "oba_your_key_prefix.secret_key_here",
    "Idempotency-Key": "idemp_${Date.now()}",
    "Content-Type": "application/json",
}
payload = {
    "version": 1,
    "input": {"query": "Your input query here"},
}

response = requests.post(url, headers=headers, json=payload)
print("Output:", response.json())`

  const getCodeSnippet = () => {
    switch (activeTab) {
      case "curl": return curlCode
      case "ts": return tsCode
      case "python": return pythonCode
    }
  }

  const copyCode = () => {
    navigator.clipboard.writeText(getCodeSnippet())
    setCopied(true)
    toast.success("Code copied to clipboard")
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="h-full overflow-y-auto p-8 w-full space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center h-10 w-10 rounded-xl bg-muted">
            <BookOpen className="h-5 w-5 text-muted-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight uppercase">In-App API Documentation</h1>
            <p className="text-sm text-muted-foreground">
              Dynamic integration code & endpoint specifications for published agent contracts
            </p>
          </div>
        </div>
      </div>

      {/* Published Agent Selector */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Cpu className="h-4 w-4 text-blue-500" />
            Select Agent Contract
          </CardTitle>
          <CardDescription>
            Choose a published agent to generate live, copy-paste code snippets
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Select
            value={selectedAgent?.id || ""}
            onValueChange={(id) => {
              const match = agents.find((a) => a.id === id)
              if (match) setSelectedAgent(match)
            }}
          >
            <SelectTrigger className="max-w-md">
              <SelectValue placeholder="Select an agent..." />
            </SelectTrigger>
            <SelectContent>
              {agents.map((a) => (
                <SelectItem key={a.id} value={a.id}>
                  {a.name} ({a.model_id || "default model"})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Interactive Code Snippets */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as any)}>
                <TabsList>
                  <TabsTrigger value="curl">cURL</TabsTrigger>
                  <TabsTrigger value="ts">TypeScript / JS</TabsTrigger>
                  <TabsTrigger value="python">Python</TabsTrigger>
                </TabsList>
              </Tabs>
              <Button variant="outline" size="sm" onClick={copyCode} className="gap-1.5 text-xs">
                {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
                Copy Code
              </Button>
            </div>
            <div className="bg-muted p-4 rounded-lg font-mono text-xs overflow-x-auto relative">
              <pre>{getCodeSnippet()}</pre>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Error Catalog & Limits */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Shield className="h-4 w-4 text-emerald-500" />
              Error Catalog
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs space-y-3">
            <div className="border rounded divide-y font-mono">
              <div className="p-2.5 flex items-center justify-between bg-muted/30">
                <span className="font-semibold text-amber-500">401 UNAUTHORIZED</span>
                <span className="text-muted-foreground font-sans">Invalid, expired, or revoked API key</span>
              </div>
              <div className="p-2.5 flex items-center justify-between">
                <span className="font-semibold text-amber-500">403 INSUFFICIENT_SCOPE</span>
                <span className="text-muted-foreground font-sans">Key lacks required scope (agent:invoke)</span>
              </div>
              <div className="p-2.5 flex items-center justify-between bg-muted/30">
                <span className="font-semibold text-amber-500">403 AGENT_ACCESS_DENIED</span>
                <span className="text-muted-foreground font-sans">Application not granted access</span>
              </div>
              <div className="p-2.5 flex items-center justify-between">
                <span className="font-semibold text-amber-500">422 INPUT_SCHEMA_VALIDATION_FAILED</span>
                <span className="text-muted-foreground font-sans">Payload failed input schema</span>
              </div>
              <div className="p-2.5 flex items-center justify-between bg-muted/30">
                <span className="font-semibold text-rose-500">502 OUTPUT_SCHEMA_VALIDATION_FAILED</span>
                <span className="text-muted-foreground font-sans">Agent output failed schema after repair</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              MVP Scope Notice
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs space-y-3 text-muted-foreground leading-relaxed">
            <p>
              <strong>Synchronous Invocation:</strong> All agent invocation calls execute synchronously in the MVP boundary with server-side JSON schema output validation and bounded repair.
            </p>
            <p>
              <strong>Async Jobs & Webhooks:</strong> Asynchronous job polling and signed webhooks are deferred for future platform releases.
            </p>
            <p>
              <strong>Idempotency Keys:</strong> Pass <code className="bg-muted px-1 py-0.5 rounded font-mono">Idempotency-Key</code> header to safely retry requests without re-executing LLM turns.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
