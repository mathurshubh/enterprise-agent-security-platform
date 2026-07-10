/**
 * DashboardPage — Central landing page.
 *
 * ADR-009: "A central landing page displaying high-level security
 * metrics: total active agents, tool counts, registered detection
 * rules, historical audit volume."
 *
 * This is a placeholder.  PR #49 will implement the actual
 * dashboard widgets backed by GET /api/v1/info.
 */

export default function DashboardPage() {
  return (
    <div className="space-y-6">

      {/* Page heading */}
      <div>
        <h2 className="text-xl font-bold text-text-primary">
          Security Overview
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          High-level security metrics for the Enterprise Agent Security Platform.
        </p>
      </div>

      {/* Placeholder metric cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Active Agents',   value: '—' },
          { label: 'Registered Tools', value: '—' },
          { label: 'Detection Rules', value: '—' },
          { label: 'Audit Events',    value: '—' },
        ].map((card) => (
          <div
            key={card.label}
            className="bg-bg-surface border border-border-secondary rounded-xl p-5"
          >
            <div className="text-xs font-medium text-text-muted uppercase tracking-wide">
              {card.label}
            </div>
            <div className="mt-2 text-2xl font-bold text-text-primary">
              {card.value}
            </div>
          </div>
        ))}
      </div>

      {/* Empty state */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl p-8 text-center">
        <p className="text-sm text-text-muted">
          Dashboard widgets will be implemented in PR #49 using data from the Enterprise Management API.
        </p>
      </div>
    </div>
  )
}
