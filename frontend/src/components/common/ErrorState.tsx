/**
 * ErrorState — Standardized API error display.
 *
 * Renders when backend service calls fail. Eliminates the duplicated
 * inline error JSX previously defined in every page component.
 * Supports Principle 10 (Graceful Degradation): baseline management
 * capabilities must display meaningful error context, not silent failures.
 *
 * ADR-022 / 09-ui-component-architecture.md: Tier 2 Shared Domain Widget.
 */

interface ErrorStateProps {
  message: string
  /** Optional additional context shown below the primary message. */
  detail?: string
}

export default function ErrorState({ message, detail }: ErrorStateProps) {
  return (
    <div className="bg-status-error/10 border border-status-error/30 rounded-xl p-4 flex flex-col gap-1.5">
      <div className="text-xs font-semibold text-status-error uppercase tracking-wider">
        Connection Error
      </div>
      <p className="text-xs text-text-secondary leading-relaxed">
        {message}
      </p>
      {detail ? (
        <div className="text-[10px] text-text-muted mt-1">
          {detail}
        </div>
      ) : (
        <div className="text-[10px] text-text-muted mt-1">
          Ensure the Enterprise Agent Security Platform backend service is running and accessible at the management port.
        </div>
      )}
    </div>
  )
}
