/**
 * MetricCard — Reusable metric display card.
 *
 * Renders a labelled numeric or string metric value with an animated
 * loading skeleton when data is being fetched. Eliminates the duplicated
 * metric card JSX previously repeated across DashboardPage, SessionsPage,
 * AgentsPage, ToolsPage, DetectionRulesPage, and AuditTimelinePage.
 *
 * ADR-022 / 09-ui-component-architecture.md: Tier 2 Shared Domain Widget.
 */

interface MetricCardProps {
  label: string
  value: number | string
  loading?: boolean
  subtitle?: string
}

export default function MetricCard({ label, value, loading = false, subtitle }: MetricCardProps) {
  return (
    <div className="bg-bg-surface border border-border-secondary rounded-xl p-5 flex flex-col justify-between min-h-[110px]">
      <div className="text-xs font-medium text-text-muted uppercase tracking-wide">
        {label}
      </div>

      {loading ? (
        <div className="mt-2 h-8 w-24 bg-border-primary/40 rounded animate-pulse" />
      ) : (
        <div className="mt-2 text-2xl font-bold text-text-primary">
          {value}
        </div>
      )}

      {subtitle && !loading && (
        <div className="mt-1 text-xs text-text-muted">
          {subtitle}
        </div>
      )}
    </div>
  )
}
