/**
 * App — Root component and route configuration.
 *
 * REACT CONCEPT: "Component Tree"
 * ──────────────────────────────────────────────────────────────────
 * Every React application is a tree of components.  The root
 * component (App) sits at the top and defines the overall
 * structure.  Here, App configures the router which then decides
 * which page component to render based on the current URL.
 *
 * Think of it like a FastAPI application where `app = FastAPI()`
 * is the root and `app.include_router(...)` registers routes.
 *
 * REACT ROUTER CONCEPT: "BrowserRouter" and "Routes"
 * ──────────────────────────────────────────────────────────────────
 * BrowserRouter enables client-side URL handling using the browser's
 * History API (no full page reloads).
 *
 * Routes / Route define the URL-to-component mapping:
 *   path="/"         → DashboardPage
 *   path="/agents"   → AgentsPage
 *   etc.
 *
 * The layout route (path="/") wraps all children in AppLayout,
 * which provides the sidebar + header.  This is equivalent to
 * template inheritance in server-side frameworks.
 *
 * ADR-009 COMPLIANCE:
 *   - Routes map 1:1 to ADR-009 Initial Pages.
 *   - No runtime execution routes exist.
 *   - No authentication guards are implemented yet.
 */

import { BrowserRouter, Routes, Route } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
import DashboardPage from './pages/Dashboard/DashboardPage'
import AgentsPage from './pages/Agents/AgentsPage'
import ToolsPage from './pages/Tools/ToolsPage'
import DetectionRulesPage from './pages/Detection/DetectionRulesPage'
import AuditTimelinePage from './pages/Audit/AuditTimelinePage'
import SessionsPage from './pages/Sessions/SessionsPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/*
          Layout route: AppLayout renders Sidebar + Header and
          contains an <Outlet /> where child routes are injected.
        */}
        <Route element={<AppLayout />}>
          <Route index              element={<DashboardPage />} />
          <Route path="/agents"     element={<AgentsPage />} />
          <Route path="/tools"      element={<ToolsPage />} />
          <Route path="/detection"  element={<DetectionRulesPage />} />
          <Route path="/audit"      element={<AuditTimelinePage />} />
          <Route path="/sessions"   element={<SessionsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
