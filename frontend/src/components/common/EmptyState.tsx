/**
 * EmptyState — Standardized empty-state display.
 *
 * Renders when a backend API returns an empty payload. Per Principle 1
 * (Backend Is Truth), the console never fabricates synthetic data —
 * it displays a clear empty state instead.
 *
 * ADR-022 / 09-ui-component-architecture.md: Tier 2 Shared Domain Widget.
 */

interface EmptyStateProps {
  title: string
  description?: string
  /** Optional call-to-action element (e.g., a link or button). */
  action?: React.ReactNode
}

export default function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
      {/* Simple visual indicator — icon system to be introduced in a future UI refinement PR */}
      <div className="w-12 h-12 rounded-full bg-bg-surface border border-border-secondary flex items-center justify-center mb-4">
        <span className="text-xl text-text-muted select-none" aria-hidden="true">—</span>
      </div>

      <div className="text-sm font-semibold text-text-primary">
        {title}
      </div>

      {description && (
        <p className="mt-1.5 text-xs text-text-secondary max-w-sm leading-relaxed">
          {description}
        </p>
      )}

      {action && (
        <div className="mt-4">
          {action}
        </div>
      )}
    </div>
  )
}
