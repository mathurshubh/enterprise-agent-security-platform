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
 * Migration from v0.11.0:
 *   - All existing paths preserved (zero URL breakage).
 *   - /sessions and /scenarios promoted to primary sidebar navigation.
 *   - /approvals and /findings added as new Phase 2-gated placeholder routes.
 *
 * ADR-022 compliance:
 *   - Routes map 1:1 to canonical navigation architecture.
 *   - No client-side security logic.
 *   - No authentication guards implemented yet.
 */

import { BrowserRouter, Routes, Route } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'

// MONITOR
import DashboardPage from './pages/Dashboard/DashboardPage'
import ApprovalQueuePage from './pages/Approvals/ApprovalQueuePage'

// INVESTIGATE
import SessionsPage from './pages/Sessions/SessionsPage'
import FindingsPage from './pages/Findings/FindingsPage'
import AuditTimelinePage from './pages/Audit/AuditTimelinePage'

// GOVERN
import AgentsPage from './pages/Agents/AgentsPage'
import ToolsPage from './pages/Tools/ToolsPage'
import DetectionRulesPage from './pages/Detection/DetectionRulesPage'
import ScenariosPage from './pages/Scenarios/ScenariosPage'

export default function App() {
  return (
    <BrowserRouter>
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
    </BrowserRouter>
  )
}
