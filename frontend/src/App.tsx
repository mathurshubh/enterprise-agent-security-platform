/**
 * App — Root component and route configuration.
 *
 * Implements the 9 canonical routes defined in ADR-022 and
 * docs/architecture/enterprise-security-console/04-navigation-architecture.md.
 *
 * Route sections:
 *   MONITOR    — / (Command Center), /approvals (Approval Queue)
 *   INVESTIGATE — /sessions, /findings, /audit
 *   GOVERN     — /agents, /tools, /detection, /scenarios
 *
 * Lazy Loading (PR #70):
 *   All page components are loaded with React.lazy() for route-level
 *   code splitting. Each page becomes a separate JS chunk loaded on demand,
 *   reducing the initial bundle size. The <Suspense> fallback renders a
 *   centered loading indicator while the chunk is fetched.
 *
 *   Only page components are lazy-loaded. Layout components (AppLayout,
 *   Sidebar, Header) are eagerly loaded because they are needed immediately
 *   on every route and represent a small portion of the total bundle.
 *
 * Migration notes (from v0.11.0):
 *   - All existing paths preserved (zero URL breakage).
 *   - /sessions and /scenarios promoted to primary sidebar navigation.
 *   - /approvals and /findings added as new Phase 2-gated placeholder routes.
 *   - Eager imports replaced with React.lazy() (PR #70).
 *
 * ADR-022 compliance:
 *   - Routes map 1:1 to canonical navigation architecture.
 *   - No client-side security logic.
 *   - No authentication guards implemented yet (Phase 3 — ADR-009).
 */

import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
import LoadingState from './components/common/LoadingState'

// ── MONITOR ──────────────────────────────────────────────────────────────────
const DashboardPage     = lazy(() => import('./pages/Dashboard/DashboardPage'))
const ApprovalQueuePage = lazy(() => import('./pages/Approvals/ApprovalQueuePage'))

// ── INVESTIGATE ───────────────────────────────────────────────────────────────
const SessionsPage      = lazy(() => import('./pages/Sessions/SessionsPage'))
const FindingsPage      = lazy(() => import('./pages/Findings/FindingsPage'))
const AuditTimelinePage = lazy(() => import('./pages/Audit/AuditTimelinePage'))

// ── GOVERN ────────────────────────────────────────────────────────────────────
const AgentsPage        = lazy(() => import('./pages/Agents/AgentsPage'))
const ToolsPage         = lazy(() => import('./pages/Tools/ToolsPage'))
const DetectionRulesPage = lazy(() => import('./pages/Detection/DetectionRulesPage'))
const ScenariosPage     = lazy(() => import('./pages/Scenarios/ScenariosPage'))

export default function App() {
  return (
    <BrowserRouter>
      {/*
        Suspense wraps the entire Routes tree so that lazy-loaded page chunks
        display a loading indicator while being fetched. The fallback is
        rendered in the full viewport (before the layout shell is mounted).
        Once the layout itself is loaded, ErrorBoundary in AppLayout provides
        per-page isolation for render errors.
      */}
      <Suspense fallback={<LoadingState label="Loading console..." fullscreen />}>
        <Routes>
          {/*
            Layout route: AppLayout renders Sidebar + Header and
            contains an <Outlet /> where child routes are injected.
          */}
          <Route element={<AppLayout />}>

            {/* MONITOR */}
            <Route index              element={<DashboardPage />} />
            <Route path="/approvals"  element={<ApprovalQueuePage />} />

            {/* INVESTIGATE */}
            <Route path="/sessions"   element={<SessionsPage />} />
            <Route path="/findings"   element={<FindingsPage />} />
            <Route path="/audit"      element={<AuditTimelinePage />} />

            {/* GOVERN */}
            <Route path="/agents"     element={<AgentsPage />} />
            <Route path="/tools"      element={<ToolsPage />} />
            <Route path="/detection"  element={<DetectionRulesPage />} />
            <Route path="/scenarios"  element={<ScenariosPage />} />

          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
