/**
 * Header — Top navigation bar for the Enterprise Security Console.
 *
 * Displays the current page title, platform operational status indicator,
 * version badge, and persona context.
 *
 * Release identity consumes canonical platform metadata from /version with a
 * build-time fallback to __APP_VERSION__. If the API is unreachable, the
 * operational indicator explicitly states "Connection unavailable" rather than
 * falsely implying that the platform is operational.
 */

import { usePlatformMetadata } from '../../hooks/usePlatformMetadata'

interface HeaderProps {
  title: string
}

export default function Header({ title }: HeaderProps) {
  const { data: metadata, isError } = usePlatformMetadata()

  const displayVersion = metadata?.version ?? __APP_VERSION__
  const isOperational = !isError && Boolean(metadata)

  return (
    <header className="h-14 bg-bg-secondary border-b border-border-primary flex items-center justify-between px-6 shrink-0">

      {/* ── Page Title ──────────────────────────────────────────── */}
      <h1 className="text-base font-semibold text-text-primary">
        {title}
      </h1>

      {/* ── Right-side Status Indicators ────────────────────────── */}
      <div className="flex items-center gap-5">
        {isOperational ? (
          <span className="flex items-center gap-1.5 text-xs text-status-active">
            <span className="w-1.5 h-1.5 rounded-full bg-status-active" aria-hidden="true" />
            Operational
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-xs text-status-error">
            <span className="w-1.5 h-1.5 rounded-full bg-status-error" aria-hidden="true" />
            Connection unavailable
          </span>
        )}
        <span className="text-xs text-text-muted">v{displayVersion}</span>
        <div className="w-px h-5 bg-border-primary" aria-hidden="true" />
        <span className="text-xs text-text-secondary">Security Engineer</span>
      </div>

    </header>
  )
}
