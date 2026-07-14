/**
 * AuditTable — Tabular history of platform security decisions.
 *
 * REACT CONCEPT: "Presentational Component & Tooltip Rendering"
 * ──────────────────────────────────────────────────────────────────
 * Renders the tabular audit log. Column layout matches enterprise SOC
 * timelines: Time, Decision, Agent, Tool, and truncated Event ID.
 *
 * Timestamp Formatting:
 *   Consumes the shared `formatTimestamp` utility to render times
 *   consistently as YYYY-MM-DD HH:mm:ss across all environment locales.
 */

import type { AuditEvent, AuditDecision } from '../../../types/auditEvent'
import { formatTimestamp } from '../../../utils/date'

interface AuditTableProps {
  events: AuditEvent[]
  loading: boolean
}

// ── Badge Style Configurations ─────────────────────────────────────
const DECISION_CONFIG: Record<AuditDecision, string> = {
  ALLOW: 'bg-status-active/10 text-status-active border-status-active/20',
  DENY: 'bg-status-error/15 text-status-error border-status-error/30 font-semibold',
  APPROVAL_REQUIRED: 'bg-status-warning/10 text-status-warning border-status-warning/20',
  UNKNOWN: 'bg-border-primary/50 text-text-muted border-border-primary',
}

export default function AuditTable({ events, loading }: AuditTableProps) {
  const truncateId = (id: string) => {
    if (id.length <= 8) return id
    return `${id.slice(0, 8)}...`
  }

  if (loading) {
    return (
      <div className="divide-y divide-border-secondary">
        <div className="grid grid-cols-5 gap-4 px-6 py-4 bg-bg-secondary text-xs font-semibold text-text-muted uppercase">
          <span>Time</span>
          <span>Decision</span>
          <span>Agent</span>
          <span>Tool</span>
          <span className="text-right">Event ID</span>
        </div>
        {[1, 2].map((n) => (
          <div key={n} className="grid grid-cols-5 gap-4 px-6 py-4 items-center">
            <div className="h-4 w-32 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-5 w-16 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-24 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-24 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-16 bg-border-primary/40 rounded ml-auto animate-pulse" />
          </div>
        ))}
      </div>
    )
  }

  if (events.length === 0) {
    return (
      <div className="px-6 py-16 text-center space-y-2 bg-bg-surface">
        <h3 className="text-sm font-bold text-text-primary">
          No audit events logged.
        </h3>
        <p className="text-xs text-text-secondary max-w-sm mx-auto">
          Audit logs will be populated once agents trigger tools requests.
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto w-full">
      <table className="w-full text-left border-collapse min-w-[800px]">
        <thead>
          <tr className="bg-bg-secondary border-b border-border-secondary text-xs font-semibold text-text-muted uppercase tracking-wider">
            <th className="px-6 py-4">Time</th>
            <th className="px-6 py-4">Decision</th>
            <th className="px-6 py-4">Agent</th>
            <th className="px-6 py-4">Tool</th>
            <th className="px-6 py-4 text-right">Event ID</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border-secondary text-xs">
          {events.map((event) => (
            <tr key={event.id} className="hover:bg-bg-surface-hover/30 transition-colors">
              
              {/* Time */}
              <td className="px-6 py-4 text-text-secondary font-mono whitespace-nowrap">
                {formatTimestamp(event.timestamp)}
              </td>

              {/* Decision Badge */}
              <td className="px-6 py-4">
                <span className={`px-2 py-0.5 rounded border text-[10px] uppercase font-medium ${DECISION_CONFIG[event.decision]}`}>
                  {event.decision}
                </span>
              </td>

              {/* Agent ID */}
              <td className="px-6 py-4 text-text-secondary font-mono">
                {event.agentId}
              </td>

              {/* Tool ID */}
              <td className="px-6 py-4 text-text-secondary font-mono">
                {event.toolId}
              </td>

              {/* Truncated Event ID with tooltip */}
              <td className="px-6 py-4 text-right text-text-muted font-mono" title={event.id}>
                {truncateId(event.id)}
              </td>

            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
