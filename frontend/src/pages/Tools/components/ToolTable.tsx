/**
 * ToolTable — List of registered capability tools.
 *
 * REACT CONCEPT: "Presentational Component & Null Coalescing"
 * ──────────────────────────────────────────────────────────────────
 * Renders the table view for registered tools.  Unexposed backend parameters
 * are mapped to null by the service layer, and rendered as "—" placeholders
 * using null-coalescing (`?? '—'`) in this view.
 *
 * Table Layout Stability:
 *   Badges and conditional structures check for property existence first.
 *   When the backend API exposes these fields in the future, updating the DTO
 *   mapper in `toolService.ts` will instantly populate the cells without
 *   requiring layout modifications in this table component.
 */

import type { Tool } from '../../../types/tool'

interface ToolTableProps {
  tools: Tool[]
  loading: boolean
}

// ── Badge Style Configurations ─────────────────────────────────────
const STATUS_CONFIG: Record<string, string> = {
  ENABLED: 'bg-status-active/10 text-status-active border-status-active/20',
  DISABLED: 'bg-status-error/10 text-status-error border-status-error/20',
}

const RISK_CONFIG: Record<string, string> = {
  LOW: 'bg-status-active/10 text-status-active border-status-active/20',
  MEDIUM: 'bg-status-warning/10 text-status-warning border-status-warning/20',
  HIGH: 'bg-status-error/15 text-status-error border-status-error/30 font-semibold',
  CRITICAL: 'bg-status-error/15 text-status-error border-status-error/30 font-semibold',
}

export default function ToolTable({ tools, loading }: ToolTableProps) {
  if (loading) {
    return (
      <div className="divide-y divide-border-secondary">
        <div className="grid grid-cols-8 gap-4 px-6 py-4 bg-bg-secondary text-xs font-semibold text-text-muted uppercase">
          <span>Name</span>
          <span>Version</span>
          <span>Status</span>
          <span>Risk</span>
          <span>Category</span>
          <span>Timeout</span>
          <span>Approval</span>
          <span className="text-right">Actions</span>
        </div>
        {[1, 2].map((n) => (
          <div key={n} className="grid grid-cols-8 gap-4 px-6 py-4 items-center">
            <div className="h-4 w-28 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-12 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-16 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-16 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-20 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-12 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-16 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-6 w-12 bg-border-primary/40 rounded ml-auto animate-pulse" />
          </div>
        ))}
      </div>
    )
  }

  if (tools.length === 0) {
    return (
      <div className="px-6 py-16 text-center space-y-2 bg-bg-surface">
        <h3 className="text-sm font-bold text-text-primary">
          No tools registered.
        </h3>
        <p className="text-xs text-text-secondary max-w-sm mx-auto">
          Register an executable capability tool to begin audit tracking.
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
            <th className="px-6 py-4">Description</th>
            <th className="px-6 py-4">Version</th>
            <th className="px-6 py-4">Status</th>
            <th className="px-6 py-4">Risk Level</th>
            <th className="px-6 py-4">Category</th>
            <th className="px-6 py-4">Timeout</th>
            <th className="px-6 py-4">Approval</th>
            <th className="px-6 py-4 text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border-secondary text-xs">
          {tools.map((tool) => (
            <tr key={tool.id} className="hover:bg-bg-surface-hover/30 transition-colors">
              
              <td className="px-6 py-4">
                <div className="font-semibold text-text-primary">{tool.name}</div>
                <div className="text-[10px] text-text-muted mt-0.5 font-mono">{tool.id}</div>
              </td>

              <td className="px-6 py-4 text-text-secondary max-w-xs truncate" title={tool.description}>
                {tool.description}
              </td>

              <td className="px-6 py-4 text-text-secondary font-mono">{tool.version}</td>

              {/* Status Cell - Stable Layout */}
              <td className="px-6 py-4">
                {tool.status ? (
                  <span className={`px-2 py-0.5 rounded border text-[10px] uppercase font-medium ${STATUS_CONFIG[tool.status.toUpperCase()] ?? 'bg-bg-surface border-border-primary text-text-secondary'}`}>
                    {tool.status}
                  </span>
                ) : (
                  <span className="text-text-muted">—</span>
                )}
              </td>

              {/* Risk Level Cell - Stable Layout */}
              <td className="px-6 py-4">
                {tool.riskLevel ? (
                  <span className={`px-2 py-0.5 rounded border text-[10px] uppercase font-medium ${RISK_CONFIG[tool.riskLevel.toUpperCase()] ?? 'bg-bg-surface border-border-primary text-text-secondary'}`}>
                    {tool.riskLevel}
                  </span>
                ) : (
                  <span className="text-text-muted">—</span>
                )}
              </td>

              {/* Category Cell - Null Coalescing */}
              <td className="px-6 py-4 text-text-secondary">
                {tool.category ?? <span className="text-text-muted">—</span>}
              </td>

              {/* Timeout Cell */}
              <td className="px-6 py-4 text-text-secondary font-mono">
                {tool.timeoutSeconds !== null && tool.timeoutSeconds !== undefined ? (
                  `${tool.timeoutSeconds}s`
                ) : (
                  <span className="text-text-muted">—</span>
                )}
              </td>

              {/* Approval Cell */}
              <td className="px-6 py-4">
                {tool.approvalRequired !== null && tool.approvalRequired !== undefined ? (
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${tool.approvalRequired ? 'bg-status-warning/10 text-status-warning border border-status-warning/20' : 'bg-bg-surface border border-border-primary text-text-secondary'}`}>
                    {tool.approvalRequired ? 'Yes' : 'No'}
                  </span>
                ) : (
                  <span className="text-text-muted">—</span>
                )}
              </td>

              <td className="px-6 py-4 text-right">
                <div className="flex items-center justify-end gap-2">
                  <button
                    disabled
                    aria-label={`View tool ${tool.name}`}
                    title="View action is not yet implemented"
                    className="px-2 py-1 bg-border-primary/50 text-text-muted rounded hover:bg-bg-surface cursor-not-allowed transition-colors text-[10px]"
                  >
                    View
                  </button>
                  <button
                    disabled
                    aria-label={`Configure tool ${tool.name}`}
                    title="Configure action is not yet implemented"
                    className="px-2 py-1 bg-border-primary/50 text-text-muted rounded hover:bg-bg-surface cursor-not-allowed transition-colors text-[10px]"
                  >
                    Configure
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
