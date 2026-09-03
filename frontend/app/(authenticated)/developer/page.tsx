"use client"

import { useState, useEffect } from "react"
import { Plus, Key, Copy, Check, Trash2, Eye, Shield, Globe, Layers, BookOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { apiClient } from "@/lib/api-client"

interface Application {
  id: string
  name: string
  description?: string
  status: string
  default_scopes: string[]
  created_at: string
}

interface APIKey {
  id: string
  name: string
  key_prefix: string
  scopes: string[]
  expires_at?: string
  revoked_at?: string
  last_used_at?: string
  created_at: string
}

export default function DeveloperPage() {
  const [activeTab, setActiveTab] = useState("applications")
  const [applications, setApplications] = useState<Application[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedApp, setSelectedApp] = useState<Application | null>(null)
  const [keys, setKeys] = useState<APIKey[]>([])

  // New Application Modal State
  const [showCreateApp, setShowCreateApp] = useState(false)
  const [appName, setAppName] = useState("")
  const [appDesc, setAppDesc] = useState("")
  const [appScopes, setAppScopes] = useState("agent:invoke")

  // New API Key Modal State
  const [showCreateKey, setShowCreateKey] = useState(false)
  const [keyName, setKeyName] = useState("")
  const [keyScopes, setKeyScopes] = useState("agent:invoke,agent:read")
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null)
  const [copiedKey, setCopiedKey] = useState(false)

  useEffect(() => {
    fetchApplications()
  }, [])

  const fetchApplications = async () => {
    try {
      setLoading(true)
      const data = await apiClient.get("/api/v1/applications")
      setApplications(data || [])
      if (data && data.length > 0 && !selectedApp) {
        setSelectedApp(data[0])
        fetchKeys(data[0].id)
      }
    } catch (err) {
      console.error("Failed to load applications:", err)
    } finally {
      setLoading(false)
    }
  }

  const fetchKeys = async (appId: string) => {
    try {
      const data = await apiClient.get(`/api/v1/applications/${appId}/keys`)
      setKeys(data || [])
    } catch (err) {
      console.error("Failed to load API keys:", err)
    }
  }

  const handleSelectApp = (app: Application) => {
    setSelectedApp(app)
    fetchKeys(app.id)
  }

  const handleCreateApp = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const scopesArr = appScopes.split(",").map((s) => s.trim()).filter(Boolean)
      const newApp = await apiClient.post("/api/v1/applications", {
        name: appName,
        description: appDesc,
        default_scopes: scopesArr,
      })
      setShowCreateApp(false)
      setAppName("")
      setAppDesc("")
      fetchApplications()
      if (newApp) {
        setSelectedApp(newApp)
        fetchKeys(newApp.id)
      }
    } catch (err) {
      console.error("Failed to create application:", err)
    }
  }

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedApp) return
    try {
      const scopesArr = keyScopes.split(",").map((s) => s.trim()).filter(Boolean)
      const res = await apiClient.post(`/api/v1/applications/${selectedApp.id}/keys`, {
        name: keyName,
        scopes: scopesArr,
      })
      setNewlyCreatedKey(res.api_key)
      setKeyName("")
      fetchKeys(selectedApp.id)
    } catch (err) {
      console.error("Failed to create key:", err)
    }
  }

  const handleRevokeKey = async (keyId: string) => {
    if (!selectedApp) return
    try {
      await apiClient.post(`/api/v1/applications/${selectedApp.id}/keys/${keyId}/revoke`, {})
      fetchKeys(selectedApp.id)
    } catch (err) {
      console.error("Failed to revoke key:", err)
    }
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedKey(true)
    setTimeout(() => setCopiedKey(false), 2000)
  }

  return (
    <div className="flex flex-col gap-6 p-8 max-w-7xl mx-auto">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Developer & API Platform</h1>
        <p className="text-muted-foreground mt-1">
          Manage application registrations, scoped API keys, schema-validated agent invocation, and integrations.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {/* Sidebar Navigation */}
        <Card className="col-span-1 border border-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Integrations
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 px-3 pb-3">
            <Button
              variant={activeTab === "applications" ? "secondary" : "ghost"}
              className="w-full justify-start gap-2 text-sm"
              onClick={() => setActiveTab("applications")}
            >
              <Globe className="h-4 w-4" />
              Applications & Keys
            </Button>
            <Button
              variant={activeTab === "schemas" ? "secondary" : "ghost"}
              className="w-full justify-start gap-2 text-sm"
              onClick={() => (window.location.href = "/developer/schemas")}
            >
              <Layers className="h-4 w-4" />
              Schemas
            </Button>
            <Button
              variant={activeTab === "docs" ? "secondary" : "ghost"}
              className="w-full justify-start gap-2 text-sm"
              onClick={() => (window.location.href = "/developer/docs")}
            >
              <BookOpen className="h-4 w-4" />
              API Documentation
            </Button>
          </CardContent>
        </Card>

        {/* Main Content Area */}
        <div className="col-span-1 md:col-span-3 space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">Registered Applications</h2>
            <Button onClick={() => setShowCreateApp(true)}>
              <Plus className="h-4 w-4 mr-2" />
              New Application
            </Button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            </div>
          ) : applications.length === 0 ? (
            <Card className="p-8 text-center border-dashed">
              <CardDescription>No applications registered yet.</CardDescription>
              <Button className="mt-4" onClick={() => setShowCreateApp(true)}>
                Register Your First Application
              </Button>
            </Card>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Applications List */}
              <div className="col-span-1 space-y-3">
                {applications.map((app) => (
                  <Card
                    key={app.id}
                    className={`cursor-pointer transition-colors hover:border-primary/50 ${
                      selectedApp?.id === app.id ? "border-primary bg-accent/30" : ""
                    }`}
                    onClick={() => handleSelectApp(app)}
                  >
                    <CardHeader className="p-4">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-base">{app.name}</CardTitle>
                        <Badge variant={app.status === "active" ? "default" : "secondary"}>
                          {app.status}
                        </Badge>
                      </div>
                      {app.description && (
                        <CardDescription className="text-xs line-clamp-2 mt-1">
                          {app.description}
                        </CardDescription>
                      )}
                    </CardHeader>
                  </Card>
                ))}
              </div>

              {/* API Keys for Selected Application */}
              <Card className="col-span-1 lg:col-span-2">
                <CardHeader className="flex flex-row items-center justify-between">
                  <div>
                    <CardTitle className="text-lg">{selectedApp?.name} - API Keys</CardTitle>
                    <CardDescription className="text-xs mt-1">
                      Manage secret API keys issued for {selectedApp?.name}.
                    </CardDescription>
                  </div>
                  <Button size="sm" onClick={() => setShowCreateKey(true)}>
                    <Key className="h-4 w-4 mr-2" />
                    Create Key
                  </Button>
                </CardHeader>
                <CardContent className="space-y-4">
                  {keys.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-4 text-center">
                      No API keys created for this application yet.
                    </p>
                  ) : (
                    <div className="space-y-3">
                      {keys.map((k) => (
                        <div
                          key={k.id}
                          className="flex items-center justify-between p-3 border rounded-lg bg-card"
                        >
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <p className="font-medium text-sm">{k.name}</p>
                              <code className="text-xs font-mono bg-muted px-1.5 py-0.5 rounded">
                                {k.key_prefix}...
                              </code>
                              {k.revoked_at && <Badge variant="destructive">Revoked</Badge>}
                            </div>
                            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                              <span>Scopes: {k.scopes.join(", ")}</span>
                              <span>•</span>
                              <span>
                                Created: {new Date(k.created_at).toLocaleDateString()}
                              </span>
                            </div>
                          </div>
                          {!k.revoked_at && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-destructive hover:text-destructive"
                              onClick={() => handleRevokeKey(k.id)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </div>

      {/* Create Application Dialog */}
      <Dialog open={showCreateApp} onOpenChange={setShowCreateApp}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Register New Application</DialogTitle>
            <DialogDescription>
              Create an application container to manage API keys and agent invocation access.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreateApp} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="app-name">Application Name</Label>
              <Input
                id="app-name"
                value={appName}
                onChange={(e) => setAppName(e.target.value)}
                placeholder="e.g. Customer Portal Integration"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="app-desc">Description</Label>
              <Textarea
                id="app-desc"
                value={appDesc}
                onChange={(e) => setAppDesc(e.target.value)}
                placeholder="Brief summary of what this application does"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="app-scopes">Default Scopes (comma-separated)</Label>
              <Input
                id="app-scopes"
                value={appScopes}
                onChange={(e) => setAppScopes(e.target.value)}
                placeholder="agent:invoke, agent:read"
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowCreateApp(false)}>
                Cancel
              </Button>
              <Button type="submit">Register Application</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Create API Key Dialog */}
      <Dialog
        open={showCreateKey}
        onOpenChange={(open) => {
          setShowCreateKey(open)
          if (!open) setNewlyCreatedKey(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create API Key for {selectedApp?.name}</DialogTitle>
            <DialogDescription>
              Generate a secret API key. The key secret will be revealed exactly ONCE upon creation.
            </DialogDescription>
          </DialogHeader>

          {newlyCreatedKey ? (
            <div className="space-y-4 py-2">
              <div className="p-3 bg-amber-500/10 border border-amber-500/20 text-amber-600 rounded-md text-xs font-medium">
                Warning: Store this key safely. It will NEVER be shown again!
              </div>
              <div className="flex items-center gap-2">
                <code className="flex-1 p-2 bg-muted rounded border text-xs font-mono break-all">
                  {newlyCreatedKey}
                </code>
                <Button size="icon" variant="outline" onClick={() => copyToClipboard(newlyCreatedKey)}>
                  {copiedKey ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
                </Button>
              </div>
              <DialogFooter>
                <Button onClick={() => setShowCreateKey(false)}>Done</Button>
              </DialogFooter>
            </div>
          ) : (
            <form onSubmit={handleCreateKey} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="key-name">Key Label / Name</Label>
                <Input
                  id="key-name"
                  value={keyName}
                  onChange={(e) => setKeyName(e.target.value)}
                  placeholder="e.g. Production Service Key"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="key-scopes">Scopes (comma-separated)</Label>
                <Input
                  id="key-scopes"
                  value={keyScopes}
                  onChange={(e) => setKeyScopes(e.target.value)}
                  placeholder="agent:invoke, agent:read"
                />
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setShowCreateKey(false)}>
                  Cancel
                </Button>
                <Button type="submit">Generate API Key</Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
