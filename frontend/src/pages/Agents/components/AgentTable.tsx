/**
 * AgentTable — List of registered agents.
 *
 * REACT CONCEPT: "Presentational Component"
 * ──────────────────────────────────────────────────────────────────
 * Renders the table view, mapping badge styles from configuration objects
 * to avoid magic strings or conditional chains.
 *
 * Feature Folder Pattern:
 *   Located under `pages/Agents/components/` as it is feature-specific.
 *
 * Accessibility features:
 *   - Proper table head `<th>` semantics.
 *   - Placeholder actions disabled and labeled with helper titles.
 */

import type { Agent, AgentStatus, RiskTier } from '../../../types/agent'

interface AgentTableProps {
  agents: Agent[]
  loading: boolean
}

// ── Badge Style Configurations ─────────────────────────────────────
// Centralized mapping objects to avoid magic string comparison chains.
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

export default function AgentTable({ agents, loading }: AgentTableProps) {
  if (loading) {
    return (
      <div className="divide-y divide-border-secondary">
        <div className="grid grid-cols-8 gap-4 px-6 py-4 bg-bg-secondary text-xs font-semibold text-text-muted uppercase">
          <span>Name</span>
          <span>Status</span>
          <span>Risk</span>
          <span>Framework</span>
          <span>Provider</span>
          <span>Owner</span>
          <span>Last Seen</span>
          <span className="text-right">Actions</span>
        </div>
        {[1, 2, 3].map((n) => (
          <div key={n} className="grid grid-cols-8 gap-4 px-6 py-4 items-center">
            <div className="h-4 w-28 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-5 w-16 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-5 w-16 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-16 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-16 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-20 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-16 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-6 w-12 bg-border-primary/40 rounded ml-auto animate-pulse" />
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
          Register an AI agent to begin governance.
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto w-full">
      <table className="w-full text-left border-collapse min-w-[800px]">
        <thead>
          <tr className="bg-bg-secondary border-b border-border-secondary text-xs font-semibold text-text-muted uppercase tracking-wider">
            <th className="px-6 py-4">Name / ID</th>
            <th className="px-6 py-4">Status</th>
            <th className="px-6 py-4">Risk</th>
            <th className="px-6 py-4">Framework</th>
            <th className="px-6 py-4">Provider</th>
            <th className="px-6 py-4">Owner</th>
            <th className="px-6 py-4">Approved Tools</th>
            <th className="px-6 py-4 text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border-secondary text-xs">
          {agents.map((agent) => (
            <tr key={agent.id} className="hover:bg-bg-surface-hover/30 transition-colors">
              
              <td className="px-6 py-4">
                <div className="font-semibold text-text-primary">{agent.name}</div>
                <div className="text-[10px] text-text-muted mt-0.5 font-mono">{agent.id}</div>
              </td>

              <td className="px-6 py-4">
                <span className={`px-2 py-0.5 rounded border text-[10px] uppercase font-medium ${STATUS_CONFIG[agent.status]}`}>
                  {agent.status}
                </span>
              </td>

              <td className="px-6 py-4">
                <span className={`px-2 py-0.5 rounded border text-[10px] uppercase font-medium ${RISK_CONFIG[agent.riskLevel]}`}>
                  {agent.riskLevel}
                </span>
              </td>

              <td className="px-6 py-4 text-text-secondary">{agent.framework ?? '—'}</td>

              <td className="px-6 py-4 text-text-secondary">{agent.provider ?? '—'}</td>

              <td className="px-6 py-4 text-text-secondary">{agent.owner}</td>

              {/* Tools tags */}
              <td className="px-6 py-4">
                {agent.approvedTools.length === 0 ? (
                  <span className="text-text-muted italic">None</span>
                ) : (
                  <div className="flex flex-wrap gap-1">
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

              {/* Action placeholders */}
              <td className="px-6 py-4 text-right">
                <div className="flex items-center justify-end gap-2">
                  <button
                    disabled
                    aria-label={`View agent ${agent.name}`}
                    title="View action is not yet implemented"
                    className="px-2 py-1 bg-border-primary/50 text-text-muted rounded hover:bg-bg-surface cursor-not-allowed transition-colors text-[10px]"
                  >
                    View
                  </button>
                  <button
                    disabled
                    aria-label={`Edit agent ${agent.name}`}
                    title="Edit action is not yet implemented"
                    className="px-2 py-1 bg-border-primary/50 text-text-muted rounded hover:bg-bg-surface cursor-not-allowed transition-colors text-[10px]"
                  >
                    Edit
                  </button>
                  <button
                    disabled
                    aria-label={`Disable agent ${agent.name}`}
                    title="Disable action is not yet implemented"
                    className="px-2 py-1 bg-status-error/5 text-status-error/40 border border-status-error/10 rounded cursor-not-allowed text-[10px]"
                  >
                    Disable
                  </button>
                </div>
              </td>

            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
