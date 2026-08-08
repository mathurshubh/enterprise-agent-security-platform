/**
 * SessionTable — List of active agent interaction sessions.
 *
 * Renders the table view for registered agent sessions directly returned by the backend API.
 * Displays only fields that exist in the backend DTO:
 * Session ID, Agent ID, and Started At.
 *
 * Feature Folder Pattern:
 *   Located under `pages/Sessions/components/` as it is feature-specific.
 */

import type { Session } from '../../../types/session'
import { formatTimestamp } from '../../../utils/date'

export type SortField = 'id' | 'agentId' | 'startedAt'
export type SortDirection = 'asc' | 'desc'

interface SessionTableProps {
  sessions: Session[]
  loading: boolean
  sortField: SortField | null
  sortDirection: SortDirection
  onSort: (field: SortField) => void
}

export default function SessionTable({
  sessions,
  loading,
  sortField,
  sortDirection,
  onSort,
}: SessionTableProps) {
  if (loading) {
    return (
      <div className="divide-y divide-border-secondary">
        <div className="grid grid-cols-3 gap-4 px-6 py-4 bg-bg-secondary text-xs font-semibold text-text-muted uppercase">
          <span>Session ID</span>
          <span>Agent ID</span>
          <span>Started At</span>
        </div>
        {[1, 2, 3].map((n) => (
          <div key={n} className="grid grid-cols-3 gap-4 px-6 py-4 items-center">
            <div className="h-4 w-32 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-24 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-36 bg-border-primary/40 rounded animate-pulse" />
          </div>
        ))}
      </div>
    )
  }

  if (sessions.length === 0) {
    return (
      <div className="px-6 py-16 text-center space-y-2 bg-bg-surface">
        <h3 className="text-sm font-bold text-text-primary">
          No sessions registered.
        </h3>
        <p className="text-xs text-text-secondary max-w-sm mx-auto">
          No sessions were returned by the Management API.
        </p>
      </div>
    )
  }

  const renderSortIndicator = (field: SortField) => {
    if (sortField !== field) return <span className="text-text-muted/40 ml-1">↕</span>
    return <span className="text-accent-primary ml-1">{sortDirection === 'asc' ? '▲' : '▼'}</span>
  }

  return (
    <div className="overflow-x-auto w-full">
      <table className="w-full text-left border-collapse min-w-[600px]">
        <thead>
          <tr className="bg-bg-secondary border-b border-border-secondary text-xs font-semibold text-text-muted uppercase tracking-wider select-none">
            <th className="px-6 py-4 cursor-pointer hover:text-text-primary transition-colors" onClick={() => onSort('id')}>
              <div className="flex items-center">
                Session ID {renderSortIndicator('id')}
              </div>
            </th>

            <th className="px-6 py-4 cursor-pointer hover:text-text-primary transition-colors" onClick={() => onSort('agentId')}>
              <div className="flex items-center">
                Agent ID {renderSortIndicator('agentId')}
              </div>
            </th>

            <th className="px-6 py-4 cursor-pointer hover:text-text-primary transition-colors" onClick={() => onSort('startedAt')}>
              <div className="flex items-center">
                Started At {renderSortIndicator('startedAt')}
              </div>
            </th>

          </tr>
        </thead>
        <tbody className="divide-y divide-border-secondary text-xs">
          {sessions.map((session) => (
            <tr key={session.id} className="hover:bg-bg-surface-hover/30 transition-colors">
              
              {/* Session ID */}
              <td className="px-6 py-4 font-mono text-[11px] text-text-primary" title={session.id}>
                {session.id}
              </td>

              {/* Agent ID */}
              <td className="px-6 py-4 font-mono text-text-secondary">
                {session.agentId}
              </td>

              {/* Started At Timestamp */}
              <td className="px-6 py-4 font-mono text-text-secondary whitespace-nowrap">
                {formatTimestamp(session.startedAt)}
              </td>

            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
