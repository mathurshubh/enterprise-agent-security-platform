/**
 * AppLayout — Application shell that wraps every page.
 *
 * REACT CONCEPT: "Layout" with "Outlet"
 * ──────────────────────────────────────────────────────────────────
 * In React Router, a "layout route" is a parent route that renders
 * shared UI (sidebar, header) around its child routes.  The child
 * route's component is injected at the <Outlet /> position.
 *
 * This is conceptually similar to template inheritance in Jinja2:
 *   - The layout is the base template.
 *   - <Outlet /> is the {% block content %} placeholder.
 *   - Each page fills in the content block.
 *
 * REACT CONCEPT: "useLocation" hook
 * ──────────────────────────────────────────────────────────────────
 * Hooks are functions that let components "hook into" React features
 * like state, context, or — in this case — the current URL.
 *
 * `useLocation()` returns the current browser URL.  We use it to
 * derive the page title for the Header.  This is a read-only
 * operation — the layout never modifies routing state.
 *
 * ADR-009 COMPLIANCE:
 *   - The layout composes Sidebar + Header + Outlet.
 *   - It is purely structural — no business logic.
 *   - The sidebar is fixed-width (15rem / 240px).
 *   - The main content area fills the remaining viewport.
 */

import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from '../components/layout/Sidebar'
import Header from '../components/layout/Header'

/**
 * Maps URL paths to human-readable page titles.
 *
 * TYPESCRIPT CONCEPT: "Record<K, V>"
 * ──────────────────────────────────────────────────────────────────
 * Record<string, string> is a TypeScript utility type meaning
 * "an object where both keys and values are strings".  It's like
 * Dict[str, str] in Python's typing module.
 */
const pageTitles: Record<string, string> = {
  '/':          'Dashboard',
  '/agents':    'Agents',
  '/tools':     'Tools',
  '/detection': 'Detection Rules',
  '/audit':     'Audit Timeline',
}

export default function AppLayout() {
  const location = useLocation()
  const title = pageTitles[location.pathname] ?? 'Enterprise Security Console'

  return (
    <div className="flex min-h-screen">
      <Sidebar />

      {/* Main area is offset by the sidebar width (w-60 = 15rem) */}
      <div className="flex flex-col flex-1 ml-60">
        <Header title={title} />

        {/*
          <Outlet /> is where React Router injects the child route's
          page component.  When the URL is "/agents", the AgentsPage
          component renders here.
        */}
        <main className="flex-1 p-6 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
