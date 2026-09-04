"use client"

import { useEffect, useState } from "react"
import { useSession } from "next-auth/react"
import { useRouter } from "next/navigation"
import { apiClient } from "@/lib/api-client"
import type { KnowledgeBase, CreateKnowledgeBaseRequest } from "@/types/playground"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { BookOpen, Plus, Trash2, FileText, Globe, Loader2, AlertTriangle, Code, Layers, Filter } from "lucide-react"
import { toast } from "sonner"
import { useConfirm } from "@/hooks/use-confirm"
import { usePermissionsStore } from "@/stores/permissions-store"
import { AnimatedList, AnimatedListItem } from "@/components/ui/animated-list"

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleDateString()
}

export default function KnowledgePage() {
  const { data: authSession } = useSession()
  const router = useRouter()
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [secrets, setSecrets] = useState<any[]>([])
  const [applications, setApplications] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [scopeFilter, setScopeFilter] = useState<"all" | "workspace" | "application">("all")

  // Modal / Drawer state
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [showCodeDrawer, setShowCodeDrawer] = useState(false)
  const [selectedKBForCode, setSelectedKBForCode] = useState<KnowledgeBase | null>(null)

  // Form state
  const [createName, setCreateName] = useState("")
  const [createDescription, setCreateDescription] = useState("")
  const [createScopeType, setCreateScopeType] = useState<"workspace" | "application">("workspace")
  const [createAppId, setCreateAppId] = useState("")
  const [isCustomAppId, setIsCustomAppId] = useState(false)
  const [createExternalId, setCreateExternalId] = useState("")
  const [createProvider, setCreateProvider] = useState("google")
  const [createModel, setCreateModel] = useState("gemini-embedding-2")
  const [createSecretId, setCreateSecretId] = useState("")
  const [createShared, setCreateShared] = useState(false)
  const [createLoading, setCreateLoading] = useState(false)

  const userRole = (authSession?.user as { role?: string })?.role
  const canCreateKB = usePermissionsStore((s) => s.permissions.create_knowledge_bases)

  const [ConfirmDialog, confirmDelete] = useConfirm({
    title: "Delete knowledge base",
    description: "This will permanently delete this knowledge base and all its documents. This action cannot be undone.",
    confirmLabel: "Delete",
    variant: "destructive",
  })

  useEffect(() => {
    if (!authSession?.accessToken) return
    apiClient.setAccessToken(authSession.accessToken as string)
    load()
  }, [authSession?.accessToken])

  const load = async () => {
    setIsLoading(true)
    try {
      const [kbs, secretsList, appsList] = await Promise.all([
        apiClient.listKnowledgeBases(),
        apiClient.listSecrets().catch(() => []),
        apiClient.listApplications().catch(() => []),
      ])
      setKnowledgeBases(kbs)
      setSecrets(secretsList)
      setApplications(appsList)
    } catch {
      toast.error("Failed to load knowledge bases")
    } finally {
      setIsLoading(false)
    }
  }

  const handleCreate = async () => {
    if (!createName.trim()) return
    setCreateLoading(true)
    try {
      const kb = await apiClient.createKnowledgeBase({
        name: createName.trim(),
        description: createDescription.trim() || undefined,
        scope_type: createScopeType,
        app_id: createAppId.trim() || undefined,
        external_id: createExternalId.trim() || undefined,
        embedding_provider: createProvider,
        embedding_model: createModel,
        secret_id: createSecretId || undefined,
        is_shared: createShared,
      })
      setKnowledgeBases((prev) => [kb, ...prev])
      setShowCreateDialog(false)
      resetForm()
      toast.success("Knowledge base created")
      router.push(`/knowledge/${kb.id}`)
    } catch (err: any) {
      toast.error(err?.message || "Failed to create knowledge base")
    } finally {
      setCreateLoading(false)
    }
  }

  const resetForm = () => {
    setCreateName("")
    setCreateDescription("")
    setCreateScopeType("workspace")
    setCreateAppId("")
    setIsCustomAppId(false)
    setCreateExternalId("")
    setCreateProvider("google")
    setCreateModel("gemini-embedding-2")
    setCreateSecretId("")
    setCreateShared(false)
  }

  const handleDelete = async (kb: KnowledgeBase) => {
    const confirmed = await confirmDelete()
    if (!confirmed) return
    try {
      await apiClient.deleteKnowledgeBase(kb.id)
      setKnowledgeBases((prev) => prev.filter((k) => k.id !== kb.id))
      toast.success("Knowledge base deleted")
    } catch (err: any) {
      toast.error(err?.message || "Failed to delete knowledge base")
    }
  }

  const handleDialogClose = (open: boolean) => {
    if (!open) {
      resetForm()
    }
    setShowCreateDialog(open)
  }

  const secretIdsSet = new Set(secrets.map((s) => String(s.id)))

  const filteredKnowledgeBases = knowledgeBases.filter((kb) => {
    if (scopeFilter === "workspace") return kb.scope_type === "workspace" || (!kb.app_id && !kb.external_id)
    if (scopeFilter === "application") return kb.scope_type === "application" || Boolean(kb.app_id || kb.external_id)
    return true
  })

  return (
    <div className="flex flex-col h-full">
      <ConfirmDialog />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 px-6 py-4 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <BookOpen className="h-5 w-5 text-muted-foreground" />
          <h1 className="text-2xl font-bold tracking-tight uppercase">Knowledge Bases</h1>
        </div>

        <div className="flex items-center gap-3">
          {/* Scope Filter */}
          <div className="flex items-center bg-muted/50 p-1 rounded-lg border border-border gap-1 text-xs">
            <Filter className="h-3.5 w-3.5 text-muted-foreground ml-1.5" />
            <button
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${scopeFilter === "all" ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"}`}
              onClick={() => setScopeFilter("all")}
            >
              All
            </button>
            <button
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${scopeFilter === "workspace" ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"}`}
              onClick={() => setScopeFilter("workspace")}
            >
              Workspace
            </button>
            <button
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${scopeFilter === "application" ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"}`}
              onClick={() => setScopeFilter("application")}
            >
              Application-Specific
            </button>
          </div>

          {canCreateKB && (
            <Button size="sm" className="h-9" onClick={() => setShowCreateDialog(true)}>
              <Plus className="h-4 w-4 mr-1.5" />
              New Knowledge Base
            </Button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoading ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : filteredKnowledgeBases.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-60 gap-3 text-center">
            <BookOpen className="h-10 w-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              {knowledgeBases.length === 0 ? "No knowledge bases yet." : "No knowledge bases match the selected filter."}
            </p>
            {canCreateKB && (
              <Button size="sm" variant="outline" className="h-9" onClick={() => setShowCreateDialog(true)}>
                <Plus className="h-4 w-4 mr-1.5" />
                Create a knowledge base
              </Button>
            )}
          </div>
        ) : (
          <AnimatedList className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filteredKnowledgeBases.map((kb) => {
              const isMissingSecret = kb.secret_id && !secretIdsSet.has(String(kb.secret_id))

              return (
                <AnimatedListItem key={kb.id}>
                  <Card
                    className="cursor-pointer hover:bg-muted/30 transition-colors flex flex-col justify-between h-full"
                    onClick={() => router.push(`/knowledge/${kb.id}`)}
                  >
                    <CardHeader className="pb-2">
                      <div className="flex items-start justify-between gap-2">
                        <CardTitle className="text-base font-semibold leading-snug">{kb.name}</CardTitle>
                        <div className="flex flex-wrap items-center gap-1 shrink-0">
                          {kb.is_shared && (
                            <Badge variant="secondary" className="text-xs gap-1">
                              <Globe className="h-3 w-3" />
                              Shared
                            </Badge>
                          )}
                          {kb.app_id && (
                            <Badge variant="outline" className="text-xs gap-1 border-primary/30 text-primary bg-primary/5">
                              <Layers className="h-3 w-3" />
                              App: {kb.app_id}
                            </Badge>
                          )}
                          {kb.external_id && (
                            <Badge variant="outline" className="text-xs bg-muted/50">
                              Ext ID: {kb.external_id}
                            </Badge>
                          )}
                          {isMissingSecret && (
                            <Badge variant="destructive" className="text-xs gap-1">
                              <AlertTriangle className="h-3 w-3" />
                              Credentials Missing
                            </Badge>
                          )}
                        </div>
                      </div>
                    </CardHeader>

                    <CardContent className="pt-0">
                      {kb.description && (
                        <p className="text-sm text-muted-foreground mb-3 line-clamp-2">{kb.description}</p>
                      )}

                      <div className="flex items-center justify-between mt-auto pt-2 border-t border-border/50">
                        <div className="flex items-center gap-1 text-sm text-muted-foreground">
                          <FileText className="h-3.5 w-3.5" />
                          <span>{kb.document_count} document{kb.document_count !== 1 ? "s" : ""}</span>
                        </div>

                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-muted-foreground hover:text-foreground cursor-pointer"
                            title="Application Integration Snippets"
                            onClick={(e) => {
                              e.stopPropagation()
                              setSelectedKBForCode(kb)
                              setShowCodeDrawer(true)
                            }}
                          >
                            <Code className="h-3.5 w-3.5" />
                          </Button>

                          <span className="text-xs text-muted-foreground ml-1">{formatDate(kb.created_at)}</span>

                          {canCreateKB && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-muted-foreground hover:text-destructive cursor-pointer"
                              onClick={(e) => {
                                e.stopPropagation()
                                handleDelete(kb)
                              }}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </AnimatedListItem>
              )
            })}
          </AnimatedList>
        )}
      </div>

      {/* Create Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={handleDialogClose}>
        <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Create Knowledge Base</DialogTitle>
            <DialogDescription>
              Configure application scope and runtime embedding credentials for RAG indexing.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-3">
            <div className="grid gap-2">
              <Label htmlFor="kb-name">Name</Label>
              <Input
                id="kb-name"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder="e.g. Bug Tracker Knowledge Base"
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="kb-description">Description</Label>
              <Textarea
                id="kb-description"
                value={createDescription}
                onChange={(e) => setCreateDescription(e.target.value)}
                placeholder="Describe what this knowledge base contains..."
                rows={2}
                className="resize-none"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-2">
                <Label htmlFor="kb-scope-type">Scope Type</Label>
                <select
                  id="kb-scope-type"
                  value={createScopeType}
                  onChange={(e) => setCreateScopeType(e.target.value as "workspace" | "application")}
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <option value="workspace">Workspace</option>
                  <option value="application">Application-Specific</option>
                </select>
              </div>

              <div className="grid gap-2">
                <Label htmlFor="kb-provider">Embedding Provider</Label>
                <select
                  id="kb-provider"
                  value={createProvider}
                  onChange={(e) => {
                    const p = e.target.value
                    setCreateProvider(p)
                    if (p === "google") setCreateModel("gemini-embedding-2")
                    else if (p === "openai") setCreateModel("text-embedding-3-small")
                  }}
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <option value="google">Google Gemini</option>
                  <option value="openai">OpenAI</option>
                  <option value="custom">Custom Provider</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-2">
                <Label htmlFor="kb-app-id">App Scope ID (app_id)</Label>
                <select
                  id="kb-app-id"
                  value={isCustomAppId ? "__custom__" : createAppId}
                  onChange={(e) => {
                    const val = e.target.value
                    if (val === "__custom__") {
                      setIsCustomAppId(true)
                      setCreateAppId("")
                    } else {
                      setIsCustomAppId(false)
                      setCreateAppId(val)
                    }
                  }}
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <option value="">-- None / Select App --</option>
                  {applications.map((app) => (
                    <option key={app.id} value={app.id}>
                      {app.name} (ID: {app.id})
                    </option>
                  ))}
                  <option value="__custom__">+ Custom App Scope ID...</option>
                </select>
                {isCustomAppId && (
                  <Input
                    id="kb-custom-app-id"
                    value={createAppId}
                    onChange={(e) => setCreateAppId(e.target.value)}
                    placeholder="e.g. bug-tracker"
                    className="mt-1"
                  />
                )}
              </div>

              <div className="grid gap-2">
                <Label htmlFor="kb-ext-id">External Reference ID</Label>
                <Input
                  id="kb-ext-id"
                  value={createExternalId}
                  onChange={(e) => setCreateExternalId(e.target.value)}
                  placeholder="e.g. proj-99"
                />
              </div>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="kb-secret-id">Runtime Embedding Secret (Secrets Vault)</Label>
              <select
                id="kb-secret-id"
                value={createSecretId}
                onChange={(e) => setCreateSecretId(e.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring"
              >
                <option value="">-- Active Provider Default --</option>
                {secrets.map((sec) => (
                  <option key={sec.id} value={sec.id}>
                    {sec.name} ({sec.secret_type || "api_key"})
                  </option>
                ))}
              </select>
            </div>

            {userRole === "admin" && (
              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="kb-shared"
                  checked={createShared}
                  onChange={(e) => setCreateShared(e.target.checked)}
                  className="h-4 w-4 rounded border-border"
                />
                <Label htmlFor="kb-shared" className="cursor-pointer text-sm">
                  Share with all workspace users
                </Label>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={createLoading || !createName.trim()}>
              {createLoading && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
              Create Knowledge Base
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Code Snippets Drawer / Dialog */}
      <Dialog open={showCodeDrawer} onOpenChange={setShowCodeDrawer}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Code className="h-5 w-5" />
              Application Integration Snippets
            </DialogTitle>
            <DialogDescription>
              Use these REST API requests to dynamically upsert knowledge base metadata and ingest external documents.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-2 text-xs">
            <div>
              <Label className="text-xs font-semibold mb-1 block">1. Knowledge Base Upsert (`PUT /knowledge/apps/upsert`)</Label>
              <pre className="bg-muted p-3 rounded-md overflow-x-auto font-mono text-[11px] leading-normal border border-border">
{`curl -X PUT "${typeof window !== "undefined" ? window.location.origin : ""}/api/knowledge/apps/upsert" \\
  -H "Authorization: Bearer <YOUR_API_TOKEN_OR_CLIENT_SECRET>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "app_id": "${selectedKBForCode?.app_id || "bug-tracker"}",
    "external_id": "${selectedKBForCode?.external_id || "proj-99"}",
    "name": "${selectedKBForCode?.name || "Project Alpha KB"}",
    "description": "Scoped Knowledge Base for Project Alpha",
    "embedding_provider": "${selectedKBForCode?.embedding_provider || "google"}"
  }'`}
              </pre>
            </div>

            <div>
              <Label className="text-xs font-semibold mb-1 block">2. External Document Ingestion (`POST /knowledge/apps/ingest`)</Label>
              <pre className="bg-muted p-3 rounded-md overflow-x-auto font-mono text-[11px] leading-normal border border-border">
{`curl -X POST "${typeof window !== "undefined" ? window.location.origin : ""}/api/knowledge/apps/ingest" \\
  -H "Authorization: Bearer <YOUR_API_TOKEN_OR_CLIENT_SECRET>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "app_id": "${selectedKBForCode?.app_id || "bug-tracker"}",
    "external_id": "${selectedKBForCode?.external_id || "proj-99"}",
    "doc_type": "bug_report",
    "title": "Bug #101: High CPU Spikes",
    "content": "Background worker CPU spikes to 100% on large batch payloads."
  }'`}
              </pre>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCodeDrawer(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
