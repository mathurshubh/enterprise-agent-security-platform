/**
 * DashboardPage — Command Center landing surface.
 *
 * Operational Mode: MONITOR
 *
 * Phase 1 implementation per ADR-022 / 11-implementation-roadmap.md:
 *   - Zone 2 (Operational Awareness): Inventory and activity metrics sourced
 *     from existing Management API endpoints.
 *   - Zone 1 (Action Required Queue): Displayed as a degraded-mode banner
 *     until Phase 2 backend Behavioral Intelligence APIs are available.
 *
 * Refactored to use shared <MetricCard>, <PageHeader>, and <ErrorState>
 * components extracted as part of the application shell PR.
 *
 * ADR-022 / 08-page-specifications.md: Page 1 — Command Center.
 */

import { useMemo } from 'react'
import { useAgents } from '../../hooks/useAgents'
import { useTools } from '../../hooks/useTools'
import { useDetectionRules } from '../../hooks/useDetectionRules'
import { useAuditEvents } from '../../hooks/useAuditEvents'
import { useSessions } from '../../hooks/useSessions'
import PageHeader from '../../components/ui/PageHeader'
import MetricCard from '../../components/common/MetricCard'
import ErrorState from '../../components/common/ErrorState'

export default function DashboardPage() {
  // ── Domain Hooks ──────────────────────────────────────────────────
  const { agents,   loading: loadingAgents,   error: errorAgents }   = useAgents()
  const { tools,    loading: loadingTools,    error: errorTools }    = useTools()
  const { rules,    loading: loadingRules,    error: errorRules }    = useDetectionRules()
  const { events,   loading: loadingEvents,   error: errorEvents }   = useAuditEvents()
  const { sessions, loading: loadingSessions, error: errorSessions } = useSessions()

  // ── Merged States ──────────────────────────────────────────────────
  const loading = loadingAgents || loadingTools || loadingRules || loadingEvents || loadingSessions
  const error   = errorAgents || errorTools || errorRules || errorEvents || errorSessions

  // ── Inventory Metrics (Zone 2) ─────────────────────────────────────
  const inventoryMetrics = [
    { label: 'Registered Agents', value: agents.length },
    { label: 'Registered Tools',  value: tools.length },
    { label: 'Detection Rules',   value: rules.length },
    { label: 'Sessions',          value: sessions.length },
    { label: 'Audit Events',      value: events.length },
  ]

  // ── Activity Metrics (Zone 2) ──────────────────────────────────────
  const healthyAgents = useMemo(
    () => agents.filter((a) => a.status === 'ACTIVE').length,
    [agents]
  )
  const highRiskAgents = useMemo(
    () => agents.filter((a) => a.riskLevel === 'HIGH' || a.riskLevel === 'CRITICAL').length,
    [agents]
  )
  const allowedDecisions = useMemo(
    () => events.filter((e) => e.decision === 'ALLOW').length,
    [events]
  )
  const deniedDecisions = useMemo(
    () => events.filter((e) => e.decision === 'DENY').length,
    [events]
  )
  const uniqueToolsUsed = useMemo(
    () => new Set(events.map((e) => e.toolId)).size,
    [events]
  )

  const activityMetrics = [
    { label: 'Healthy Agents',    value: healthyAgents },
    { label: 'High Risk Agents',  value: highRiskAgents },
    { label: 'Allowed Decisions', value: allowedDecisions },
    { label: 'Denied Decisions',  value: deniedDecisions },
    { label: 'Unique Tools Used', value: uniqueToolsUsed },
  ]

  return (
    <div className="space-y-6">

      <PageHeader
        title="Command Center"
        description="Operational platform overview. Zone 1 (Action Required Queue) activates in Phase 2 when Behavioral Intelligence APIs are available."
      />

      {/* ── Zone 1: Action Required Queue (Phase 2 degraded-mode banner) ── */}
      <div className="bg-status-warning/10 border border-status-warning/30 rounded-xl p-4">
        <div className="text-xs font-semibold text-status-warning uppercase tracking-wider">
          Action Required Queue — Phase 2
        </div>
        <p className="text-xs text-text-secondary mt-1 leading-relaxed">
          The Action Required Work Queue will surface held sessions and high-severity findings
          in this zone when the Behavioral Intelligence backend APIs are connected in v0.13.0.
        </p>
      </div>

      {/* ── Error State ────────────────────────────────────────────────── */}
      {error && <ErrorState message={error} />}

      {/* ── Zone 2: Platform Inventory ────────────────────────────────── */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-text-primary">Platform Inventory</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {inventoryMetrics.map((card) => (
            <MetricCard
              key={card.label}
              label={card.label}
              value={card.value}
              loading={loading}
            />
          ))}
        </div>
      </div>

      {/* ── Zone 2: Platform Activity ──────────────────────────────────── */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-text-primary">Platform Activity</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {activityMetrics.map((card) => (
            <MetricCard
              key={card.label}
              label={card.label}
              value={card.value}
              loading={loading}
            />
          ))}
        </div>
      </div>

    </div>
  )
}
