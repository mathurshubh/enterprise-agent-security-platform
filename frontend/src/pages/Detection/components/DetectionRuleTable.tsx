/**
 * DetectionRuleTable — List of active threat detection rules.
 *
 * REACT CONCEPT: "Presentational Component & Null Coalescing"
 * ──────────────────────────────────────────────────────────────────
 * Renders the table view for active detection rules. Unexposed fields
 * (like status) are rendered as "—" placeholders using null-coalescing.
 */

import type { DetectionRule, DetectionCategory } from '../../../types/detectionRule'

interface DetectionRuleTableProps {
  rules: DetectionRule[]
  loading: boolean
}

// ── Category Config Lookup ─────────────────────────────────────────
const CATEGORY_LABELS: Record<DetectionCategory, string> = {
  PROMPT_SECURITY: 'Prompt Security',
  DATA_SECURITY: 'Data Security',
  TOOL_SECURITY: 'Tool Security',
  IDENTITY_SECURITY: 'Identity Security',
  BEHAVIORAL_SECURITY: 'Behavioral Security',
  POLICY_SECURITY: 'Policy Security',
  UNKNOWN: 'Unknown',
}

const CATEGORY_COLORS: Record<DetectionCategory, string> = {
  PROMPT_SECURITY: 'bg-status-active/10 text-status-active border-status-active/20',
  DATA_SECURITY: 'bg-status-info/10 text-status-info border-status-info/20',
  TOOL_SECURITY: 'bg-status-warning/10 text-status-warning border-status-warning/20',
  IDENTITY_SECURITY: 'bg-status-error/10 text-status-error border-status-error/20',
  BEHAVIORAL_SECURITY: 'bg-accent-primary/10 text-accent-primary border-accent-primary/20',
  POLICY_SECURITY: 'bg-status-info/15 text-status-info border-status-info/30',
  UNKNOWN: 'bg-border-primary/50 text-text-muted border-border-primary',
}

export default function DetectionRuleTable({ rules, loading }: DetectionRuleTableProps) {
  if (loading) {
    return (
      <div className="divide-y divide-border-secondary">
        <div className="grid grid-cols-5 gap-4 px-6 py-4 bg-bg-secondary text-xs font-semibold text-text-muted uppercase">
          <span>Rule Name</span>
          <span>Category</span>
          <span>Description</span>
          <span>Mapped Controls</span>
          <span className="text-right">Actions</span>
        </div>
        {[1, 2].map((n) => (
          <div key={n} className="grid grid-cols-5 gap-4 px-6 py-4 items-center">
            <div className="h-4 w-28 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-5 w-20 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-40 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-24 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-6 w-12 bg-border-primary/40 rounded ml-auto animate-pulse" />
          </div>
        ))}
      </div>
    )
  }

  if (rules.length === 0) {
    return (
      <div className="px-6 py-16 text-center space-y-2 bg-bg-surface">
        <h3 className="text-sm font-bold text-text-primary">
          No detection rules registered.
        </h3>
        <p className="text-xs text-text-secondary max-w-sm mx-auto">
          Add a detection rule to begin security threat monitoring.
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto w-full">
      <table className="w-full text-left border-collapse min-w-[800px]">
        <thead>
          <tr className="bg-bg-secondary border-b border-border-secondary text-xs font-semibold text-text-muted uppercase tracking-wider">
            <th className="px-6 py-4">Rule Name</th>
            <th className="px-6 py-4">Category</th>
            <th className="px-6 py-4">Description</th>
            <th className="px-6 py-4">Mapped Controls</th>
            <th className="px-6 py-4">Status</th>
            <th className="px-6 py-4 text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border-secondary text-xs">
          {rules.map((rule) => (
            <tr key={rule.name} className="hover:bg-bg-surface-hover/30 transition-colors">
              
              {/* Name */}
              <td className="px-6 py-4 font-semibold text-text-primary">
                {rule.name}
              </td>

              {/* Category Badge */}
              <td className="px-6 py-4">
                <span className={`px-2 py-0.5 rounded border text-[10px] uppercase font-medium ${CATEGORY_COLORS[rule.category]}`}>
                  {CATEGORY_LABELS[rule.category]}
                </span>
              </td>

              {/* Description */}
              <td className="px-6 py-4 text-text-secondary max-w-xs truncate" title={rule.description}>
                {rule.description}
              </td>

              {/* Mapped Controls Tags */}
              <td className="px-6 py-4">
                {rule.controls.length === 0 ? (
                  <span className="text-text-muted italic">None</span>
                ) : (
                  <div className="flex flex-wrap gap-1">
                    {rule.controls.map((ctrl) => (
                      <span
                        key={`${ctrl.framework}-${ctrl.controlId}`}
                        title={`${ctrl.title} (v${ctrl.version})`}
                        className="px-1.5 py-0.5 rounded bg-bg-surface border border-border-primary text-[10px] text-text-secondary font-mono"
                      >
                        {ctrl.framework}: {ctrl.controlId}
                      </span>
                    ))}
                  </div>
                )}
              </td>

              {/* Status - Null Coalescing */}
              <td className="px-6 py-4 text-text-muted italic">
                {rule.status ?? '—'}
              </td>

              {/* Action placeholders */}
              <td className="px-6 py-4 text-right">
                <div className="flex items-center justify-end gap-2">
                  <button
                    disabled
                    aria-label={`View detection rule ${rule.name}`}
                    title="View action is not yet implemented"
                    className="px-2 py-1 bg-border-primary/50 text-text-muted rounded hover:bg-bg-surface cursor-not-allowed transition-colors text-[10px]"
                  >
                    View
                  </button>
                  <button
                    disabled
                    aria-label={`Configure detection rule ${rule.name}`}
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
