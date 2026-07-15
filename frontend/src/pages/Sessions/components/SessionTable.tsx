/**
 * SessionTable — Tabular history of active agent interaction sessions.
 *
 * REACT CONCEPT: "Presentational Component & Tooltip Rendering"
 * ──────────────────────────────────────────────────────────────────
 * Renders the tabular active session log. Column layout matches enterprise SOC
 * timelines: Time (startedAt), Session ID (truncated), and Agent ID.
 */

import type { Session } from '../../../types/session'
import { formatTimestamp } from '../../../utils/date'

interface SessionTableProps {
  sessions: Session[]
  loading: boolean
}

export default function SessionTable({ sessions, loading }: SessionTableProps) {
  const truncateId = (id: string) => {
    if (id.length <= 8) return id
    return `${id.slice(0, 8)}...`
  }

  if (loading) {
    return (
      <div className="divide-y divide-border-secondary animate-pulse">
        <div className="grid grid-cols-3 gap-4 px-6 py-4 bg-bg-secondary text-xs font-semibold text-text-muted uppercase">
          <span>Time</span>
          <span>Session ID</span>
          <span>Agent ID</span>
        </div>
        {[1, 2].map((n) => (
          <div key={n} className="grid grid-cols-3 gap-4 px-6 py-4 items-center">
            <div className="h-4 w-32 bg-border-primary/40 rounded" />
            <div className="h-4 w-24 bg-border-primary/40 rounded" />
            <div className="h-4 w-24 bg-border-primary/40 rounded" />
          </div>
        ))}
      </div>
    )
  }

  if (sessions.length === 0) {
    return (
      <div className="px-6 py-16 text-center space-y-2 bg-bg-surface">
        <h3 className="text-sm font-bold text-text-primary">
          No sessions found.
        </h3>
        <p className="text-xs text-text-secondary max-w-sm mx-auto">
          Sessions will appear here after agents begin executing requests.
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto w-full">
      <table className="w-full text-left border-collapse min-w-[600px]">
        <thead>
          <tr className="bg-bg-secondary border-b border-border-secondary text-xs font-semibold text-text-muted uppercase tracking-wider">
            <th className="px-6 py-4">Time</th>
            <th className="px-6 py-4">Session ID</th>
            <th className="px-6 py-4">Agent ID</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border-secondary text-xs">
          {sessions.map((session) => (
            <tr key={session.id} className="hover:bg-bg-surface-hover/30 transition-colors">
              
              {/* Time */}
              <td className="px-6 py-4 text-text-secondary font-mono whitespace-nowrap">
                {formatTimestamp(session.startedAt)}
              </td>

              {/* Truncated Session ID with tooltip */}
              <td className="px-6 py-4 text-text-primary font-mono" title={session.id}>
                {truncateId(session.id)}
              </td>

              {/* Agent ID */}
              <td className="px-6 py-4 text-text-secondary font-mono">
                {session.agentId}
              </td>

            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
