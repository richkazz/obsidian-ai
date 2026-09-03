"use client"

import { useState, useEffect, createElement } from "react"
import type { ReactElement, ReactNode } from "react"
import { X, FileText, FileCode2, ChevronDown, Pencil, Plus, Braces } from "lucide-react"
import type { FileUIPart } from "ai"
import {
  PromptInput,
  PromptInputTextarea,
  PromptInputHeader,
  PromptInputFooter,
  PromptInputTools,
  PromptInputSubmit,
  PromptInputActionMenu,
  PromptInputActionMenuTrigger,
  PromptInputActionMenuContent,
  PromptInputActionAddAttachments,
  usePromptInputAttachments,
} from "@/components/ai-elements/prompt-input"
import { usePlaygroundStore } from "@/stores/playground-store"
import { apiClient } from "@/lib/api-client"
import { cn } from "@/lib/utils"
import type { Artifact } from "@/types/playground"

interface ChatInputProps {
  onSend: (message: string, files?: FileUIPart[], structured?: boolean) => void
  onStop: () => void
  isStreaming: boolean
  disabled?: boolean
}

function AttachmentPreview() {
  const { files, remove } = usePromptInputAttachments()
  if (files.length === 0) return null

  return (
    <PromptInputHeader>
      <div className="flex flex-wrap gap-2 px-1 pt-1">
        {files.map((file) => {
          const isImage = file.mediaType.startsWith("image/")
          return (
            <div
              key={file.id}
              className="relative group flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-2.5 py-2 text-xs"
            >
              {isImage ? (
                <img
                  src={file.url}
                  alt={file.filename || "attachment"}
                  className="h-10 w-10 rounded object-cover"
                />
              ) : (
                <FileText className="size-4 text-muted-foreground shrink-0" />
              )}
              <span className="max-w-30 truncate text-muted-foreground">
                {file.filename || "file"}
              </span>
              <button
                type="button"
                onClick={() => remove(file.id)}
                className="ml-1 rounded-full p-0.5 hover:bg-muted-foreground/20 transition-colors cursor-pointer"
              >
                <X className="size-3 text-muted-foreground" />
              </button>
            </div>
          )
        })}
      </div>
    </PromptInputHeader>
  )
}

// ── Artifact target selector ──────────────────────────────────────────────────

function ArtifactTargetSelector({
  artifacts,
  target,
  onChange,
}: {
  artifacts: Artifact[]
  target: Artifact | null
  onChange: (a: Artifact | null) => void
}): ReactElement | null {
  const [open, setOpen] = useState(false)

  if (artifacts.length === 0) return null

  return (
    <div className="relative flex items-center">
      {/* Mode pill */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors cursor-pointer",
          target
            ? "bg-primary/10 border-primary/30 text-primary hover:bg-primary/20"
            : "bg-muted/40 border-border text-muted-foreground hover:bg-muted/70 hover:text-foreground",
        )}
      >
        {target ? (
          <>
            <Pencil className="h-2.5 w-2.5" />
            Editing: {target.title}
          </>
        ) : (
          <>
            <Plus className="h-2.5 w-2.5" />
            New artifact
          </>
        )}
        <ChevronDown className={cn("h-2.5 w-2.5 transition-transform", open && "rotate-180")} />
      </button>

      {/* Dropdown — renders below the pill, no overflow clipping */}
      {open && (
        <div className="absolute top-full mt-1 left-0 z-50 min-w-52 rounded-lg border border-border bg-popover shadow-lg py-1 text-xs">
          {/* New artifact option */}
          <button
            type="button"
            onClick={() => { onChange(null); setOpen(false) }}
            className={cn(
              "w-full flex items-center gap-2 px-3 py-2 hover:bg-muted/50 transition-colors text-left cursor-pointer",
              !target && "text-foreground font-medium",
              target && "text-muted-foreground",
            )}
          >
            <Plus className="h-3 w-3 shrink-0" />
            New artifact
          </button>

          <div className="my-1 border-t border-border" />

          {/* Existing artifacts */}
          {artifacts.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => { onChange(a); setOpen(false) }}
              className={cn(
                "w-full flex items-center gap-2 px-3 py-2 hover:bg-muted/50 transition-colors text-left cursor-pointer",
                target?.id === a.id && "text-primary font-medium",
                target?.id !== a.id && "text-muted-foreground",
              )}
            >
              <FileCode2 className="h-3 w-3 shrink-0" />
              <span className="truncate">{a.title}</span>
              <span className="ml-auto shrink-0 text-xs opacity-60">{a.type}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function ChatInput({ onSend, onStop, isStreaming, disabled }: ChatInputProps) {
  const status = isStreaming ? "streaming" as const : "ready" as const
  const artifacts = usePlaygroundStore((s): Artifact[] => s.artifacts)
  const selectedAgentId = usePlaygroundStore((s) => s.selectedAgentId)
  const [targetArtifact, setTargetArtifact] = useState<Artifact | null>(null)
  const [structured, setStructured] = useState(false)
  const [schemas, setSchemas] = useState<{ input?: unknown; output?: unknown }>({})
  const hasSchemas = Boolean(schemas.input || schemas.output)
  const currentTargetArtifact = targetArtifact && artifacts.some((a) => a.id === targetArtifact.id)
    ? targetArtifact
    : null
  const artifactSelector: ReactNode = artifacts.length > 0
    ? createElement(ArtifactTargetSelector, { artifacts, target: currentTargetArtifact, onChange: setTargetArtifact }) as unknown as ReactNode
    : null

  useEffect(() => {
    if (!structured || !selectedAgentId) return
    let active = true
    Promise.all([apiClient.getAgentAPIConfig(selectedAgentId), apiClient.listSchemas()])
      .then(([config, allSchemas]) => {
        const input = allSchemas.find((schema: { latest_version?: { id?: unknown; canonical_schema?: unknown } }) => String(schema.latest_version?.id) === String(config.input_schema_version_id))
        const output = allSchemas.find((schema: { latest_version?: { id?: unknown; canonical_schema?: unknown } }) => String(schema.latest_version?.id) === String(config.output_schema_version_id))
        if (active) setSchemas({ input: input?.latest_version?.canonical_schema, output: output?.latest_version?.canonical_schema })
      })
      .catch(() => { if (active) setSchemas({}) })
    return () => { active = false }
  }, [structured, selectedAgentId])

  const handleSend = (text: string, files?: FileUIPart[]) => {
    let content = text
    if (currentTargetArtifact) {
      // Prepend a context block so the model knows exactly which artifact to update
      content = `[EDIT ARTIFACT id="${currentTargetArtifact.id}" title="${currentTargetArtifact.title}" type="${currentTargetArtifact.type}"]\n${text}`
      // Keep targetArtifact selected so the user can keep editing without re-selecting
    }
    onSend(content, files, structured)
  }

  return (
    <div className="border-t border-border px-4 py-4">
      <div className="max-w-3xl mx-auto flex flex-col gap-1.5">
        {/* Artifact target selector — outside PromptInput so dropdown isn't clipped */}
        {artifactSelector as never}
        {structured && hasSchemas && (
          <details className="rounded-md border border-primary/20 bg-primary/5 px-3 py-2 text-xs">
            <summary className="cursor-pointer font-medium text-primary">Active JSON contract</summary>
            <div className="mt-2 grid gap-2 md:grid-cols-2">
              <pre className="max-h-32 overflow-auto rounded bg-background/70 p-2">{String(JSON.stringify(schemas.input || {}, null, 2))}</pre>
              <pre className="max-h-32 overflow-auto rounded bg-background/70 p-2">{String(JSON.stringify(schemas.output || {}, null, 2))}</pre>
            </div>
          </details>
        )}
        <PromptInput
          accept="image/*,application/pdf,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          multiple
          maxFiles={10}
          maxFileSize={20 * 1024 * 1024}
          onSubmit={({ text, files }) => {
            const trimmed = text.trim()
            if ((!trimmed && files.length === 0) || disabled) return
            handleSend(trimmed, files.length > 0 ? files : undefined)
          }}
        >
          <AttachmentPreview />
          <PromptInputTextarea
            placeholder={disabled ? "Select an agent to start..." : structured ? '{"query":"..."}' : "Ask anything..."}
            disabled={disabled}
          />
          <PromptInputFooter>
            <PromptInputTools>
              <PromptInputActionMenu>
                <PromptInputActionMenuTrigger />
                <PromptInputActionMenuContent>
                  <PromptInputActionAddAttachments label="Attach files" />
                </PromptInputActionMenuContent>
              </PromptInputActionMenu>
              <button
                type="button"
                onClick={() => setStructured((value) => !value)}
                disabled={disabled}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs transition-colors",
                  structured ? "border-primary/40 bg-primary/10 text-primary" : "border-border text-muted-foreground hover:bg-muted",
                )}
                title="Test this agent's JSON input and output contract"
              >
                <Braces className="size-3.5" />
                JSON test
              </button>
              <span className="text-xs text-muted-foreground">
                {structured ? "Input and output follow the API schemas" : "Shift + Enter for new line"}
              </span>
            </PromptInputTools>
            <PromptInputSubmit
              status={status}
              onStop={onStop}
              disabled={disabled}
            />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  )
}
