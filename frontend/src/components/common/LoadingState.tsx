/**
 * LoadingState — Centered full-area loading indicator.
 *
 * Renders during initial data fetch operations. Provides a consistent
 * skeleton/spinner experience across all console pages.
 *
 * ADR-022 / 09-ui-component-architecture.md: Tier 2 Shared Domain Widget.
 */

interface LoadingStateProps {
  label?: string
}

export default function LoadingState({ label = 'Loading...' }: LoadingStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3" role="status" aria-label={label}>
      {/* Pulsing ring spinner — no icon library dependency */}
      <div className="w-8 h-8 rounded-full border-2 border-border-primary border-t-accent-primary animate-spin" />
      <span className="text-xs text-text-muted">{label}</span>
    </div>
  )
}
