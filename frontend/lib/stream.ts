import type { Message, ToolCall, ReasoningStep, AgentStep, ToolRound, FileAttachment, WorkflowStepResult, FileNode, HITLApprovalEvent, ToolProposalEvent, ArtifactEvent, NodeStartEvent, NodeCompleteEvent, NodeErrorEvent, NodeContentDeltaEvent } from "@/types/playground"

// Use the browser's current origin by default. In a deployed Compose stack,
// `localhost` means the visitor's machine, not the backend container; using it
// here prevents chat requests from ever reaching the agent. Nginx proxies the
// same-origin /chat and /workflows SSE endpoints without buffering.
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || ""

export interface KBContextEvent {
  kbs: { id: string; name: string }[]
}

export interface TokenUsageEvent {
  input_tokens: number
  output_tokens: number
  session_total_input: number
  session_total_output: number
}

export interface ContextCompactedEvent {
  messages_summarized: number
  summary_preview: string
}

export interface TraceSpanEvent {
  trace_id: string
  span_id: string
  parent_span_id?: string
  name: string
  span_type: string
  status: string
  duration_ms?: number
  cost_usd?: number
}

export async function streamChat(
  accessToken: string,
  sessionId: string,
  message: string,
  onContentDelta: (content: string) => void,
  onToolCall: (toolCall: ToolCall) => void,
  onReasoning: (reasoning: ReasoningStep) => void,
  onComplete: (message: Message) => void,
  onError: (error: string) => void,
  onAgentStep?: (step: AgentStep) => void,
  onAgentMessage?: (agentId: string, agentName: string, content: string) => void,
  onToolRound?: (round: ToolRound) => void,
  signal?: AbortSignal,
  attachments?: FileAttachment[],
  onKBContext?: (event: KBContextEvent) => void,
  onKBWarning?: (event: KBContextEvent) => void,
  onTerminalOutput?: (content: string, isComplete: boolean) => void,
  onFileTree?: (nodes: FileNode[]) => void,
  onSourceUrl?: (url: string, title?: string) => void,
  onPlanStart?: (title: string, description?: string) => void,
  onPlanStep?: (step: string) => void,
  onPlanEnd?: () => void,
  onJsxPreview?: (jsx: string, isComplete: boolean) => void,
  onTokenUsage?: (event: TokenUsageEvent) => void,
  onContextCompacted?: (event: ContextCompactedEvent) => void,
  onHITLApprovalRequired?: (event: HITLApprovalEvent) => void,
  onToolProposalRequired?: (event: ToolProposalEvent) => void,
  onToolGenerating?: (event: { name: string; handler_type: string }) => void,
  onArtifact?: (event: ArtifactEvent) => void,
  onTraceSpan?: (event: TraceSpanEvent) => void,
  structured = false,
): Promise<void> {
  const body: Record<string, unknown> = {
    session_id: sessionId,
    message,
    stream: true,
    structured,
  }
  if (attachments && attachments.length > 0) {
    body.attachments = attachments.map((a) => ({
      filename: a.filename,
      media_type: a.media_type,
      file_type: a.file_type,
      data: a.data,
    }))
  }

  let response: Response
  try {
    response = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify(body),
      signal,
    })
  } catch (error) {
    if ((error as Error).name !== "AbortError") {
      onError("Unable to reach the agent service. Please try again.")
    }
    return
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    onError(errorData.detail || `Request failed with status ${response.status}`)
    return
  }

  if (!response.body) {
    onError("No response body")
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  let currentEventType = ""

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split("\n")
      buffer = lines.pop() || ""

      for (const line of lines) {
        const trimmed = line.trim()

        if (trimmed.startsWith("event: ")) {
          currentEventType = trimmed.slice(7).trim()
          continue
        }

        if (trimmed.startsWith("data: ")) {
          const dataStr = trimmed.slice(6)
          try {
            const data = JSON.parse(dataStr)

            switch (currentEventType) {
              case "content_delta":
                onContentDelta(data.content || "")
                break
              case "tool_call":
                onToolCall(data)
                break
              case "reasoning_delta":
                onReasoning({
                  type: "thinking",
                  content: data.content || "",
                })
                break
              case "agent_step":
                onAgentStep?.(data)
                break
              case "agent_message":
                onAgentMessage?.(data.agent_id, data.agent_name, data.content)
                break
              case "tool_round":
                onToolRound?.(data)
                break
              case "kb_context":
                onKBContext?.(data)
                break
              case "kb_warning":
                onKBWarning?.(data)
                break
              case "terminal_output":
                onTerminalOutput?.(data.content ?? "", data.is_complete ?? true)
                break
              case "file_tree":
                onFileTree?.(data.tree ?? [])
                break
              case "source_url":
                onSourceUrl?.(data.url, data.title)
                break
              case "plan_start":
                onPlanStart?.(data.title ?? "Plan", data.description)
                break
              case "plan_step":
                onPlanStep?.(data.step ?? "")
                break
              case "plan_end":
                onPlanEnd?.()
                break
              case "jsx_preview":
                onJsxPreview?.(data.jsx ?? "", data.is_complete ?? false)
                break
              case "message_complete":
                onComplete(data)
                break
              case "token_usage":
                onTokenUsage?.(data)
                break
              case "context_compacted":
                onContextCompacted?.(data)
                break
              case "hitl_approval_required":
                onHITLApprovalRequired?.(data)
                break
              case "tool_proposal_required":
                onToolProposalRequired?.(data)
                break
              case "tool_generating":
                onToolGenerating?.(data)
                break
              case "artifact":
                onArtifact?.(data as ArtifactEvent)
                break
              case "span_started":
              case "span_finished":
              case "trace_started":
              case "trace_finished":
                onTraceSpan?.(data as TraceSpanEvent)
                break
              case "error":
                onError(data.error || "Unknown error")
                break
              case "done":
                return
            }
          } catch {
            // Skip malformed JSON
          }
          currentEventType = ""
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}


export interface WorkflowStartEvent {
  run_id: string
  workflow_name: string
  total_steps: number
}

export interface StepStartEvent {
  step_order: number
  agent_id: string
  agent_name: string
  task: string
}

export interface StepCompleteEvent {
  step_order: number
  agent_name: string
  output: string
}

export interface WorkflowCompleteEvent {
  run_id: string
  final_output: string
}

export async function streamWorkflow(
  accessToken: string,
  workflowId: string,
  input: string,
  onWorkflowStart: (event: WorkflowStartEvent) => void,
  onStepStart: (event: StepStartEvent) => void,
  onStepContentDelta: (stepOrder: number, content: string) => void,
  onStepComplete: (event: StepCompleteEvent) => void,
  onStepError: (stepOrder: number, error: string) => void,
  onWorkflowComplete: (event: WorkflowCompleteEvent) => void,
  onWorkflowError: (runId: string, error: string) => void,
  signal?: AbortSignal,
  // DAG node callbacks (optional — only fired for DAG workflows)
  onNodeStart?: (event: NodeStartEvent) => void,
  onNodeContentDelta?: (event: NodeContentDeltaEvent) => void,
  onNodeComplete?: (event: NodeCompleteEvent) => void,
  onNodeError?: (event: NodeErrorEvent) => void,
): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${BACKEND_URL}/workflows/${workflowId}/run`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ input }),
      signal,
    })
  } catch (error) {
    if ((error as Error).name !== "AbortError") {
      onWorkflowError("", "Unable to reach the workflow service. Please try again.")
    }
    return
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    onWorkflowError("", errorData.detail || `Request failed with status ${response.status}`)
    return
  }

  if (!response.body) {
    onWorkflowError("", "No response body")
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  let currentEventType = ""

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split("\n")
      buffer = lines.pop() || ""

      for (const line of lines) {
        const trimmed = line.trim()

        if (trimmed.startsWith("event: ")) {
          currentEventType = trimmed.slice(7).trim()
          continue
        }

        if (trimmed.startsWith("data: ")) {
          const dataStr = trimmed.slice(6)
          try {
            const data = JSON.parse(dataStr)

            switch (currentEventType) {
              case "workflow_start":
                onWorkflowStart(data)
                break
              case "step_start":
                onStepStart(data)
                break
              case "step_content_delta":
                onStepContentDelta(data.step_order, data.content || "")
                break
              case "step_complete":
                onStepComplete(data)
                break
              case "step_error":
                onStepError(data.step_order, data.error || "Unknown error")
                break
              case "workflow_complete":
                onWorkflowComplete(data)
                break
              case "workflow_error":
                onWorkflowError(data.run_id || "", data.error || "Unknown error")
                break
              // DAG node events
              case "node_start":
                onNodeStart?.(data as NodeStartEvent)
                break
              case "node_content_delta":
                onNodeContentDelta?.(data as NodeContentDeltaEvent)
                break
              case "node_complete":
                onNodeComplete?.(data as NodeCompleteEvent)
                break
              case "node_error":
                onNodeError?.(data as NodeErrorEvent)
                break
              case "done":
                return
            }
          } catch {
            // Skip malformed JSON
          }
          currentEventType = ""
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
