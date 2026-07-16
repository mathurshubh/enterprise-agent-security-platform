/**
 * ScenarioTable — List of registered security scenarios.
 *
 * REACT CONCEPT: "Presentational Component"
 * ──────────────────────────────────────────────────────────────────
 * Renders the table list view, mapping badge styles from configuration objects
 * to keep rendering declarative.
 */

import type { Scenario, ScenarioSeverity } from '../../../types/scenario'

interface ScenarioTableProps {
  scenarios: Scenario[]
  loading: boolean
}

// ── Badge Style Configurations ─────────────────────────────────────
const SEVERITY_CONFIG: Record<ScenarioSeverity, string> = {
  LOW: 'bg-status-active/10 text-status-active border-status-active/20',
  MEDIUM: 'bg-status-warning/10 text-status-warning border-status-warning/20',
  HIGH: 'bg-status-error/15 text-status-error border-status-error/30 font-semibold',
  CRITICAL: 'bg-status-error/15 text-status-error border-status-error/30 font-semibold',
}

const RESPONSE_CONFIG: Record<string, string> = {
  MONITOR: 'bg-status-info/10 text-status-info border-status-info/20',
  ALERT: 'bg-status-warning/10 text-status-warning border-status-warning/20',
  REQUIRE_APPROVAL: 'bg-status-error/15 text-status-error border-status-error/30 font-semibold',
  SUSPEND_AGENT: 'bg-status-error/15 text-status-error border-status-error/30 font-semibold',
}

export default function ScenarioTable({ scenarios, loading }: ScenarioTableProps) {
  if (loading) {
    return (
      <div className="divide-y divide-border-secondary animate-pulse">
        <div className="grid grid-cols-5 gap-4 px-6 py-4 bg-bg-secondary text-xs font-semibold text-text-muted uppercase">
          <span>Scenario</span>
          <span>Category</span>
          <span>Severity</span>
          <span>Expected Detection</span>
          <span>Expected Response</span>
        </div>
        {[1, 2, 3].map((n) => (
          <div key={n} className="grid grid-cols-5 gap-4 px-6 py-4 items-center">
            <div className="space-y-1">
              <div className="h-4 w-32 bg-border-primary/40 rounded" />
              <div className="h-3 w-16 bg-border-primary/40 rounded" />
            </div>
            <div className="h-4 w-20 bg-border-primary/40 rounded" />
            <div className="h-5 w-16 bg-border-primary/40 rounded" />
            <div className="h-4 w-28 bg-border-primary/40 rounded" />
            <div className="h-5 w-24 bg-border-primary/40 rounded" />
          </div>
        ))}
      </div>
    )
  }

  if (scenarios.length === 0) {
    return (
      <div className="px-6 py-16 text-center space-y-2 bg-bg-surface">
        <h3 className="text-sm font-bold text-text-primary">
          No scenarios found.
        </h3>
        <p className="text-xs text-text-secondary max-w-sm mx-auto">
          No registered scenarios match the active search filter.
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto w-full">
      <table className="w-full text-left border-collapse min-w-[800px]">
        <thead>
          <tr className="bg-bg-secondary border-b border-border-secondary text-xs font-semibold text-text-muted uppercase tracking-wider">
            <th className="px-6 py-4">Scenario</th>
            <th className="px-6 py-4">Category</th>
            <th className="px-6 py-4">Severity</th>
            <th className="px-6 py-4">Expected Detection</th>
            <th className="px-6 py-4">Expected Response</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border-secondary text-xs">
          {scenarios.map((scenario) => (
            <tr key={scenario.id} className="hover:bg-bg-surface-hover/30 transition-colors">
              
              <td className="px-6 py-4">
                <div className="font-semibold text-text-primary">{scenario.name}</div>
                <div className="text-[10px] text-text-muted mt-0.5 font-mono">{scenario.id}</div>
                {scenario.description && (
                  <p className="text-[11px] text-text-secondary mt-1 max-w-md">
                    {scenario.description}
                  </p>
                )}
              </td>

              <td className="px-6 py-4 text-text-secondary font-medium">
                {scenario.category}
              </td>

              <td className="px-6 py-4">
                <span className={`px-2 py-0.5 rounded border text-[10px] uppercase font-medium ${SEVERITY_CONFIG[scenario.severity]}`}>
                  {scenario.severity}
                </span>
              </td>

              <td className="px-6 py-4">
                {scenario.expectedDetectionRules.length === 0 ? (
                  <span className="text-text-muted italic">None (Allowed)</span>
                ) : (
                  <div className="flex flex-wrap gap-1">
                    {scenario.expectedDetectionRules.map((rule) => (
                      <span
                        key={rule}
                        className="px-1.5 py-0.5 rounded bg-bg-surface border border-border-primary text-[10px] text-text-secondary font-mono"
                      >
                        {rule}
                      </span>
                    ))}
                  </div>
                )}
              </td>

              <td className="px-6 py-4">
                <span className={`px-2 py-0.5 rounded border text-[10px] uppercase font-medium ${RESPONSE_CONFIG[scenario.expectedResponse] || 'border-border-primary text-text-secondary'}`}>
                  {scenario.expectedResponse}
                </span>
              </td>

            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
