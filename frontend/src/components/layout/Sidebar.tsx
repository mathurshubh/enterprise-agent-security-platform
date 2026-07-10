/**
 * Sidebar — Primary navigation for the Enterprise Security Console.
 *
 * REACT CONCEPT: "Component"
 * ──────────────────────────────────────────────────────────────────
 * A React component is a function that returns JSX (HTML-like syntax
 * that compiles to JavaScript).  Components are the building blocks
 * of every React application — similar to how Python classes are the
 * building blocks of your backend services.
 *
 * Key differences from backend code:
 *   - A component is a function, not a class.
 *   - It returns UI markup (JSX), not data.
 *   - React calls this function every time it needs to re-render.
 *
 * REACT CONCEPT: "NavLink" (from React Router)
 * ──────────────────────────────────────────────────────────────────
 * NavLink is like an <a> tag but integrated with React Router's
 * client-side routing.  When clicked, it updates the URL and
 * renders the matching page WITHOUT a full page reload.
 *
 * NavLink also provides an `isActive` boolean via a render function,
 * which we use to highlight the current page in the sidebar.
 *
 * ADR-009 COMPLIANCE:
 *   - Navigation entries map 1:1 to the Initial Pages section.
 *   - Coverage and Findings are omitted (marked as Roadmap in ADR-009).
 */

import { NavLink } from 'react-router-dom'

/**
 * Navigation item definition.
 *
 * TYPESCRIPT CONCEPT: "Interface"
 * ──────────────────────────────────────────────────────────────────
 * An interface defines the shape of an object — like a Pydantic
 * model defines the shape of a request body.  TypeScript checks
 * at compile time that every NavItem has all required fields.
 */
interface NavItem {
  label: string
  path: string
}

/**
 * The sidebar navigation entries.
 * Each entry maps to an ADR-009 Initial Page.
 */
const navItems: NavItem[] = [
  { label: 'Dashboard',       path: '/' },
  { label: 'Agents',          path: '/agents' },
  { label: 'Tools',           path: '/tools' },
  { label: 'Detection Rules', path: '/detection' },
  { label: 'Audit Timeline',  path: '/audit' },
]

export default function Sidebar() {
  return (
    <aside className="fixed top-0 left-0 h-screen w-60 bg-bg-secondary border-r border-border-primary flex flex-col z-30">

      {/* ── Brand ──────────────────────────────────────────────── */}
      <div className="px-5 py-5 border-b border-border-primary">
        <div className="text-xs font-semibold tracking-widest uppercase text-accent-primary">
          Enterprise
        </div>
        <div className="text-sm font-bold text-text-primary mt-0.5">
          Security Console
        </div>
      </div>

      {/* ── Navigation ─────────────────────────────────────────── */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) =>
              [
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors duration-150',
                isActive
                  ? 'bg-accent-primary/15 text-accent-primary'
                  : 'text-text-secondary hover:bg-bg-surface-hover hover:text-text-primary',
              ].join(' ')
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* ── Footer ─────────────────────────────────────────────── */}
      <div className="px-5 py-4 border-t border-border-primary">
        <div className="text-xs text-text-muted">
          Platform v0.9.0
        </div>
      </div>
    </aside>
  )
}
