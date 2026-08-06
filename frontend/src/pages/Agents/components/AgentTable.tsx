/**
 * AgentTable — List of registered agents.
 *
 * Renders the table view for registered agent identities, risk tiers,
 * status, and approved tools directly returned by the backend API.
 *
 * Feature Folder Pattern:
 *   Located under `pages/Agents/components/` as it is feature-specific.
 */

import type { Agent, AgentStatus, RiskTier } from '../../../types/agent'

export type SortField = 'name' | 'owner' | 'riskLevel' | 'status' | 'approvedTools'
export type SortDirection = 'asc' | 'desc'

interface AgentTableProps {
  agents: Agent[]
  loading: boolean
  sortField: SortField | null
  sortDirection: SortDirection
  onSort: (field: SortField) => void
}

// ── Badge Style Configurations ─────────────────────────────────────
const STATUS_CONFIG: Record<AgentStatus, string> = {
  ACTIVE: 'bg-status-active/10 text-status-active border-status-active/20',
  REGISTERED: 'bg-status-info/10 text-status-info border-status-info/20',
  SUSPENDED: 'bg-status-warning/10 text-status-warning border-status-warning/20',
  DISABLED: 'bg-status-error/10 text-status-error border-status-error/20',
}

const RISK_CONFIG: Record<RiskTier, string> = {
  LOW: 'bg-status-active/10 text-status-active border-status-active/20',
  MEDIUM: 'bg-status-warning/10 text-status-warning border-status-warning/20',
  HIGH: 'bg-status-error/15 text-status-error border-status-error/30 font-semibold',
  CRITICAL: 'bg-status-error/15 text-status-error border-status-error/30 font-semibold',
}

export default function AgentTable({
  agents,
  loading,
  sortField,
  sortDirection,
  onSort,
}: AgentTableProps) {
  if (loading) {
    return (
      <div className="divide-y divide-border-secondary">
        <div className="grid grid-cols-6 gap-4 px-6 py-4 bg-bg-secondary text-xs font-semibold text-text-muted uppercase">
          <span>Agent ID</span>
          <span>Display Name</span>
          <span>Owner</span>
          <span>Risk Tier</span>
          <span>Status</span>
          <span>Approved Tools</span>
        </div>
        {[1, 2, 3].map((n) => (
          <div key={n} className="grid grid-cols-6 gap-4 px-6 py-4 items-center">
            <div className="h-4 w-24 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-32 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-24 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-5 w-16 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-5 w-16 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-36 bg-border-primary/40 rounded animate-pulse" />
          </div>
        ))}
      </div>
    )
  }

  if (agents.length === 0) {
    return (
      <div className="px-6 py-16 text-center space-y-2 bg-bg-surface">
        <h3 className="text-sm font-bold text-text-primary">
          No agents registered.
        </h3>
        <p className="text-xs text-text-secondary max-w-sm mx-auto">
          No registered agents were returned by the Management API.
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
      <table className="w-full text-left border-collapse min-w-[700px]">
        <thead>
          <tr className="bg-bg-secondary border-b border-border-secondary text-xs font-semibold text-text-muted uppercase tracking-wider select-none">
            <th className="px-6 py-4">Agent ID</th>

            <th className="px-6 py-4 cursor-pointer hover:text-text-primary transition-colors" onClick={() => onSort('name')}>
              <div className="flex items-center">
                Display Name {renderSortIndicator('name')}
              </div>
            </th>

            <th className="px-6 py-4 cursor-pointer hover:text-text-primary transition-colors" onClick={() => onSort('owner')}>
              <div className="flex items-center">
                Owner {renderSortIndicator('owner')}
              </div>
            </th>

            <th className="px-6 py-4 cursor-pointer hover:text-text-primary transition-colors" onClick={() => onSort('riskLevel')}>
              <div className="flex items-center">
                Risk Tier {renderSortIndicator('riskLevel')}
              </div>
            </th>

            <th className="px-6 py-4 cursor-pointer hover:text-text-primary transition-colors" onClick={() => onSort('status')}>
              <div className="flex items-center">
                Status {renderSortIndicator('status')}
              </div>
            </th>

            <th className="px-6 py-4 cursor-pointer hover:text-text-primary transition-colors" onClick={() => onSort('approvedTools')}>
              <div className="flex items-center">
                Approved Tools {renderSortIndicator('approvedTools')}
              </div>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border-secondary text-xs">
          {agents.map((agent) => (
            <tr key={agent.id} className="hover:bg-bg-surface-hover/30 transition-colors">
              
              <td className="px-6 py-4 font-mono text-[11px] text-text-muted">
                {agent.id}
              </td>

              <td className="px-6 py-4 font-semibold text-text-primary">
                {agent.name}
              </td>

              <td className="px-6 py-4 text-text-secondary">
                {agent.owner}
              </td>

              <td className="px-6 py-4">
                <span className={`px-2 py-0.5 rounded border text-[10px] uppercase font-medium ${RISK_CONFIG[agent.riskLevel]}`}>
                  {agent.riskLevel}
                </span>
              </td>

              <td className="px-6 py-4">
                <span className={`px-2 py-0.5 rounded border text-[10px] uppercase font-medium ${STATUS_CONFIG[agent.status]}`}>
                  {agent.status}
                </span>
              </td>

              {/* Approved Tools count and tags */}
              <td className="px-6 py-4">
                {agent.approvedTools.length === 0 ? (
                  <span className="text-text-muted italic">0 tools</span>
                ) : (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-text-secondary font-medium mr-1">
                      ({agent.approvedTools.length})
                    </span>
                    {agent.approvedTools.map((tool) => (
                      <span
                        key={tool}
                        className="px-1.5 py-0.5 rounded bg-bg-surface border border-border-primary text-[10px] text-text-secondary font-mono"
                      >
                        {tool}
                      </span>
                    ))}
                  </div>
                )}
              </td>

            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
