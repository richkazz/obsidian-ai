"use client"

import { useState, useEffect } from "react"
import { useSession } from "next-auth/react"
import { Code2, Plus, Key, Copy, Check, ShieldAlert, Trash2, Eye, ExternalLink } from "lucide-react"
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
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { useDeveloperStore } from "@/stores/developer-store"
import type { Application, ApplicationAPIKey } from "@/types/playground"

export default function DeveloperPage() {
  const { data: session } = useSession()
  const {
    applications,
    selectedAppKeys,
    isLoading,
    oneTimeSecret,
    fetchApplications,
    createApplication,
    fetchApplicationKeys,
    createApplicationKey,
    revokeApplicationKey,
    clearOneTimeSecret,
  } = useDeveloperStore()

  const [selectedApp, setSelectedApp] = useState<Application | null>(null)
  const [showAppDialog, setShowCreateAppDialog] = useState(false)
  const [showKeyDialog, setShowCreateKeyDialog] = useState(false)

  // Form states
  const [appName, setAppName] = useState("")
  const [appDesc, setAppDesc] = useState("")
  const [keyName, setKeyName] = useState("")
  const [keyScopes, setKeyScopes] = useState("agent:invoke")
  const [copiedSecret, setCopiedSecret] = useState(false)

  useEffect(() => {
    fetchApplications()
  }, [fetchApplications])

  useEffect(() => {
    if (applications.length > 0 && !selectedApp) {
      setSelectedApp(applications[0])
      fetchApplicationKeys(applications[0].id)
    }
  }, [applications, selectedApp, fetchApplicationKeys])

  const handleSelectApp = (app: Application) => {
    setSelectedApp(app)
    fetchApplicationKeys(app.id)
  }

  const handleCreateApp = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!appName.trim()) return
    try {
      const app = await createApplication({
        name: appName.trim(),
        description: appDesc.trim() || undefined,
        default_scopes: ["agent:invoke"],
      })
      toast.success("Application registered successfully")
      setShowCreateAppDialog(false)
      setAppName("")
      setAppDesc("")
      handleSelectApp(app)
    } catch (err: any) {
      toast.error(err.message || "Failed to create application")
    }
  }

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedApp || !keyName.trim()) return
    try {
      const scopes = keyScopes.split(",").map((s) => s.trim()).filter(Boolean)
      await createApplicationKey(selectedApp.id, {
        name: keyName.trim(),
        scopes: scopes.length > 0 ? scopes : ["agent:invoke"],
      })
      toast.success("API key created")
      setShowCreateKeyDialog(false)
      setKeyName("")
    } catch (err: any) {
      toast.error(err.message || "Failed to create key")
    }
  }

  const handleRevokeKey = async (keyId: string, name: string) => {
    if (!selectedApp || !confirm(`Revoke API key "${name}"? This action cannot be undone.`)) return
    try {
      await revokeApplicationKey(selectedApp.id, keyId)
      toast.success("API key revoked")
    } catch (err: any) {
      toast.error(err.message || "Failed to revoke key")
    }
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedSecret(true)
    toast.success("Copied to clipboard")
    setTimeout(() => setCopiedSecret(false), 2000)
  }

  return (
    <div className="h-full overflow-y-auto p-8 w-full space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center h-10 w-10 rounded-xl bg-muted">
            <Code2 className="h-5 w-5 text-muted-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight uppercase">Developer & Integrations</h1>
            <p className="text-sm text-muted-foreground">
              Register applications, issue scoped API keys, manage schemas, and view deployment documentation
            </p>
          </div>
        </div>
      </div>

      {/* Main Content Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
        {/* Left Column: Applications List */}
        <Card className="lg:col-span-1 h-fit">
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <div>
              <CardTitle className="text-base uppercase">Applications</CardTitle>
              <CardDescription>Registered client apps</CardDescription>
            </div>
            <Button size="icon-sm" onClick={() => setShowCreateAppDialog(true)}>
              <Plus className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent className="space-y-2 px-3 pb-3">
            {applications.length === 0 ? (
              <p className="text-sm text-muted-foreground p-3 text-center">No applications registered yet.</p>
            ) : (
              applications.map((app) => (
                <button
                  key={app.id}
                  onClick={() => handleSelectApp(app)}
                  className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-colors border ${
                    selectedApp?.id === app.id
                      ? "bg-accent border-accent-foreground/20 font-medium"
                      : "hover:bg-muted/50 border-transparent"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="truncate">{app.name}</span>
                    <Badge variant="outline" className="text-[10px] uppercase">
                      {app.status}
                    </Badge>
                  </div>
                  {app.description && (
                    <p className="text-xs text-muted-foreground truncate mt-1">{app.description}</p>
                  )}
                </button>
              ))
            )}
          </CardContent>
        </Card>

        {/* Right Column: API Keys & Application Management */}
        <div className="lg:col-span-3 space-y-6">
          {selectedApp ? (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <CardTitle className="text-lg">{selectedApp.name}</CardTitle>
                    <Badge>{selectedApp.status}</Badge>
                  </div>
                  <CardDescription className="mt-1">
                    {selectedApp.description || "No description provided."}
                  </CardDescription>
                </div>
                <Button onClick={() => setShowCreateKeyDialog(true)}>
                  <Key className="h-4 w-4 mr-2" />
                  Issue API Key
                </Button>
              </CardHeader>
              <CardContent className="space-y-4">
                <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">API Keys</h3>
                {selectedAppKeys.length === 0 ? (
                  <div className="text-center py-8 border rounded-lg bg-muted/20">
                    <Key className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
                    <p className="text-sm font-medium">No API keys issued for this application</p>
                    <p className="text-xs text-muted-foreground mt-1">Issue a key to allow schema-validated invocation</p>
                  </div>
                ) : (
                  <div className="border rounded-lg overflow-hidden divide-y">
                    {selectedAppKeys.map((key) => (
                      <div key={key.id} className="p-4 flex items-center justify-between">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-sm">{key.name}</span>
                            <code className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono">{key.key_prefix}.***</code>
                            {key.revoked_at ? (
                              <Badge variant="destructive">Revoked</Badge>
                            ) : (
                              <Badge variant="secondary">Active</Badge>
                            )}
                          </div>
                          <div className="flex items-center gap-4 text-xs text-muted-foreground">
                            <span>Scopes: {key.scopes.join(", ")}</span>
                            {key.last_used_at && (
                              <span>Last used: {new Date(key.last_used_at).toLocaleDateString()}</span>
                            )}
                          </div>
                        </div>
                        {!key.revoked_at && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive hover:text-destructive"
                            onClick={() => handleRevokeKey(key.id, key.name)}
                          >
                            <Trash2 className="h-4 w-4 mr-1" />
                            Revoke
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ) : (
            <div className="text-center py-16 border rounded-lg">
              <Code2 className="h-10 w-10 text-muted-foreground mx-auto mb-2" />
              <p className="text-base font-medium">Select an application or register a new one</p>
            </div>
          )}
        </div>
      </div>

      {/* Create Application Dialog */}
      <Dialog open={showAppDialog} onOpenChange={setShowCreateAppDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Register Application</DialogTitle>
            <DialogDescription>Register an external client application to manage API keys and agent access.</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreateApp} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="app-name">Application Name</Label>
              <Input
                id="app-name"
                value={appName}
                onChange={(e) => setAppName(e.target.value)}
                placeholder="e.g. Sales Portal Integration"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="app-desc">Description</Label>
              <Input
                id="app-desc"
                value={appDesc}
                onChange={(e) => setAppDesc(e.target.value)}
                placeholder="Short description of this integration"
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowCreateAppDialog(false)}>
                Cancel
              </Button>
              <Button type="submit">Register</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Create API Key Dialog */}
      <Dialog open={showKeyDialog} onOpenChange={setShowCreateKeyDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Issue API Key</DialogTitle>
            <DialogDescription>Issue a new API key for {selectedApp?.name}.</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreateKey} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="key-name">Key Name</Label>
              <Input
                id="key-name"
                value={keyName}
                onChange={(e) => setKeyName(e.target.value)}
                placeholder="e.g. Production Key"
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
              <Button type="button" variant="outline" onClick={() => setShowCreateKeyDialog(false)}>
                Cancel
              </Button>
              <Button type="submit">Create Key</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* One-Time Secret Reveal Modal */}
      <Dialog open={!!oneTimeSecret} onOpenChange={(o) => { if (!o) clearOneTimeSecret() }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-amber-500">
              <ShieldAlert className="h-5 w-5" />
              Copy Your API Key Now
            </DialogTitle>
            <DialogDescription className="text-amber-500/90 font-medium">
              This plaintext secret key will NEVER be shown again. Save it securely.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="flex items-center gap-2 border p-3 rounded bg-muted font-mono text-sm break-all">
              <span className="flex-1">{oneTimeSecret}</span>
              <Button size="icon-sm" variant="ghost" onClick={() => copyToClipboard(oneTimeSecret || "")}>
                {copiedSecret ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
              </Button>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={clearOneTimeSecret}>Done & Dismiss</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
