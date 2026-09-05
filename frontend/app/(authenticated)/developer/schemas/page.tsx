"use client"

import { useEffect, useState } from "react"
import { AlertCircle, Check, ChevronRight, Code2, FilePlus2, GitBranch, Plus, Save, ShieldCheck, Trash2, WandSparkles } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { apiClient } from "@/lib/api-client"

type SchemaNode = {
  type?: string
  description?: string
  properties?: Record<string, SchemaNode>
  required?: string[]
  items?: SchemaNode
  enum?: unknown[]
  additionalProperties?: boolean
  [key: string]: unknown
}

type SchemaVersion = {
  id: string
  schema_id: string
  version_number: number
  canonical_schema: SchemaNode
  source_format: string
  compatibility_mode?: string
  created_at: string
}

type SchemaRecord = {
  id: string
  name: string
  direction: "input" | "output"
  latest_version?: SchemaVersion
  created_at: string
}

type Issue = { level: "error" | "warning"; message: string }

const blankSchema = (): SchemaNode => ({
  type: "object",
  properties: { field: { type: "string" } },
  required: [],
  additionalProperties: false,
})

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value))

function schemaIssues(schema: SchemaNode, target: string): Issue[] {
  if (!schema || typeof schema !== "object" || Array.isArray(schema)) return [{ level: "error", message: "The schema must be a JSON object." }]
  const issues: Issue[] = []
  const types = ["object", "array", "string", "number", "integer", "boolean", "null"]
  if (schema.type && !types.includes(schema.type)) issues.push({ level: "error", message: `Unsupported type: ${schema.type}.` })
  if (schema.type === "object") {
    const properties = schema.properties ?? {}
    if (typeof properties !== "object" || Array.isArray(properties)) issues.push({ level: "error", message: "Object properties must be an object." })
    const names = Object.keys(properties)
    for (const required of schema.required ?? []) if (!names.includes(required)) issues.push({ level: "error", message: `Required property '${required}' is not defined.` })
    for (const [name, child] of Object.entries(properties)) for (const issue of schemaIssues(child, target)) issues.push({ ...issue, message: `${name}: ${issue.message}` })
    if (target === "openai" && schema.additionalProperties !== false) issues.push({ level: "warning", message: "OpenAI strict mode requires additionalProperties: false." })
    if (target === "openai") {
      const optional = names.filter((name) => !(schema.required ?? []).includes(name))
      if (optional.length) issues.push({ level: "warning", message: `OpenAI strict mode expects every property in required: ${optional.join(", ")}.` })
    }
  }
  if (schema.type === "array") {
    if (!schema.items || typeof schema.items !== "object") issues.push({ level: "error", message: "Array schemas need an items schema." })
    else for (const issue of schemaIssues(schema.items, target)) issues.push({ ...issue, message: `items: ${issue.message}` })
  }
  if (target === "gemini" && schema.additionalProperties === true) issues.push({ level: "warning", message: "Gemini has limited support for open-ended object properties." })
  return issues
}

function adaptSchema(schema: SchemaNode, target: string): SchemaNode {
  const next = clone(schema)
  if (next.type === "object") {
    next.properties = Object.fromEntries(Object.entries(next.properties ?? {}).map(([name, child]) => [name, adaptSchema(child, target)]))
    if (target === "openai") {
      next.additionalProperties = false
      next.required = Object.keys(next.properties)
    }
  }
  if (next.type === "array" && next.items) next.items = adaptSchema(next.items, target)
  return next
}

function NodeEditor({ node, onChange, depth = 0 }: { node: SchemaNode; onChange: (next: SchemaNode) => void; depth?: number }) {
  const type = node.type ?? "object"
  const properties = Object.entries(node.properties ?? {})
  const required = node.required ?? []
  const set = (patch: Partial<SchemaNode>) => onChange({ ...node, ...patch })
  const setType = (nextType: string) => {
    const next = { ...node, type: nextType }
    if (nextType === "object") { next.properties = node.properties ?? {}; next.required = node.required ?? [] }
    else { delete next.properties; delete next.required }
    if (nextType === "array") next.items = node.items ?? { type: "string" }
    else delete next.items
    onChange(next)
  }

  return <div className="space-y-3" style={{ marginLeft: depth ? 18 : 0 }}>
    <div className="grid gap-3 sm:grid-cols-[150px_1fr]">
      <Select value={type} onValueChange={setType}><SelectTrigger aria-label="Schema type"><SelectValue /></SelectTrigger><SelectContent>{["object", "array", "string", "number", "integer", "boolean", "null"].map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select>
      <Input placeholder="Description" value={node.description ?? ""} onChange={(event) => set({ description: event.target.value })} />
    </div>
    {type === "object" && <div className="space-y-2 rounded-md border bg-background/60 p-3">
      <div className="flex items-center justify-between"><div><p className="text-sm font-medium">Properties</p><p className="text-xs text-muted-foreground">Compose nested objects without leaving the contract.</p></div><Button type="button" size="sm" variant="outline" onClick={() => { let name = "field"; let index = 1; while ((node.properties ?? {})[name]) name = `field_${index++}`; set({ properties: { ...(node.properties ?? {}), [name]: { type: "string" } } }) }}><Plus className="mr-1 h-3.5 w-3.5" />Property</Button></div>
      {properties.map(([name, child]) => <div key={name} className="space-y-2 rounded border p-2">
        <div className="flex items-center gap-2"><Input className="h-8" value={name} aria-label={`Property name ${name}`} onChange={(event) => { const nextName = event.target.value; if (!nextName || nextName === name || (node.properties ?? {})[nextName]) return; const nextProperties = { ...(node.properties ?? {}) }; delete nextProperties[name]; nextProperties[nextName] = child; set({ properties: nextProperties, required: required.map((entry) => entry === name ? nextName : entry) }) }} /><label className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground"><input type="checkbox" checked={required.includes(name)} onChange={(event) => set({ required: event.target.checked ? [...required, name] : required.filter((entry) => entry !== name) })} /> required</label><Button type="button" size="icon-sm" variant="ghost" aria-label={`Remove ${name}`} onClick={() => { const nextProperties = { ...(node.properties ?? {}) }; delete nextProperties[name]; set({ properties: nextProperties, required: required.filter((entry) => entry !== name) }) }}><Trash2 className="h-3.5 w-3.5" /></Button></div>
        <NodeEditor node={child} depth={depth + 1} onChange={(nextChild) => set({ properties: { ...(node.properties ?? {}), [name]: nextChild } })} />
      </div>)}
      <label className="flex items-center gap-2 pt-1 text-xs text-muted-foreground"><input type="checkbox" checked={node.additionalProperties === true} onChange={(event) => set({ additionalProperties: event.target.checked })} /> allow additional properties</label>
    </div>}
    {type === "array" && <div className="rounded-md border bg-background/60 p-3"><p className="mb-2 text-sm font-medium">Array items</p><NodeEditor node={node.items ?? { type: "string" }} depth={depth + 1} onChange={(items) => set({ items })} /></div>}
    {(type === "string" || type === "number" || type === "integer") && <Textarea className="min-h-16 font-mono text-xs" placeholder='Enum values as JSON, e.g. ["draft", "published"]' value={node.enum ? JSON.stringify(node.enum, null, 2) : ""} onChange={(event) => { if (!event.target.value.trim()) return set({ enum: undefined }); try { set({ enum: JSON.parse(event.target.value) }) } catch { /* wait for valid JSON */ } }} />}
  </div>
}

export default function SchemasPage() {
  const [schemas, setSchemas] = useState<SchemaRecord[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [versions, setVersions] = useState<SchemaVersion[]>([])
  const [versionId, setVersionId] = useState<string | null>(null)
  const [schema, setSchema] = useState<SchemaNode>(blankSchema())
  const [name, setName] = useState("")
  const [direction, setDirection] = useState<"input" | "output">("input")
  const [target, setTarget] = useState("portable")
  const [jsonText, setJsonText] = useState(() => JSON.stringify(blankSchema(), null, 2))
  const [sampleText, setSampleText] = useState('{\n  "field": "example"\n}')
  const [parseError, setParseError] = useState("")
  const [serverResult, setServerResult] = useState<{ valid: boolean; errors?: { path: string; message: string }[] } | null>(null)
  const [pageError, setPageError] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [validating, setValidating] = useState(false)
  const issues = schemaIssues(schema, target)
  const errors = issues.filter((issue) => issue.level === "error")
  const warnings = issues.filter((issue) => issue.level === "warning")

  async function selectSchema(record: SchemaRecord) {
    setSelectedId(record.id); setName(record.name); setDirection(record.direction); setPageError("")
    try { const history = await apiClient.listSchemaVersions(record.id); setVersions(history || []); loadVersion(history?.[0] ?? record.latest_version) } catch (error) { setPageError(error instanceof Error ? error.message : "Unable to load schema versions") }
  }

  function loadVersion(version?: SchemaVersion) {
    if (!version) return
    const next = clone(version.canonical_schema)
    setVersionId(version.id); setSchema(next); setJsonText(JSON.stringify(next, null, 2)); setTarget(version.compatibility_mode || "portable"); setParseError(""); setServerResult(null)
  }

  async function refresh() {
    setLoading(true)
    try { const result = await apiClient.listSchemas(); setSchemas(result || []); if (!selectedId && result?.[0]) await selectSchema(result[0]) } catch (error) { setPageError(error instanceof Error ? error.message : "Unable to load schemas") } finally { setLoading(false) }
  }

  useEffect(() => {
    let active = true
    apiClient.listSchemas().then((result) => {
      if (active) setSchemas(result || [])
    }).catch((error: unknown) => {
      if (active) setPageError(error instanceof Error ? error.message : "Unable to load schemas")
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [])

  function newSchema() { const next = blankSchema(); setSelectedId(null); setVersions([]); setVersionId(null); setName(""); setDirection("input"); setTarget("portable"); setSchema(next); setJsonText(JSON.stringify(next, null, 2)); setParseError(""); setServerResult(null); setPageError("") }
  function updateSchema(next: SchemaNode) { setSchema(next); setJsonText(JSON.stringify(next, null, 2)); setParseError(""); setServerResult(null) }
  function updateJson(value: string) { setJsonText(value); setServerResult(null); try { setSchema(JSON.parse(value)); setParseError("") } catch (error) { setParseError(error instanceof Error ? error.message : "Invalid JSON") } }

  async function saveVersion() {
    if (!name.trim() || parseError || errors.length) return
    setSaving(true); setPageError("")
    try { const body = { name: name.trim(), direction, canonical_schema: schema, source_format: "json_schema", compatibility_mode: target }; const saved = selectedId ? await apiClient.createSchemaVersion(selectedId, body) : await apiClient.createSchema(body); await refresh(); if (selectedId) await selectSchema(schemas.find((record) => record.id === selectedId) as SchemaRecord); else if (saved?.id) await selectSchema(saved) } catch (error) { setPageError(error instanceof Error ? error.message : "Unable to save schema version") } finally { setSaving(false) }
  }

  async function validateSample() {
    if (!selectedId || !versionId) { setServerResult({ valid: false, errors: [{ path: "$", message: "Save a version before running server validation." }] }); return }
    try { setValidating(true); const payload = JSON.parse(sampleText); setServerResult(await apiClient.validateSchema(selectedId, versionId, payload)) } catch (error) { setServerResult({ valid: false, errors: [{ path: "$", message: error instanceof Error ? error.message : "Sample must be valid JSON" }] }) } finally { setValidating(false) }
  }

  return <div className="mx-auto flex max-w-[1500px] flex-col gap-5 p-5 lg:p-8">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Developer contracts</p><h1 className="mt-1 text-3xl font-semibold tracking-tight">Schema workshop</h1><p className="mt-1 max-w-2xl text-sm text-muted-foreground">Build, verify, and version the JSON contracts your agents expose to applications and model providers.</p></div><Button onClick={newSchema}><FilePlus2 className="mr-2 h-4 w-4" />New schema</Button></header>
    {pageError && <div role="alert" className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"><AlertCircle className="h-4 w-4" />{pageError}</div>}
    <div className="grid min-h-[700px] gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
      <Card className="h-fit overflow-hidden"><CardHeader className="border-b bg-muted/20 pb-4"><CardTitle className="text-sm">Schema library</CardTitle><CardDescription>{schemas.length} contract{schemas.length === 1 ? "" : "s"}</CardDescription></CardHeader><ScrollArea className="max-h-[620px]"><CardContent className="space-y-1 p-2">{loading ? <p className="p-3 text-sm text-muted-foreground">Loading...</p> : schemas.length === 0 ? <p className="p-3 text-sm text-muted-foreground">Start with a new schema.</p> : schemas.map((record) => <button key={record.id} onClick={() => void selectSchema(record)} className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm ${selectedId === record.id ? "bg-primary/10 text-primary" : "hover:bg-muted"}`}><span className="min-w-0"><span className="block truncate font-medium">{record.name}</span><span className="text-xs text-muted-foreground">{record.direction} · v{record.latest_version?.version_number ?? "-"}</span></span><ChevronRight className="h-4 w-4 shrink-0" /></button>)}</CardContent></ScrollArea></Card>
      <main className="min-w-0 space-y-5"><Card><CardContent className="grid gap-4 p-5 md:grid-cols-[minmax(0,1fr)_150px_190px] md:items-end"><div className="space-y-2"><Label htmlFor="schema-name">Schema name</Label><Input id="schema-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="OrderResponse" /></div><div className="space-y-2"><Label>Direction</Label><Select value={direction} onValueChange={(value: "input" | "output") => setDirection(value)} disabled={Boolean(selectedId)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="input">Input</SelectItem><SelectItem value="output">Output</SelectItem></SelectContent></Select></div><div className="space-y-2"><Label>Provider profile</Label><Select value={target} onValueChange={setTarget}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="portable">Portable JSON Schema</SelectItem><SelectItem value="openai">ChatGPT / OpenAI strict</SelectItem><SelectItem value="gemini">Gemini structured output</SelectItem><SelectItem value="anthropic">Anthropic structured output</SelectItem></SelectContent></Select></div></CardContent></Card>
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_310px]"><Card className="min-w-0"><CardHeader className="flex-row items-center justify-between space-y-0 border-b pb-3"><div><CardTitle className="text-base">Contract editor</CardTitle><CardDescription>{selectedId ? `Editing a new version of ${name}` : "Unsaved schema"}</CardDescription></div><div className="flex gap-2"><Button variant="outline" size="sm" onClick={() => updateSchema(adaptSchema(schema, target))} disabled={target === "portable"}><WandSparkles className="mr-1 h-3.5 w-3.5" />Adapt</Button><Button size="sm" onClick={() => void saveVersion()} disabled={saving || !name.trim() || Boolean(parseError) || errors.length > 0}><Save className="mr-1 h-3.5 w-3.5" />{saving ? "Saving..." : selectedId ? "Create version" : "Save schema"}</Button></div></CardHeader><CardContent className="p-0"><Tabs defaultValue="builder"><TabsList className="m-4 mb-0"><TabsTrigger value="builder"><GitBranch className="mr-1.5 h-3.5 w-3.5" />Builder</TabsTrigger><TabsTrigger value="json"><Code2 className="mr-1.5 h-3.5 w-3.5" />JSON</TabsTrigger></TabsList><TabsContent value="builder" className="m-0 p-4"><NodeEditor node={schema} onChange={updateSchema} /></TabsContent><TabsContent value="json" className="m-0 p-4"><Textarea value={jsonText} onChange={(event) => updateJson(event.target.value)} className="min-h-[520px] font-mono text-xs leading-5" spellCheck={false} />{parseError && <p className="mt-2 flex items-center gap-1 text-xs text-destructive"><AlertCircle className="h-3.5 w-3.5" />{parseError}</p>}</TabsContent></Tabs></CardContent></Card>
          <aside className="space-y-5"><Card><CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-base"><ShieldCheck className="h-4 w-4 text-primary" />Compatibility</CardTitle><CardDescription>{target === "portable" ? "Draft 2020-12 checks" : `Rules for ${target}`}</CardDescription></CardHeader><CardContent className="space-y-2">{issues.length === 0 ? <p className="flex items-center gap-2 text-sm text-emerald-600"><Check className="h-4 w-4" />Ready for this profile</p> : issues.map((issue, index) => <div key={`${issue.message}-${index}`} className={`flex gap-2 text-xs ${issue.level === "error" ? "text-destructive" : "text-amber-700 dark:text-amber-400"}`}><AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span>{issue.message}</span></div>)}{warnings.length > 0 && errors.length === 0 && <p className="pt-1 text-xs text-muted-foreground">Warnings can be adapted before saving.</p>}</CardContent></Card>
            <Card><CardHeader className="pb-3"><CardTitle className="text-base">Version history</CardTitle><CardDescription>Versions are immutable after saving.</CardDescription></CardHeader><CardContent className="space-y-1">{versions.length === 0 ? <p className="text-sm text-muted-foreground">No saved versions.</p> : versions.map((version) => <button key={version.id} onClick={() => loadVersion(version)} className={`flex w-full items-center justify-between rounded px-2 py-2 text-left text-sm ${version.id === versionId ? "bg-primary/10 text-primary" : "hover:bg-muted"}`}><span>Version {version.version_number}</span><Badge variant="outline">{version.compatibility_mode || "portable"}</Badge></button>)}</CardContent></Card>
            <Card><CardHeader className="pb-3"><CardTitle className="text-base">Verify a payload</CardTitle><CardDescription>Run a saved version through the server validator.</CardDescription></CardHeader><CardContent className="space-y-3"><Textarea value={sampleText} onChange={(event) => setSampleText(event.target.value)} className="min-h-28 font-mono text-xs" spellCheck={false} /><Button className="w-full" variant="outline" onClick={() => void validateSample()} disabled={validating}><Check className="mr-2 h-4 w-4" />{validating ? "Checking..." : "Validate payload"}</Button>{serverResult && <div className={`rounded-md border p-2 text-xs ${serverResult.valid ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700" : "border-destructive/30 bg-destructive/10 text-destructive"}`}>{serverResult.valid ? "Payload matches this version." : (serverResult.errors ?? []).map((error) => <p key={`${error.path}-${error.message}`}><strong>{error.path}</strong> {error.message}</p>)}</div>}</CardContent></Card></aside>
        </div>
      </main>
    </div>
  </div>
}