"use client"

import { useEffect, useRef, useState } from "react"
import { useSession } from "next-auth/react"
import { useRouter } from "next/navigation"
import { apiClient } from "@/lib/api-client"
import type { AsyncJobItem } from "@/types/playground"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { Clock, CheckCircle2, XCircle, TimerOff, X } from "lucide-react"
import { cn } from "@/lib/utils"

const POLL_INTERVAL = 8000

const STATUS_ICON: Record<AsyncJobItem["status"], React.ReactNode> = {
  pending: <Clock className="h-3.5 w-3.5 text-blue-500 animate-pulse" />,
  completed: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />,
  failed: <XCircle className="h-3.5 w-3.5 text-destructive" />,
  expired: <TimerOff className="h-3.5 w-3.5 text-muted-foreground" />,
}

export function AsyncJobsGlobalBadge() {
  const { data: authSession } = useSession()
  const router = useRouter()
  const [jobs, setJobs] = useState<AsyncJobItem[]>([])
  const [open, setOpen] = useState(false)
  const [dismissing, setDismissing] = useState<Record<string, boolean>>({})
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!authSession?.accessToken) return
    apiClient.setAccessToken(authSession.accessToken as string)
    poll()
    intervalRef.current = setInterval(poll, POLL_INTERVAL)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [authSession?.accessToken])

  const poll = async () => {
    try {
      const pending = await apiClient.getGlobalPendingAsyncJobs()
      setJobs(pending)
    } catch {
      // silent — badge just stays empty on error
    }
  }

  const handleDismiss = async (job: AsyncJobItem) => {
    setDismissing((prev) => ({ ...prev, [job.job_id]: true }))
    try {
      await apiClient.markAsyncJobSeen(job.job_id)
      setJobs((prev) => prev.filter((j) => j.job_id !== job.job_id))
    } catch {
      setDismissing((prev) => ({ ...prev, [job.job_id]: false }))
    }
  }

  if (jobs.length === 0) return null

  const activeCount = jobs.filter((j) => j.status === "pending").length

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="relative h-8 gap-1.5 text-xs text-blue-600 dark:text-blue-400 hover:bg-blue-500/10"
        >
          <Clock className={cn("h-3.5 w-3.5", activeCount > 0 && "animate-pulse")} />
          <span className="hidden sm:inline">Background jobs</span>
          <Badge className="absolute -top-1 -right-1 h-4 min-w-4 px-1 text-[10px] bg-blue-500 text-white border-0">
            {jobs.length}
          </Badge>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="px-3 py-2 border-b">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Background Jobs</p>
        </div>
        <div className="max-h-72 overflow-y-auto divide-y">
          {jobs.map((job) => (
            <div key={job.job_id} className="px-3 py-2.5 space-y-1.5">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex items-start gap-1.5">
                  {STATUS_ICON[job.status]}
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{job.description}</p>
                    <button
                      className="text-xs text-muted-foreground hover:text-foreground truncate block max-w-full text-left"
                      onClick={() => {
                        setOpen(false)
                        router.push(`/sessions?highlight=${job.session_id}`)
                      }}
                    >
                      {job.status === "pending"
                        ? `Checking… (${job.poll_count} check${job.poll_count === 1 ? "" : "s"} so far)`
                        : `Session ${job.session_id.slice(0, 8)}…`}
                    </button>
                  </div>
                </div>
                {job.status !== "pending" && (
                  <button
                    className="shrink-0 text-muted-foreground hover:text-foreground disabled:opacity-50"
                    onClick={() => handleDismiss(job)}
                    disabled={dismissing[job.job_id]}
                    title="Dismiss"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
              {job.status !== "pending" && (job.last_result || job.error) && (
                <p className="text-xs text-muted-foreground line-clamp-2">
                  {job.error || job.last_result}
                </p>
              )}
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}
