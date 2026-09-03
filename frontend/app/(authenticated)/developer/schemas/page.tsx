"use client"

import { useState, useEffect } from "react"
import { useSession } from "next-auth/react"
import { FileCode, Plus, Check, AlertCircle, Trash2, Eye, ArrowRight, Code } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { useDeveloperStore } from "@/stores/developer-store"
import type { AgentSchema } from "@/types/playground"

interface FieldDefinition {
  name: string
  type: "string" | "number" | "integer" | "boolean" | "array" | "object"
  description: string
  required: boolean
}

export default function SchemasPage() {
  const { schemas, isLoading, fetchSchemas, createSchema, createSchemaVersion, validateSchemaPayload } = useDeveloperStore()

  const [searchQuery, setSearchQuery] = useState("")
  const [showCreateDialog, setShowCreateDialog] = useState(false)

  // Builder mode
  const [authorMode, setAuthorMode] = useState<"visual" | "code">("visual")

  // Form states
  const [schemaName, setSchemaName] = useState("")
  const [direction, setDirection] = useState<"input" | "output">("input")
  const [fields, setFields] = useState<FieldDefinition[]>([
    { name: "message", type: "string", description: "Main text field", required: true },
  ])
  const [rawJsonSchema, setRawJsonSchema] = useState(`{
  "type": "object",
  "properties": {
    "message": { "type": "string", "description": "Main text field" }
  },
  "required": ["message"]
}`)

  // Validation tester state
  const [testSchema, setTestSchema] = useState<AgentSchema | null>(null)
  const [testPayload, setTestPayload] = useState('{\n  "message": "hello world"\n}')
  const [testResult, setTestResult] = useState<{ valid: boolean; errors: any[] } | null>(null)
  const [validating, setValidating] = useState(false)

  useEffect(() => {
    fetchSchemas()
  }, [fetchSchemas])

  const addField = () => {
    setFields([...fields, { name: "", type: "string", description: "", required: false }])
  }

  const removeField = (index: number) => {
    setFields(fields.filter((_, i) => i !== index))
  }

  const updateField = (index: number, key: keyof FieldDefinition, value: any) => {
    const updated = [...fields]
    updated[index] = { ...updated[index], [key]: value }
    setFields(updated)
  }

  const buildJsonFromFields = () => {
    const properties: Record<string, any> = {}
    const required: string[] = []

    fields.forEach((f) => {
      if (f.name.trim()) {
        properties[f.name.trim()] = {
          type: f.type,
          description: f.description || undefined,
        }
        if (f.required) {
          required.push(f.name.trim())
        }
      }
    })

    return {
      type: "object",
      properties,
      required: required.length > 0 ? required : undefined,
    }
  }

  const handleCreateSchema = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!schemaName.trim()) return

    let canonical: Record<string, any>
    if (authorMode === "visual") {
      canonical = buildJsonFromFields()
    } else {
      try {
        canonical = JSON.parse(rawJsonSchema)
      } catch (err) {
        toast.error("Invalid JSON Schema format")
        return
      }
    }

    try {
      await createSchema({
        name: schemaName.trim(),
        direction,
        canonical_schema: canonical,
      })
      toast.success("Schema created successfully")
      setShowCreateDialog(false)
      setSchemaName("")
    } catch (err: any) {
      toast.error(err.message || "Failed to create schema")
    }
  }

  const handleTestValidation = async () => {
    if (!testSchema || !testSchema.latest_version) return
    let parsedPayload: object
    try {
      parsedPayload = JSON.parse(testPayload)
    } catch (err) {
      toast.error("Test payload is not valid JSON")
      return
    }

    setValidating(true)
    try {
      const res = await validateSchemaPayload(testSchema.id, testSchema.latest_version.id, parsedPayload)
      setTestResult(res)
    } catch (err: any) {
      toast.error(err.message || "Validation request failed")
    } finally {
      setValidating(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-8 w-full space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center h-10 w-10 rounded-xl bg-muted">
            <FileCode className="h-5 w-5 text-muted-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight uppercase">JSON Schemas</h1>
            <p className="text-sm text-muted-foreground">
              Define input and output schemas for external agent API invocations
            </p>
          </div>
        </div>
        <Button onClick={() => setShowCreateDialog(true)}>
          <Plus className="h-4 w-4 mr-2" />
          New Schema
        </Button>
      </div>

      {/* Schema Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {schemas.map((s) => (
          <Card key={s.id} className="hover:border-primary/50 transition-colors">
            <CardHeader className="flex flex-row items-start justify-between pb-2">
              <div>
                <CardTitle className="text-base">{s.name}</CardTitle>
                <CardDescription className="text-xs uppercase mt-0.5">{s.direction} schema</CardDescription>
              </div>
              <Badge variant={s.direction === "input" ? "default" : "secondary"}>
                v{s.latest_version?.version_number || 1}
              </Badge>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="bg-muted p-2 rounded text-xs font-mono max-h-32 overflow-y-auto">
                <pre>{JSON.stringify(s.latest_version?.canonical_schema || {}, null, 2)}</pre>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="w-full text-xs"
                onClick={() => {
                  setTestSchema(s)
                  setTestResult(null)
                }}
              >
                <Eye className="h-3.5 w-3.5 mr-1" />
                Test Validation
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Create Schema Modal */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Create JSON Schema</DialogTitle>
            <DialogDescription>Define field rules for agent inputs or outputs.</DialogDescription>
          </DialogHeader>

          <div className="space-y-4 overflow-y-auto flex-1 pr-1">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Schema Name</Label>
                <Input
                  value={schemaName}
                  onChange={(e) => setSchemaName(e.target.value)}
                  placeholder="e.g. Customer Query Schema"
                />
              </div>
              <div className="space-y-2">
                <Label>Direction</Label>
                <Select value={direction} onValueChange={(v: "input" | "output") => setDirection(v)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="input">Input Schema</SelectItem>
                    <SelectItem value="output">Output Schema</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Tabs value={authorMode} onValueChange={(v) => setAuthorMode(v as "visual" | "code")}>
              <TabsList className="w-full grid grid-cols-2">
                <TabsTrigger value="visual">Visual Builder</TabsTrigger>
                <TabsTrigger value="code">Code Mode (JSON Schema)</TabsTrigger>
              </TabsList>

              <TabsContent value="visual" className="space-y-3 pt-3">
                <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                  {fields.map((f, i) => (
                    <div key={i} className="flex items-center gap-2 border p-2 rounded">
                      <Input
                        value={f.name}
                        onChange={(e) => updateField(i, "name", e.target.value)}
                        placeholder="Field name"
                        className="h-8 text-xs flex-1"
                      />
                      <Select value={f.type} onValueChange={(v) => updateField(i, "type", v)}>
                        <SelectTrigger className="h-8 text-xs w-28">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="string">string</SelectItem>
                          <SelectItem value="number">number</SelectItem>
                          <SelectItem value="integer">integer</SelectItem>
                          <SelectItem value="boolean">boolean</SelectItem>
                          <SelectItem value="array">array</SelectItem>
                          <SelectItem value="object">object</SelectItem>
                        </SelectContent>
                      </Select>
                      <Input
                        value={f.description}
                        onChange={(e) => updateField(i, "description", e.target.value)}
                        placeholder="Description"
                        className="h-8 text-xs flex-1"
                      />
                      <div className="flex items-center gap-1">
                        <Label className="text-[10px]">Req</Label>
                        <Switch
                          checked={f.required}
                          onCheckedChange={(v) => updateField(i, "required", v)}
                        />
                      </div>
                      <Button size="icon-sm" variant="ghost" onClick={() => removeField(i)}>
                        <Trash2 className="h-3.5 w-3.5 text-destructive" />
                      </Button>
                    </div>
                  ))}
                </div>
                <Button variant="outline" size="sm" onClick={addField} className="text-xs">
                  <Plus className="h-3.5 w-3.5 mr-1" />
                  Add Field
                </Button>
              </TabsContent>

              <TabsContent value="code" className="pt-3">
                <Textarea
                  value={rawJsonSchema}
                  onChange={(e) => setRawJsonSchema(e.target.value)}
                  className="font-mono text-xs h-60"
                  placeholder="Paste JSON Schema here..."
                />
              </TabsContent>
            </Tabs>
          </div>

          <DialogFooter className="pt-3 border-t">
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>Cancel</Button>
            <Button onClick={handleCreateSchema}>Create Schema</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Validation Test Dialog */}
      <Dialog open={!!testSchema} onOpenChange={(o) => { if (!o) setTestSchema(null) }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Test Payload Validation</DialogTitle>
            <DialogDescription>Validate sample JSON payloads against {testSchema?.name}.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Label className="text-xs">JSON Payload</Label>
            <Textarea
              value={testPayload}
              onChange={(e) => setTestPayload(e.target.value)}
              className="font-mono text-xs h-36"
            />
            {testResult && (
              <div className={`p-3 rounded text-xs border ${testResult.valid ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600" : "bg-destructive/10 border-destructive/30 text-destructive"}`}>
                <div className="font-semibold flex items-center gap-1.5">
                  {testResult.valid ? <Check className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                  {testResult.valid ? "Payload is valid against schema" : "Validation Failed"}
                </div>
                {!testResult.valid && (
                  <pre className="mt-2 text-[10px] font-mono whitespace-pre-wrap">{JSON.stringify(testResult.errors, null, 2)}</pre>
                )}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTestSchema(null)}>Close</Button>
            <Button onClick={handleTestValidation} disabled={validating}>
              {validating ? "Validating..." : "Run Validation"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
