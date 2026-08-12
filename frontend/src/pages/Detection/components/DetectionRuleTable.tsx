/**
 * DetectionRuleTable — List of active threat detection rules.
 *
 * Renders the table view for active detection rules directly returned by the backend API.
 * Displays only fields that actually exist in the backend DTO:
 * Rule Name, Category, Description, and Mapped Controls.
 *
 * Feature Folder Pattern:
 *   Located under `pages/Detection/components/` as it is feature-specific.
 */

import type { DetectionRule, DetectionCategory } from '../../../types/detectionRule'

export type SortField = 'name' | 'category' | 'description' | 'controls'
export type SortDirection = 'asc' | 'desc'

interface DetectionRuleTableProps {
  rules: DetectionRule[]
  loading: boolean
  sortField: SortField | null
  sortDirection: SortDirection
  onSort: (field: SortField) => void
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

export default function DetectionRuleTable({
  rules,
  loading,
  sortField,
  sortDirection,
  onSort,
}: DetectionRuleTableProps) {
  if (loading) {
    return (
      <div className="divide-y divide-border-secondary">
        <div className="grid grid-cols-4 gap-4 px-6 py-4 bg-bg-secondary text-xs font-semibold text-text-muted uppercase">
          <span>Rule Name</span>
          <span>Category</span>
          <span>Description</span>
          <span>Mapped Controls</span>
        </div>
        {[1, 2, 3].map((n) => (
          <div key={n} className="grid grid-cols-4 gap-4 px-6 py-4 items-center">
            <div className="h-4 w-32 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-5 w-24 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-48 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-28 bg-border-primary/40 rounded animate-pulse" />
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
          No registered detection rules were returned by the Management API.
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
      <table className="w-full text-left border-collapse min-w-[750px]">
        <thead>
          <tr className="bg-bg-secondary border-b border-border-secondary text-xs font-semibold text-text-muted uppercase tracking-wider select-none">
            <th className="px-6 py-4 cursor-pointer hover:text-text-primary transition-colors" onClick={() => onSort('name')}>
              <div className="flex items-center">
                Rule Name {renderSortIndicator('name')}
              </div>
            </th>

            <th className="px-6 py-4 cursor-pointer hover:text-text-primary transition-colors" onClick={() => onSort('category')}>
              <div className="flex items-center">
                Category {renderSortIndicator('category')}
              </div>
            </th>

            <th className="px-6 py-4 cursor-pointer hover:text-text-primary transition-colors" onClick={() => onSort('description')}>
              <div className="flex items-center">
                Description {renderSortIndicator('description')}
              </div>
            </th>

            <th className="px-6 py-4 cursor-pointer hover:text-text-primary transition-colors" onClick={() => onSort('controls')}>
              <div className="flex items-center">
                Mapped Controls {renderSortIndicator('controls')}
              </div>
            </th>
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

            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
