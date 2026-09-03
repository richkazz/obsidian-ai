"use client"

import { useState, useEffect } from "react"
import { Plus, Code, Layers, Trash2, Eye } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { apiClient } from "@/lib/api-client"

interface SchemaVersion {
  id: string
  schema_id: string
  version_number: number
  canonical_schema: any
  created_at: string
}

interface Schema {
  id: string
  name: string
  direction: "input" | "output"
  latest_version?: SchemaVersion
  created_at: string
}

export default function SchemasPage() {
  const [schemas, setSchemas] = useState<Schema[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [mode, setMode] = useState<"visual" | "code">("visual")

  // Form fields
  const [schemaName, setSchemaName] = useState("")
  const [direction, setDirection] = useState<"input" | "output">("input")
  const [jsonCode, setJsonCode] = useState('{\n  "type": "object",\n  "properties": {\n    "query": { "type": "string" }\n  },\n  "required": ["query"]\n}')

  // Visual mode state
  const [visualField, setVisualField] = useState("query")
  const [visualType, setVisualType] = useState("string")

  useEffect(() => {
    fetchSchemas()
  }, [])

  const fetchSchemas = async () => {
    try {
      setLoading(true)
      const data = await apiClient.get("/api/v1/schemas")
      setSchemas(data || [])
    } catch (err) {
      console.error("Failed to load schemas:", err)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      let schemaDef = {}
      if (mode === "code") {
        schemaDef = JSON.parse(jsonCode)
      } else {
        schemaDef = {
          type: "object",
          properties: {
            [visualField]: { type: visualType },
          },
          required: [visualField],
        }
      }

      await apiClient.post("/api/v1/schemas", {
        name: schemaName,
        direction,
        canonical_schema: schemaDef,
      })

      setShowCreate(false)
      setSchemaName("")
      fetchSchemas()
    } catch (err) {
      console.error("Failed to create schema:", err)
    }
  }

  return (
    <div className="flex flex-col gap-6 p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">JSON Schemas</h1>
          <p className="text-muted-foreground mt-1">
            Author and version input/output contract schemas for API-exposed agents.
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4 mr-2" />
          New Schema
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      ) : schemas.length === 0 ? (
        <Card className="p-8 text-center border-dashed">
          <CardDescription>No contract schemas created yet.</CardDescription>
          <Button className="mt-4" onClick={() => setShowCreate(true)}>
            Create Your First Schema
          </Button>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {schemas.map((s) => (
            <Card key={s.id} className="flex flex-col justify-between">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">{s.name}</CardTitle>
                  <Badge variant={s.direction === "input" ? "default" : "secondary"}>
                    {s.direction}
                  </Badge>
                </div>
                <CardDescription className="text-xs mt-1">
                  Latest: v{s.latest_version?.version_number || 1}
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <pre className="p-3 bg-muted rounded text-xs font-mono max-h-36 overflow-y-auto">
                  {JSON.stringify(s.latest_version?.canonical_schema || {}, null, 2)}
                </pre>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create Schema Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Author JSON Schema</DialogTitle>
            <DialogDescription>
              Define input or output contracts visually or in JSON Schema format.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="s-name">Schema Name</Label>
                <Input
                  id="s-name"
                  value={schemaName}
                  onChange={(e) => setSchemaName(e.target.value)}
                  placeholder="e.g. AgentInputSchema"
                  required
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

            <Tabs value={mode} onValueChange={(v) => setMode(v as "visual" | "code")}>
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="visual">Visual Builder</TabsTrigger>
                <TabsTrigger value="code">JSON Code</TabsTrigger>
              </TabsList>
              <TabsContent value="visual" className="space-y-3 pt-3">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Field Name</Label>
                    <Input value={visualField} onChange={(e) => setVisualField(e.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label>Data Type</Label>
                    <Select value={visualType} onValueChange={setVisualType}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="string">String</SelectItem>
                        <SelectItem value="number">Number</SelectItem>
                        <SelectItem value="boolean">Boolean</SelectItem>
                        <SelectItem value="object">Object</SelectItem>
                        <SelectItem value="array">Array</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </TabsContent>
              <TabsContent value="code" className="pt-3">
                <Textarea
                  value={jsonCode}
                  onChange={(e) => setJsonCode(e.target.value)}
                  rows={8}
                  className="font-mono text-xs"
                />
              </TabsContent>
            </Tabs>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowCreate(false)}>
                Cancel
              </Button>
              <Button type="submit">Create Schema</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
