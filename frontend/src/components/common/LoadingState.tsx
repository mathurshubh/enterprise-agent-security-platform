/**
 * LoadingState — Centered loading indicator.
 *
 * Two rendering modes:
 *   default    — Centered within its container (used within page content areas).
 *   fullscreen — Centers in the full viewport (used as Suspense fallback in App.tsx
 *                while lazy-loaded page chunks are being fetched).
 *
 * ADR-022 / 09-ui-component-architecture.md: Tier 2 Shared Domain Widget.
 */

interface LoadingStateProps {
  label?: string
  /**
   * When true, renders centered in the full viewport rather than
   * relative to the parent container. Used as the React.Suspense
   * fallback in App.tsx during route chunk loading.
   */
  fullscreen?: boolean
}

export default function LoadingState({ label = 'Loading...', fullscreen = false }: LoadingStateProps) {
  if (fullscreen) {
    return (
      <div
        className="fixed inset-0 flex flex-col items-center justify-center gap-3 bg-bg-primary"
        role="status"
        aria-label={label}
      >
        <div className="w-8 h-8 rounded-full border-2 border-border-primary border-t-accent-primary animate-spin" />
        <span className="text-xs text-text-muted">{label}</span>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3" role="status" aria-label={label}>
      {/* Pulsing ring spinner — no icon library dependency */}
      <div className="w-8 h-8 rounded-full border-2 border-border-primary border-t-accent-primary animate-spin" />
      <span className="text-xs text-text-muted">{label}</span>
    </div>
  )
}
