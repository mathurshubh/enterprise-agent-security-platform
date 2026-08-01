/**
 * AppLayout — Application shell wrapping every console page.
 *
 * Composes Sidebar + Header + main content Outlet.
 * The sidebar is fixed at w-60 (240px); the main area fills the remainder.
 *
 * Error Isolation (PR #70):
 *   The <Outlet /> is wrapped with <ErrorBoundary /> so that a rendering
 *   crash on any individual page does not propagate to the application shell.
 *   The sidebar and header remain functional, allowing the analyst to navigate
 *   away from the crashed page.
 *
 * Page title resolution delegates to resolvePageTitle() from the shared
 * navigation config (src/config/navigation.ts), ensuring the Header title
 * always matches the sidebar label — eliminating drift between the two.
 *
 * Breadcrumbs: Intentionally deferred. Breadcrumbs are meaningful only in
 * the multi-panel Session Investigation Workspace (/sessions/:id) introduced
 * in Phase 3 (v0.14.0). Top-level routes have no nesting depth that
 * warrants breadcrumbs. This deferral is documented in the Phase 1 PR.
 *
 * ADR-009 / ADR-022 compliance:
 *   - Purely structural — no business logic, no API calls.
 *   - All 9 canonical routes are covered via resolvePageTitle.
 */

import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from '../components/layout/Sidebar'
import Header from '../components/layout/Header'
import ErrorBoundary from '../components/common/ErrorBoundary'
import { resolvePageTitle } from '../config/navigation'

export default function AppLayout() {
  const location = useLocation()
  const title = resolvePageTitle(location.pathname)

  return (
    <div className="flex min-h-screen">
      <Sidebar />

      {/* Main area offset by sidebar width (w-60 = 15rem) */}
      <div className="flex flex-col flex-1 ml-60 min-h-screen">
        <Header title={title} />

        {/*
          ErrorBoundary wraps the Outlet so that a render crash on any page
          is isolated to the page content area. The shell (sidebar + header)
          remains fully functional, allowing the analyst to navigate away.
        */}
        <main className="flex-1 p-6 overflow-y-auto">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  )
}
