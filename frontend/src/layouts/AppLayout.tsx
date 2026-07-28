/**
 * AppLayout — Application shell wrapping every console page.
 *
 * Composes Sidebar + Header + main content Outlet.
 * The sidebar is fixed at w-60 (240px); the main area fills the remainder.
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

        {/* Page content — Outlet injects the matched child route component */}
        <main className="flex-1 p-6 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
