"use client"

import { useState, useEffect } from "react"
import {
  BookOpen,
  Code2,
  Database,
  Key,
  Layers,
  Terminal,
  Search,
  Copy,
  Check,
  ChevronRight,
  ExternalLink,
  ShieldCheck,
  Zap,
  Sparkles,
  Server,
  FileText,
  AlertCircle,
  Info,
  HelpCircle,
  Lightbulb,
  CheckCircle2,
  ArrowUpRight,
  Cpu,
  Lock,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
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

export default function DeveloperDocsPage() {
  const [activeSection, setActiveSection] = useState("overview")
  const [searchQuery, setSearchQuery] = useState("")
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [contracts, setContracts] = useState<PublishedContract[]>([])

  useEffect(() => {
    fetchExposedAgents()
  }, [])

  const fetchExposedAgents = async () => {
    try {
      const data = await apiClient.listAgents()
      const published = await Promise.all(
        data.map(async (agent) => {
          try {
            const config = await apiClient.getAgentAPIConfig(agent.id)
            if (config.publication_state !== "published") return null
            const schemas = await apiClient.listSchemas()
            const input = schemas.find(
              (schema) => String(schema.latest_version?.id) === String(config.input_schema_version_id)
            )
            const output = schemas.find(
              (schema) => String(schema.latest_version?.id) === String(config.output_schema_version_id)
            )
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
        })
      )
      setContracts(published.filter((c): c is PublishedContract => c !== null))
    } catch (err) {
      console.error("Failed to load agents for docs:", err)
    }
  }

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const backendEndpoint =
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    (typeof window !== "undefined" ? window.location.origin : "")

  // Section categories
  const docCategories = [
    {
      title: "Getting Started",
      items: [
        { id: "overview", label: "Overview & Architecture", icon: Zap },
        { id: "auth", label: "Authentication & Scopes", icon: Key },
        { id: "quickstart", label: "Quickstart Guide", icon: Terminal },
      ],
    },
    {
      title: "Knowledge Base & RAG",
      items: [
        { id: "kb-overview", label: "RAG Architecture Overview", icon: Database },
        { id: "kb-scoping", label: "Workspace vs App Scoping", icon: Layers },
        { id: "kb-upsert-api", label: "1. KB Upsert API", icon: Code2 },
        { id: "kb-ingest-api", label: "2. Document Ingestion API", icon: FileText },
        { id: "kb-search-api", label: "3. Vector Search API", icon: Search },
        { id: "kb-credentials", label: "Secrets Vault & Embeddings", icon: Lock },
        { id: "kb-maf-integration", label: "Agent MAF RAG Integration", icon: Cpu },
      ],
    },
    {
      title: "External Agent API Platform",
      items: [
        { id: "agent-invocations", label: "Agent Invocations API", icon: Sparkles },
        { id: "agent-sessions", label: "Sessions & History", icon: Server },
        { id: "published-contracts", label: "Live Agent Contracts", icon: ShieldCheck },
      ],
    },
    {
      title: "Contracts & Validation",
      items: [
        { id: "schemas", label: "JSON Schemas & Versioning", icon: FileText },
        { id: "errors", label: "Error Catalog", icon: AlertCircle },
      ],
    },
    {
      title: "SDKs & Integration Examples",
      items: [
        { id: "code-curl", label: "cURL Examples", icon: Terminal },
        { id: "code-python", label: "Python SDK", icon: Code2 },
        { id: "code-javascript", label: "JavaScript / TypeScript", icon: Code2 },
      ],
    },
    {
      title: "Platform Extensions",
      items: [
        { id: "extensions-future", label: "Tools, MCP & Extensions", icon: Lightbulb },
      ],
    },
  ]

  const filteredCategories = docCategories.map((cat) => ({
    ...cat,
    items: cat.items.filter(
      (item) =>
        item.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
        cat.title.toLowerCase().includes(searchQuery.toLowerCase())
    ),
  })).filter((cat) => cat.items.length > 0)

  return (
    <div className="flex flex-col h-full bg-background text-foreground">
      {/* Top Docs Header Bar */}
      <div className="flex items-center justify-between px-8 py-3.5 border-b border-border bg-card/60 backdrop-blur-sm sticky top-0 z-20 shrink-0">
        <div className="flex items-center gap-3">
          <div className="p-1.5 bg-primary/10 rounded-lg text-primary">
            <BookOpen className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight">Obsidian AI Developer Documentation</h1>
              <Badge variant="outline" className="text-[10px] font-mono border-primary/30 text-primary">
                v1.0 Standard
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              Microsoft Docs style reference for Knowledge Bases, RAG APIs, External Agent Contracts & Integration.
            </p>
          </div>
        </div>

        {/* Search Input */}
        <div className="relative w-64">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder="Search documentation..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 h-8 text-xs bg-background"
          />
        </div>
      </div>

      {/* Main Container */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sticky Sidebar Navigation */}
        <aside className="w-64 border-r border-border bg-muted/20 p-4 overflow-y-auto shrink-0 space-y-6">
          {filteredCategories.map((cat) => (
            <div key={cat.title}>
              <p className="px-2 mb-2 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                {cat.title}
              </p>
              <div className="space-y-0.5">
                {cat.items.map((item) => {
                  const Icon = item.icon
                  const isActive = activeSection === item.id
                  return (
                    <button
                      key={item.id}
                      onClick={() => {
                        setActiveSection(item.id)
                        const el = document.getElementById(item.id)
                        if (el) el.scrollIntoView({ behavior: "smooth" })
                      }}
                      className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors text-left ${
                        isActive
                          ? "bg-primary text-primary-foreground shadow-xs font-semibold"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                    >
                      <Icon className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{item.label}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </aside>

        {/* Center Main Content Area */}
        <main className="flex-1 overflow-y-auto p-8 space-y-12">
          {/* Section: Overview */}
          <section id="overview" className="space-y-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>Getting Started</span>
              <ChevronRight className="h-3 w-3" />
              <span className="text-foreground font-medium">Overview & Architecture</span>
            </div>
            <h2 className="text-3xl font-extrabold tracking-tight">Obsidian AI Platform Overview</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Obsidian AI is an enterprise-grade agent runtime and Model Agent Framework (MAF) platform. It provides
              a managed vector RAG pipeline, application-scoped Knowledge Bases, dynamic embedding key resolution,
              schema-validated external agent contract execution, and multi-channel orchestration.
            </p>

            {/* Architecture Cards */}
            <div className="grid gap-4 sm:grid-cols-3 pt-2">
              <Card className="bg-card/50">
                <CardHeader className="p-4 pb-2">
                  <Database className="h-5 w-5 text-primary mb-1" />
                  <CardTitle className="text-sm">Managed Vector RAG</CardTitle>
                </CardHeader>
                <CardContent className="p-4 pt-0 text-xs text-muted-foreground">
                  Qdrant vector store indexing with dynamic provider key resolution, overlap chunking, and per-KB write serialization.
                </CardContent>
              </Card>

              <Card className="bg-card/50">
                <CardHeader className="p-4 pb-2">
                  <Sparkles className="h-5 w-5 text-emerald-500 mb-1" />
                  <CardTitle className="text-sm">External Agent API</CardTitle>
                </CardHeader>
                <CardContent className="p-4 pt-0 text-xs text-muted-foreground">
                  Strict input/output JSON schema validation, contract publishing, and scoped API key authentication.
                </CardContent>
              </Card>

              <Card className="bg-card/50">
                <CardHeader className="p-4 pb-2">
                  <Lock className="h-5 w-5 text-violet-500 mb-1" />
                  <CardTitle className="text-sm">Secrets & App Scoping</CardTitle>
                </CardHeader>
                <CardContent className="p-4 pt-0 text-xs text-muted-foreground">
                  Encrypted secrets vault, multi-tenant application registration, and scope-based permissions.
                </CardContent>
              </Card>
            </div>
          </section>

          {/* Section: Authentication */}
          <section id="auth" className="space-y-4 pt-6 border-t border-border">
            <h2 className="text-2xl font-bold tracking-tight">Authentication & Scopes</h2>
            <p className="text-sm text-muted-foreground">
              All external API requests require a valid Bearer token passed in the <code className="font-mono bg-muted px-1.5 py-0.5 rounded text-xs">Authorization</code> header.
            </p>

            <div className="p-4 bg-muted/30 rounded-lg border border-border space-y-2">
              <div className="flex items-center gap-2 font-semibold text-xs text-primary">
                <Info className="h-4 w-4" />
                <span>API Key Format</span>
              </div>
              <p className="text-xs text-muted-foreground">
                Application API keys created in the Developer Portal follow the format <code className="font-mono text-foreground font-medium">oba_&lt;prefix&gt;.&lt;secret&gt;</code>. Only the bcrypt hash of the key is stored on the server.
              </p>
            </div>

            {/* Scope Table */}
            <div className="border rounded-lg overflow-hidden text-xs">
              <table className="w-full text-left">
                <thead className="bg-muted text-muted-foreground font-semibold border-b">
                  <tr>
                    <th className="p-3">Scope Name</th>
                    <th className="p-3">Description</th>
                    <th className="p-3">Required Endpoints</th>
                  </tr>
                </thead>
                <tbody className="divide-y border-border">
                  <tr>
                    <td className="p-3 font-mono font-bold text-primary">agent:invoke</td>
                    <td className="p-3">Allows invoking published agent contracts and creating sessions.</td>
                    <td className="p-3 font-mono text-muted-foreground">POST /api/v1/agent-invocations/*</td>
                  </tr>
                  <tr>
                    <td className="p-3 font-mono font-bold text-primary">agent:read</td>
                    <td className="p-3">Allows reading conversation history and past session messages.</td>
                    <td className="p-3 font-mono text-muted-foreground">GET /api/v1/agent-sessions/*</td>
                  </tr>
                  <tr>
                    <td className="p-3 font-mono font-bold text-primary">knowledge:write</td>
                    <td className="p-3">Allows upserting knowledge base metadata and ingesting documents.</td>
                    <td className="p-3 font-mono text-muted-foreground">PUT /knowledge/apps/upsert, POST /knowledge/apps/ingest</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          {/* Section: Quickstart */}
          <section id="quickstart" className="space-y-4 pt-6 border-t border-border">
            <h2 className="text-2xl font-bold tracking-tight">Quickstart Guide</h2>
            <p className="text-sm text-muted-foreground">
              Follow these three steps to register an application, issue an API key, and invoke a published agent contract:
            </p>

            <ol className="space-y-4 text-xs list-decimal list-inside text-muted-foreground font-medium">
              <li className="space-y-1">
                <strong className="text-foreground">Register an Application</strong>
                <p className="pl-5">Navigate to <code className="font-mono bg-muted px-1 py-0.5 rounded">Developer &gt; Applications</code> and create a new application entry.</p>
              </li>
              <li className="space-y-1">
                <strong className="text-foreground">Generate an API Key</strong>
                <p className="pl-5">Create a key for your application with <code className="font-mono bg-muted px-1 py-0.5 rounded">agent:invoke</code> and <code className="font-mono bg-muted px-1 py-0.5 rounded">agent:read</code> scopes. Copy the displayed secret token.</p>
              </li>
              <li className="space-y-1">
                <strong className="text-foreground">Invoke the Agent</strong>
                <p className="pl-5">Send a POST request to <code className="font-mono bg-muted px-1 py-0.5 rounded">/api/v1/agent-invocations/&lt;AGENT_ID&gt;</code> with your JSON payload.</p>
              </li>
            </ol>
          </section>

          {/* Section: KB RAG Architecture */}
          <section id="kb-overview" className="space-y-4 pt-6 border-t border-border">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>Knowledge Base & RAG</span>
              <ChevronRight className="h-3 w-3" />
              <span className="text-foreground font-medium">RAG Architecture Overview</span>
            </div>
            <h2 className="text-2xl font-bold tracking-tight">Knowledge Base RAG Platform Architecture</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              The Obsidian AI Knowledge Base platform provides high-performance retrieval-augmented generation (RAG)
              integrated into MAF agents and REST endpoints. Document contents are extracted (PDF, DOCX, TXT, MD),
              chunked with configurable overlap (500 chars / 50 overlap), embedded via dynamic runtime credentials,
              and indexed in Qdrant collections under per-KB asyncio locks.
            </p>

            <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-lg space-y-2 text-xs">
              <div className="flex items-center gap-2 font-semibold text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 className="h-4 w-4" />
                <span>Key RAG Capabilities</span>
              </div>
              <ul className="list-disc list-inside space-y-1 text-muted-foreground">
                <li><strong className="text-foreground">Dynamic Credential Resolution:</strong> Embeddings use runtime keys from the Secrets Vault without relying on server environment variables.</li>
                <li><strong className="text-foreground">Idempotent App Ingestion:</strong> Unique composite key pair <code className="font-mono">(owner_id, app_id, external_id)</code> allows safe background sync from external systems.</li>
                <li><strong className="text-foreground">MAF ContextProvider Integration:</strong> Automatically grounds conversation queries before LLM execution.</li>
              </ul>
            </div>
          </section>

          {/* Section: Workspace vs App Scoping */}
          <section id="kb-scoping" className="space-y-4 pt-6 border-t border-border">
            <h2 className="text-2xl font-bold tracking-tight">Workspace vs Application Scoping</h2>
            <p className="text-sm text-muted-foreground">
              Knowledge Bases support two primary operational scope types:
            </p>

            <div className="grid gap-4 sm:grid-cols-2 text-xs">
              <div className="p-4 border rounded-lg bg-card space-y-2">
                <div className="flex items-center gap-2 font-bold text-foreground">
                  <Badge variant="secondary">Workspace Scope</Badge>
                </div>
                <p className="text-muted-foreground leading-relaxed">
                  General-purpose knowledge base created directly in the platform UI. Accessible to workspace agents or shared across workspace users. Useful for team documentation, company policies, and static knowledge stores.
                </p>
              </div>

              <div className="p-4 border rounded-lg bg-card space-y-2">
                <div className="flex items-center gap-2 font-bold text-foreground">
                  <Badge variant="outline" className="border-primary/30 text-primary">Application Scope</Badge>
                </div>
                <p className="text-muted-foreground leading-relaxed">
                  Dedicated knowledge base tied to a specific <code className="font-mono">app_id</code> (e.g., <code className="font-mono">bug-tracker</code> or <code className="font-mono">crm-portal</code>) and <code className="font-mono">external_id</code>. Managed programmatically via REST APIs for tenant-specific or project-specific document isolation.
                </p>
              </div>
            </div>
          </section>

          {/* Section: KB Upsert API */}
          <section id="kb-upsert-api" className="space-y-4 pt-6 border-t border-border">
            <div className="flex items-center gap-2">
              <Badge className="bg-amber-600 text-white font-mono uppercase text-[10px]">PUT</Badge>
              <h2 className="text-2xl font-bold tracking-tight">1. Knowledge Base Upsert API</h2>
            </div>
            <p className="text-sm font-mono text-muted-foreground bg-muted p-2 rounded-md">
              PUT /api/knowledge/apps/upsert
            </p>
            <p className="text-sm text-muted-foreground">
              Idempotently creates or updates an application-scoped Knowledge Base. If an active KB matching <code className="font-mono">(owner_id, app_id, external_id)</code> exists, it is updated in-place (200 OK). Otherwise, a new KB is created (201 Created).
            </p>

            {/* Code Block */}
            <div className="relative">
              <Button
                size="sm"
                variant="outline"
                className="absolute right-3 top-3 h-7 text-xs gap-1.5 bg-background/80 backdrop-blur-xs z-10"
                onClick={() =>
                  copyToClipboard(
                    `curl -X PUT "${backendEndpoint}/api/knowledge/apps/upsert" \\
  -H "Authorization: Bearer oba_prefix.secret" \\
  -H "Content-Type: application/json" \\
  -d '{
    "app_id": "jira-tracker",
    "external_id": "proj-alpha",
    "name": "Project Alpha KB",
    "description": "Scoped documentation for Project Alpha",
    "embedding_provider": "google",
    "secret_id": "sec_123"
  }'`,
                    "upsert-curl"
                  )
                }
              >
                {copiedId === "upsert-curl" ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
                {copiedId === "upsert-curl" ? "Copied" : "Copy cURL"}
              </Button>
              <pre className="p-4 bg-muted rounded-lg text-xs font-mono overflow-x-auto border border-border">
{`curl -X PUT "${backendEndpoint}/api/knowledge/apps/upsert" \\
  -H "Authorization: Bearer <YOUR_API_TOKEN_OR_CLIENT_SECRET>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "app_id": "jira-tracker",
    "external_id": "proj-alpha",
    "name": "Project Alpha KB",
    "description": "Scoped documentation for Project Alpha",
    "embedding_provider": "google",
    "secret_id": "sec_123"
  }'`}
              </pre>
            </div>
          </section>

          {/* Section: KB Ingest API */}
          <section id="kb-ingest-api" className="space-y-4 pt-6 border-t border-border">
            <div className="flex items-center gap-2">
              <Badge className="bg-emerald-600 text-white font-mono uppercase text-[10px]">POST</Badge>
              <h2 className="text-2xl font-bold tracking-tight">2. Document Ingestion API</h2>
            </div>
            <p className="text-sm font-mono text-muted-foreground bg-muted p-2 rounded-md">
              POST /api/knowledge/apps/ingest
            </p>
            <p className="text-sm text-muted-foreground">
              Ingests or updates a document inside an existing application-scoped Knowledge Base. Clears previous vector chunks for <code className="font-mono">document_external_id</code> before re-indexing.
            </p>

            {/* Code Block */}
            <div className="relative">
              <Button
                size="sm"
                variant="outline"
                className="absolute right-3 top-3 h-7 text-xs gap-1.5 bg-background/80 backdrop-blur-xs z-10"
                onClick={() =>
                  copyToClipboard(
                    `curl -X POST "${backendEndpoint}/api/knowledge/apps/ingest" \\
  -H "Authorization: Bearer oba_prefix.secret" \\
  -H "Content-Type: application/json" \\
  -d '{
    "app_id": "jira-tracker",
    "external_id": "proj-alpha",
    "document_external_id": "doc-bug-101",
    "doc_type": "bug_report",
    "title": "Bug #101: Payment Gateway Timeout",
    "content": "Payment gateway times out on transactions exceeding $10,000 due to slow upstream validation.",
    "metadata": {"severity": "critical", "author": "dev-team"}
  }'`,
                    "ingest-curl"
                  )
                }
              >
                {copiedId === "ingest-curl" ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
                {copiedId === "ingest-curl" ? "Copied" : "Copy cURL"}
              </Button>
              <pre className="p-4 bg-muted rounded-lg text-xs font-mono overflow-x-auto border border-border">
{`curl -X POST "${backendEndpoint}/api/knowledge/apps/ingest" \\
  -H "Authorization: Bearer <YOUR_API_TOKEN_OR_CLIENT_SECRET>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "app_id": "jira-tracker",
    "external_id": "proj-alpha",
    "document_external_id": "doc-bug-101",
    "doc_type": "bug_report",
    "title": "Bug #101: Payment Gateway Timeout",
    "content": "Payment gateway times out on transactions exceeding $10,000 due to slow upstream validation.",
    "metadata": {"severity": "critical", "author": "dev-team"}
  }'`}
              </pre>
            </div>
          </section>

          {/* Section: KB Search API */}
          <section id="kb-search-api" className="space-y-4 pt-6 border-t border-border">
            <div className="flex items-center gap-2">
              <Badge className="bg-emerald-600 text-white font-mono uppercase text-[10px]">POST</Badge>
              <h2 className="text-2xl font-bold tracking-tight">3. Vector Search API</h2>
            </div>
            <p className="text-sm font-mono text-muted-foreground bg-muted p-2 rounded-md">
              POST /api/v1/knowledge-bases/&lt;KB_ID&gt;/search
            </p>
            <p className="text-sm text-muted-foreground">
              Queries vector embeddings for a specific knowledge base and returns top matching grounded context chunks with cosine similarity scores.
            </p>

            <pre className="p-4 bg-muted rounded-lg text-xs font-mono overflow-x-auto border border-border">
{`curl -X POST "${backendEndpoint}/api/v1/knowledge-bases/<KB_ID>/search" \\
  -H "Authorization: Bearer <YOUR_API_TOKEN>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "query": "payment gateway timeout error",
    "top_k": 5
  }'`}
            </pre>
          </section>

          {/* Section: Credentials Vault */}
          <section id="kb-credentials" className="space-y-4 pt-6 border-t border-border">
            <h2 className="text-2xl font-bold tracking-tight">Secrets Vault & Embedding Resolution</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Obsidian AI uses <code className="font-mono font-semibold text-foreground">resolve_embedding_credentials</code> to dynamically resolve API keys for RAG operations:
            </p>

            <ol className="list-decimal list-inside text-xs text-muted-foreground space-y-1.5">
              <li><strong className="text-foreground">Explicit Secret ID:</strong> If <code className="font-mono">secret_id</code> is attached to the KB, decrypts the key stored in the user's Secrets Vault.</li>
              <li><strong className="text-foreground">Active LLM Provider Fallback:</strong> If no secret is specified, looks up the user's active LLMProvider matching <code className="font-mono">embedding_provider</code> (e.g., Google Gemini or OpenAI).</li>
              <li><strong className="text-foreground">Graceful Degradation:</strong> If no credentials exist, logs a warning and uses dummy fallback credentials to prevent application crashes.</li>
            </ol>
          </section>

          {/* Section: MAF RAG Integration */}
          <section id="kb-maf-integration" className="space-y-4 pt-6 border-t border-border">
            <h2 className="text-2xl font-bold tracking-tight">Model Agent Framework (MAF) Integration</h2>
            <p className="text-sm text-muted-foreground">
              When an agent has Knowledge Bases assigned, <code className="font-mono font-semibold text-foreground">VectorStoreContextProvider</code> automatically intercepts conversation execution in the <code className="font-mono">before_run</code> phase:
            </p>

            <pre className="p-4 bg-muted rounded-lg text-xs font-mono overflow-x-auto border border-border">
{`# Automatic grounding injected into agent context instructions:

Grounded Knowledge Base Context:
[1] Payment gateway times out on transactions exceeding $10,000 due to slow upstream validation.
[2] Bug #101 workaround: split payment payloads into $5,000 chunks.

Use the above grounded knowledge to inform your response.`}
            </pre>
          </section>

          {/* Section: Agent Invocations */}
          <section id="agent-invocations" className="space-y-4 pt-6 border-t border-border">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>External Agent API</span>
              <ChevronRight className="h-3 w-3" />
              <span className="text-foreground font-medium">Agent Invocations API</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge className="bg-emerald-600 text-white font-mono uppercase text-[10px]">POST</Badge>
              <h2 className="text-2xl font-bold tracking-tight">Agent Invocations Execution API</h2>
            </div>
            <p className="text-sm font-mono text-muted-foreground bg-muted p-2 rounded-md">
              POST /api/v1/agent-invocations/&lt;AGENT_ID&gt;
            </p>
            <p className="text-sm text-muted-foreground">
              Executes a published agent contract with strict JSON schema input and output validation.
            </p>

            <pre className="p-4 bg-muted rounded-lg text-xs font-mono overflow-x-auto border border-border">
{`curl -X POST "${backendEndpoint}/api/v1/agent-invocations/123" \\
  -H "Authorization: Bearer oba_prefix.secret" \\
  -H "Content-Type: application/json" \\
  -d '{
    "input": {
      "query": "Where is my order #5001?"
    },
    "session_id": "sess_889922"
  }'`}
            </pre>
          </section>

          {/* Section: Sessions & History */}
          <section id="agent-sessions" className="space-y-4 pt-6 border-t border-border">
            <h2 className="text-2xl font-bold tracking-tight">Sessions & Conversation History</h2>
            <p className="text-sm text-muted-foreground">
              Create persistent, application-scoped sessions and retrieve message history:
            </p>

            <pre className="p-4 bg-muted rounded-lg text-xs font-mono overflow-x-auto border border-border">
{`# 1. Create a session bound to your application
POST /api/v1/agent-sessions/<AGENT_ID>

# 2. Retrieve history (requires agent:read scope)
GET /api/v1/agent-sessions/<SESSION_ID>/messages`}
            </pre>
          </section>

          {/* Section: Published Contracts */}
          <section id="published-contracts" className="space-y-4 pt-6 border-t border-border">
            <h2 className="text-2xl font-bold tracking-tight">Live Published Agent Contracts</h2>
            <p className="text-sm text-muted-foreground">
              Active published contracts currently live in your environment:
            </p>

            {contracts.length === 0 ? (
              <p className="text-xs text-muted-foreground italic">No published contracts found in current workspace.</p>
            ) : (
              <div className="grid gap-4">
                {contracts.map((c) => (
                  <Card key={c.agentId} className="border bg-card">
                    <CardHeader className="p-4 pb-2">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-sm font-bold">{c.agentName}</CardTitle>
                        <Badge className="bg-emerald-600 text-white text-[10px]">published</Badge>
                      </div>
                      <CardDescription className="text-xs">{c.description || "No description provided."}</CardDescription>
                    </CardHeader>
                    <CardContent className="p-4 pt-0 text-xs space-y-2 font-mono">
                      <p className="text-muted-foreground">POST /api/v1/agent-invocations/{c.agentId}</p>
                      <div className="flex gap-4 text-[11px] text-muted-foreground">
                        <span>Agent Version: v{c.agentVersion || 1}</span>
                        <span>Input Schema: v{c.inputSchemaVersion || 1}</span>
                        <span>Output Schema: v{c.outputSchemaVersion || 1}</span>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </section>

          {/* Section: Error Catalog */}
          <section id="errors" className="space-y-4 pt-6 border-t border-border">
            <h2 className="text-2xl font-bold tracking-tight">Error Catalog</h2>
            <p className="text-sm text-muted-foreground">
              Standard structured error responses returned by contract and RAG validation layers:
            </p>

            <div className="space-y-3 text-xs">
              <div className="p-3 border rounded-md bg-card">
                <p className="font-mono font-bold text-rose-500">INPUT_SCHEMA_VALIDATION_FAILED (422)</p>
                <p className="text-muted-foreground mt-1">Request input payload did not match the agent's pinned JSON schema contract.</p>
              </div>
              <div className="p-3 border rounded-md bg-card">
                <p className="font-mono font-bold text-rose-500">OUTPUT_SCHEMA_VALIDATION_FAILED (502)</p>
                <p className="text-muted-foreground mt-1">Agent output failed contract validation or JSON repair attempts.</p>
              </div>
              <div className="p-3 border rounded-md bg-card">
                <p className="font-mono font-bold text-rose-500">Embedding provider credentials invalid or missing (400)</p>
                <p className="text-muted-foreground mt-1">RAG embedding provider key not found in Secrets Vault or LLMProviders.</p>
              </div>
            </div>
          </section>

          {/* Section: Python SDK Example */}
          <section id="code-python" className="space-y-4 pt-6 border-t border-border">
            <h2 className="text-2xl font-bold tracking-tight">Python Integration Example</h2>
            <p className="text-sm text-muted-foreground">
              Full Python implementation for Knowledge Base upsert, document ingestion, and agent invocation:
            </p>

            <pre className="p-4 bg-muted rounded-lg text-xs font-mono overflow-x-auto border border-border">
{`import requests

BASE_URL = "${backendEndpoint}"
API_KEY = "oba_prefix.secret"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# 1. Upsert Knowledge Base
kb_res = requests.put(
    f"{BASE_URL}/api/knowledge/apps/upsert",
    headers=HEADERS,
    json={
        "app_id": "crm-app",
        "external_id": "customer-101",
        "name": "Customer 101 Knowledge Base",
        "description": "Enterprise customer knowledge profile",
    }
)
print("KB Upsert:", kb_res.json())

# 2. Ingest Document
doc_res = requests.post(
    f"{BASE_URL}/api/knowledge/apps/ingest",
    headers=HEADERS,
    json={
        "app_id": "crm-app",
        "external_id": "customer-101",
        "document_external_id": "contract-2026",
        "doc_type": "contract",
        "title": "Service Agreement 2026",
        "content": "SLA guarantees 99.99% uptime with 15 minute incident response window."
    }
)
print("Doc Ingest:", doc_res.json())`}
            </pre>
          </section>

          {/* Section: JavaScript Example */}
          <section id="code-javascript" className="space-y-4 pt-6 border-t border-border">
            <h2 className="text-2xl font-bold tracking-tight">JavaScript / TypeScript Example</h2>
            <p className="text-sm text-muted-foreground">
              Node.js and browser fetch snippet for agent contract invocations:
            </p>

            <pre className="p-4 bg-muted rounded-lg text-xs font-mono overflow-x-auto border border-border">
{`async function invokeAgent(agentId, query) {
  const response = await fetch(\`${backendEndpoint}/api/v1/agent-invocations/\${agentId}\`, {
    method: "POST",
    headers: {
      "Authorization": "Bearer oba_prefix.secret",
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      input: { query },
      session_id: "sess_custom_id"
    })
  });
  const data = await response.json();
  return data;
}`}
            </pre>
          </section>

          {/* Section: Future Extensions */}
          <section id="extensions-future" className="space-y-4 pt-6 border-t border-border pb-12">
            <h2 className="text-2xl font-bold tracking-tight">Platform Extensions & Future Expansion</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Obsidian AI is designed for modular growth. Additional platform capability sections will be expanded in future releases:
            </p>

            <div className="grid gap-3 sm:grid-cols-2 text-xs">
              <div className="p-3 border rounded-md bg-card">
                <p className="font-semibold text-foreground">Model Context Protocol (MCP)</p>
                <p className="text-muted-foreground mt-1">Connect local or remote stdio/SSE MCP server toolkits.</p>
              </div>
              <div className="p-3 border rounded-md bg-card">
                <p className="font-semibold text-foreground">Claude Skills Vault</p>
                <p className="text-muted-foreground mt-1">Reusable multi-file prompt capabilities for Anthropic Claude agents.</p>
              </div>
              <div className="p-3 border rounded-md bg-card">
                <p className="font-semibold text-foreground">WhatsApp Messaging Bridge</p>
                <p className="text-muted-foreground mt-1">Full-duplex text and voice messaging channels with agent delegation.</p>
              </div>
              <div className="p-3 border rounded-md bg-card">
                <p className="font-semibold text-foreground">Webhooks & Global Async Jobs</p>
                <p className="text-muted-foreground mt-1">Asynchronous background agent execution and event notifications.</p>
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>
  )
}
