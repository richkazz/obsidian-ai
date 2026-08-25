"use client"

import { useState } from "react"
import { useSession } from "next-auth/react"
import { Users, Check, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { apiClient } from "@/lib/api-client"
import { usePlaygroundStore } from "@/stores/playground-store"
import type { Team, Agent } from "@/types/playground"

// Inline agent add/remove for an existing team, right from the chat header —
// the team's agent_ids are re-read fresh from the DB on every message, so a
// change here applies starting with the very next message in this session,
// no need to leave the chat or restart anything.
export function TeamMembersPopover({ team }: { team: Team }) {
  const { data: session } = useSession()
  const agents = usePlaygroundStore((s) => s.agents)
  const teams = usePlaygroundStore((s) => s.teams)
  const setTeams = usePlaygroundStore((s) => s.setTeams)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)

  const toggleAgent = async (agentId: string) => {
    if (!session?.accessToken || saving) return
    const nextIds = team.agent_ids.includes(agentId)
      ? team.agent_ids.filter((id) => id !== agentId)
      : [...team.agent_ids, agentId]
    if (nextIds.length === 0) return // a team needs at least one agent

    setSaving(true)
    try {
      const updated = await apiClient.updateTeam(team.id, { agent_ids: nextIds })
      setTeams(teams.map((t) => (t.id === updated.id ? updated : t)))
    } catch (err) {
      console.error("Failed to update team members:", err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="h-7 gap-1.5 text-xs px-2">
          <Users className="h-3.5 w-3.5" />
          {team.agent_ids.length}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-0">
        <div className="px-3 py-2 border-b flex items-center justify-between">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Team Members</p>
          {saving && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
        </div>
        <div className="max-h-64 overflow-y-auto py-1">
          {agents.length === 0 ? (
            <p className="text-xs text-muted-foreground px-3 py-2">No agents available.</p>
          ) : (
            agents.map((a: Agent) => {
              const isMember = team.agent_ids.includes(a.id)
              const isOnlyMember = isMember && team.agent_ids.length === 1
              return (
                <button
                  key={a.id}
                  onClick={() => toggleAgent(a.id)}
                  disabled={saving || isOnlyMember}
                  title={isOnlyMember ? "A team needs at least one agent" : undefined}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <div
                    className={`h-4 w-4 rounded border flex items-center justify-center shrink-0 ${
                      isMember ? "bg-primary border-primary" : "border-input"
                    }`}
                  >
                    {isMember && <Check className="h-3 w-3 text-primary-foreground" />}
                  </div>
                  <span className="truncate">{a.name}</span>
                </button>
              )
            })
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
