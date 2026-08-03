/**
 * Header — Top navigation bar for the Enterprise Security Console.
 *
 * Displays the current page title, platform operational status indicator,
 * version badge, and persona context. All values are purely presentational.
 *
 * Version badge dynamically populated from package.json via __APP_VERSION__.
 *
 * ADR-009 / ADR-022 compliance:
 *   - No business logic, no API calls, no authentication.
 *   - Platform version badge consumes global __APP_VERSION__.
 */

interface HeaderProps {
  title: string
}

export default function Header({ title }: HeaderProps) {
  return (
    <header className="h-14 bg-bg-secondary border-b border-border-primary flex items-center justify-between px-6 shrink-0">

      {/* ── Page Title ──────────────────────────────────────────── */}
      <h1 className="text-base font-semibold text-text-primary">
        {title}
      </h1>

      {/* ── Right-side Status Indicators ────────────────────────── */}
      <div className="flex items-center gap-5">
        <span className="flex items-center gap-1.5 text-xs text-status-active">
          <span className="w-1.5 h-1.5 rounded-full bg-status-active" aria-hidden="true" />
          Operational
        </span>
        <span className="text-xs text-text-muted">v{__APP_VERSION__}</span>
        <div className="w-px h-5 bg-border-primary" aria-hidden="true" />
        <span className="text-xs text-text-secondary">Security Engineer</span>
      </div>

    </header>
  )
}
