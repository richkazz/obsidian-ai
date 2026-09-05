"use client"

import { useEffect, useState } from "react"
import { apiClient } from "@/lib/api-client"
import type { TraceSpan, SessionTrace, WorkflowRunTrace } from "@/types/playground"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Brain, Wrench, Server, GitBranch, ChevronRight, Clock, Zap, AlertCircle } from "lucide-react"

// ─── helpers ─────────────────────────────────────────────────────────────────

function fmtDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

function fmtTokens(n: number): string {
  if (n === 0) return "—"
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

function tryParseJson(raw?: string): string {
  if (!raw) return ""
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
}

interface SpanGroup {
  round: number
  spans: TraceSpan[]
}

function groupByRound(spans: TraceSpan[]): SpanGroup[] {
  const map = new Map<number, TraceSpan[]>()
  for (const span of spans) {
    const arr = map.get(span.round_number) ?? []
    arr.push(span)
    map.set(span.round_number, arr)
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => a - b)
    .map(([round, s]) => ({ round, s: s.sort((a, b) => a.sequence - b.sequence) }))
    .map(({ round, s }) => ({ round, spans: s }))
}

// ─── SpanRow ─────────────────────────────────────────────────────────────────

function SpanIcon({ type }: { type: TraceSpan["span_type"] }) {
  if (type === "llm_call")      return <Brain  className="h-3.5 w-3.5 text-violet-500 shrink-0" />
  if (type === "tool_call")     return <Wrench className="h-3.5 w-3.5 text-amber-500  shrink-0" />
  if (type === "mcp_call")      return <Server className="h-3.5 w-3.5 text-blue-500   shrink-0" />
  return                               <GitBranch className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
}

function SpanRow({ span, indent = false }: { span: TraceSpan; indent?: boolean }) {
  const [open, setOpen] = useState(false)
  const hasData = span.input_data || span.output_data

  return (
    <Collapsible open={open} onOpenChange={hasData ? setOpen : undefined}>
      <CollapsibleTrigger
        className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-left text-xs hover:bg-muted/50 transition-colors ${indent ? "ml-5" : ""} ${hasData ? "cursor-pointer" : "cursor-default"}`}
        disabled={!hasData}
      >
        {hasData && (
          <ChevronRight
            className={`h-3 w-3 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-90" : ""}`}
          />
        )}
        {!hasData && <span className="w-3 shrink-0" />}

        <SpanIcon type={span.span_type} />

        <span className="flex-1 font-medium truncate">{span.name}</span>

        {span.span_type === "llm_call" && (span.input_tokens > 0 || span.output_tokens > 0) && (
          <span className="text-muted-foreground shrink-0 flex items-center gap-1">
            <Zap className="h-3 w-3" />
            {fmtTokens(span.input_tokens + span.output_tokens)}
          </span>
        )}

        <span className={`shrink-0 flex items-center gap-1 ${span.duration_ms > 5000 ? "text-amber-500" : "text-muted-foreground"}`}>
          <Clock className="h-3 w-3" />
          {fmtDuration(span.duration_ms)}
        </span>

        {span.status === "error" && (
          <AlertCircle className="h-3.5 w-3.5 text-destructive shrink-0" />
        )}
      </CollapsibleTrigger>

      {hasData && (
        <CollapsibleContent>
          <div className={`mb-1 space-y-1.5 ${indent ? "ml-5" : ""}`}>
            {span.input_data && (
              <div className="px-3">
                <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">Input</p>
                <pre className="text-[10px] bg-muted/60 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all max-h-36">
                  {tryParseJson(span.input_data)}
                </pre>
              </div>
            )}
            {span.output_data && (
              <div className="px-3">
                <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">Output</p>
                <pre className="text-[10px] bg-muted/60 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all max-h-36">
                  {tryParseJson(span.output_data)}
                </pre>
              </div>
            )}
          </div>
        </CollapsibleContent>
      )}
    </Collapsible>
  )
}

// ─── RoundGroup ──────────────────────────────────────────────────────────────

function RoundGroup({ group, showDivider }: { group: SpanGroup; showDivider: boolean }) {
  const llmSpans  = group.spans.filter((s) => s.span_type === "llm_call")
  const toolSpans = group.spans.filter((s) => s.span_type !== "llm_call")

  return (
    <div>
      {showDivider && (
        <div className="flex items-center gap-2 px-3 py-1.5">
          <div className="h-px flex-1 bg-border" />
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
            {group.round === 0 ? "Initial" : `Round ${group.round}`}
          </span>
          <div className="h-px flex-1 bg-border" />
        </div>
      )}
      {llmSpans.map((span) => (
        <SpanRow key={span.id} span={span} indent={false} />
      ))}
      {toolSpans.map((span) => (
        <SpanRow key={span.id} span={span} indent={true} />
      ))}
    </div>
  )
}

// ─── TracePanel ──────────────────────────────────────────────────────────────

interface TracePanelProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  sessionId?: string | null
  workflowRunId?: string | null
}

export function TracePanel({ open, onOpenChange, sessionId, workflowRunId }: TracePanelProps) {
  const [trace, setTrace] = useState<SessionTrace | WorkflowRunTrace | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || (!sessionId && !workflowRunId)) return
    setTrace(null)
    setError(null)
    setIsLoading(true)

    const fetch = async () => {
      try {
        if (sessionId) {
          setTrace(await apiClient.getSessionTrace(sessionId))
        } else if (workflowRunId) {
          setTrace(await apiClient.getWorkflowRunTrace(workflowRunId))
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load trace")
      } finally {
        setIsLoading(false)
      }
    }
    fetch()
  }, [open, sessionId, workflowRunId])

  const [viewMode, setViewMode] = useState<"tree" | "waterfall">("tree")
  const groups = trace ? groupByRound(trace.spans) : []
  const showDividers = groups.length > 1

  const minStartTime = trace && trace.spans.length > 0 ? Math.min(...trace.spans.map(s => new Date(s.created_at).getTime())) : 0
  const totalSpanDuration = trace ? Math.max(...trace.spans.map(s => (new Date(s.created_at).getTime() - minStartTime) + (s.duration_ms || 0)), 1) : 1

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-130 sm:max-w-130 flex flex-col p-0">
        <SheetHeader className="px-4 py-3 border-b border-border shrink-0">
          <SheetTitle className="text-sm">Execution Trace</SheetTitle>

          {trace && (
            <div className="flex items-center justify-between gap-2 mt-2">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="secondary" className="text-[10px] gap-1 px-1.5">
                  <Clock className="h-3 w-3" />
                  {fmtDuration(trace.total_duration_ms)}
                </Badge>
                <Badge variant="secondary" className="text-[10px] gap-1 px-1.5">
                  <Zap className="h-3 w-3" />
                  {(trace.total_input_tokens + trace.total_output_tokens).toLocaleString()} tokens
                </Badge>
                {trace.total_cost_usd !== undefined && (
                  <Badge variant="secondary" className="text-[10px] px-1.5 font-mono">
                    ${trace.total_cost_usd.toFixed(4)}
                  </Badge>
                )}
              </div>
              <div className="flex border rounded overflow-hidden">
                <button
                  onClick={() => setViewMode("tree")}
                  className={`px-2 py-0.5 text-[10px] font-medium ${viewMode === "tree" ? "bg-muted text-foreground" : "text-muted-foreground"}`}
                >
                  Tree
                </button>
                <button
                  onClick={() => setViewMode("waterfall")}
                  className={`px-2 py-0.5 text-[10px] font-medium ${viewMode === "waterfall" ? "bg-muted text-foreground" : "text-muted-foreground"}`}
                >
                  Waterfall
                </button>
              </div>
            </div>
          )}
        </SheetHeader>

        <div className="flex-1 min-h-0">
          {isLoading ? (
            <div className="flex items-center justify-center h-full">
              <div className="flex flex-col items-center gap-3">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
                <p className="text-xs text-muted-foreground">Loading trace...</p>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-full px-6">
              <div className="text-center">
                <AlertCircle className="h-8 w-8 text-muted-foreground/40 mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">{error}</p>
              </div>
            </div>
          ) : !trace || trace.spans.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <Brain className="h-8 w-8 text-muted-foreground/30 mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No spans recorded</p>
                <p className="text-xs text-muted-foreground/70 mt-1">
                  Traces are only available for sessions with activity
                </p>
              </div>
            </div>
          ) : viewMode === "tree" ? (
            <ScrollArea className="h-full">
              <div className="py-2">
                {groups.map((group, i) => (
                  <RoundGroup
                    key={group.round}
                    group={group}
                    showDivider={showDividers && i > 0}
                  />
                ))}
              </div>
            </ScrollArea>
          ) : (
            <ScrollArea className="h-full">
              <div className="py-3 px-4 space-y-2">
                {trace.spans.map((span) => {
                  const startTime = new Date(span.created_at).getTime()
                  const leftPct = Math.max(0, Math.min(100, ((startTime - minStartTime) / totalSpanDuration) * 100))
                  const widthPct = Math.max(1, Math.min(100 - leftPct, ((span.duration_ms || 10) / totalSpanDuration) * 100))
                  return (
                    <div key={span.id} className="text-xs space-y-1 border-b border-border/40 pb-2">
                      <div className="flex items-center justify-between font-medium">
                        <span className="truncate max-w-[200px] flex items-center gap-1.5">
                          <SpanIcon type={span.span_type} />
                          {span.name}
                        </span>
                        <span className="text-[10px] text-muted-foreground font-mono">
                          {fmtDuration(span.duration_ms)}
                        </span>
                      </div>
                      <div className="w-full bg-muted/40 h-2.5 rounded relative overflow-hidden">
                        <div
                          className="bg-primary/70 h-full rounded transition-all"
                          style={{ left: `${leftPct}%`, width: `${widthPct}%`, position: "absolute" }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </ScrollArea>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
