/**
 * Header — Top bar for the Enterprise Security Console.
 *
 * REACT CONCEPT: "Props"
 * ──────────────────────────────────────────────────────────────────
 * Props (short for "properties") are the way React components
 * receive data from their parent.  Think of them like function
 * arguments in Python.
 *
 * When a parent renders <Header title="Dashboard" />, React passes
 * { title: "Dashboard" } as the props object to this function.
 *
 * TypeScript enforces the shape of props via an interface, so you
 * get compile-time errors if a required prop is missing — similar
 * to how Pydantic validates request bodies.
 *
 * ADR-009 COMPLIANCE:
 *   - Displays placeholder information only.
 *   - No business logic, no API calls, no authentication.
 */

interface HeaderProps {
  title: string
}

export default function Header({ title }: HeaderProps) {
  return (
    <header className="h-14 bg-bg-secondary border-b border-border-primary flex items-center justify-between px-6">

      {/* ── Page Title ─────────────────────────────────────────── */}
      <h1 className="text-base font-semibold text-text-primary">
        {title}
      </h1>

      {/* ── Right-side Placeholders ────────────────────────────── */}
      <div className="flex items-center gap-5">
        <span className="flex items-center gap-1.5 text-xs text-status-active">
          <span className="w-1.5 h-1.5 rounded-full bg-status-active" />
          Operational
        </span>
        <span className="text-xs text-text-muted">
          v0.9.0
        </span>
        <div className="w-px h-5 bg-border-primary" />
        <span className="text-xs text-text-secondary">
          Security Engineer
        </span>
      </div>
    </header>
  )
}
