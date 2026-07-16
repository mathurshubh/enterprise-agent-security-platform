/**
 * DashboardPage — Central platform visibility dashboard.
 *
 * Composes all domain hooks to derive live inventory counts and
 * security activity metrics from the existing Management API.
 *
 * Architecture:
 *   DashboardPage → useAgents / useTools / useDetectionRules /
 *                   useAuditEvents / useSessions
 *                 → domain services
 *                 → Management API
 */

import { useMemo } from 'react'
import { useAgents } from '../../hooks/useAgents'
import { useTools } from '../../hooks/useTools'
import { useDetectionRules } from '../../hooks/useDetectionRules'
import { useAuditEvents } from '../../hooks/useAuditEvents'
import { useSessions } from '../../hooks/useSessions'

export default function DashboardPage() {
  // ── Domain Hooks ──────────────────────────────────────────────────
  const { agents,  loading: loadingAgents,  error: errorAgents }  = useAgents()
  const { tools,   loading: loadingTools,   error: errorTools }   = useTools()
  const { rules,   loading: loadingRules,   error: errorRules }   = useDetectionRules()
  const { events,  loading: loadingEvents,  error: errorEvents }  = useAuditEvents()
  const { sessions, loading: loadingSessions, error: errorSessions } = useSessions()

  // ── Merged States ─────────────────────────────────────────────────
  const loading = loadingAgents || loadingTools || loadingRules || loadingEvents || loadingSessions
  const error   = errorAgents || errorTools || errorRules || errorEvents || errorSessions

  // ── Inventory Metrics ─────────────────────────────────────────────
  const inventoryMetrics = [
    { label: 'Registered Agents', value: agents.length },
    { label: 'Registered Tools',  value: tools.length },
    { label: 'Detection Rules',   value: rules.length },
    { label: 'Sessions',          value: sessions.length },
    { label: 'Audit Events',      value: events.length },
  ]

  // ── Platform Activity Metrics ─────────────────────────────────────
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
    { label: 'Healthy Agents',     value: healthyAgents },
    { label: 'High Risk Agents',   value: highRiskAgents },
    { label: 'Allowed Decisions',  value: allowedDecisions },
    { label: 'Denied Decisions',   value: deniedDecisions },
    { label: 'Unique Tools Used',  value: uniqueToolsUsed },
  ]

  return (
    <div className="space-y-6">

      {/* ── Page Header ────────────────────────────────────────── */}
      <div>
        <h2 className="text-xl font-bold text-text-primary">
          Security Overview
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          High-level security metrics for the Enterprise Agent Security Platform.
        </p>
      </div>

      {/* ── Error Indicator ────────────────────────────────────── */}
      {error && (
        <div className="bg-status-error/10 border border-status-error/30 rounded-xl p-4 flex flex-col gap-1.5">
          <div className="text-xs font-semibold text-status-error uppercase tracking-wider">
            Connection Error
          </div>
          <p className="text-xs text-text-secondary leading-relaxed">
            {error}
          </p>
          <div className="text-[10px] text-text-muted mt-1">
            Ensure the Enterprise Agent Security Platform backend service is running and accessible at the management port.
          </div>
        </div>
      )}

      {/* ── Platform Inventory ─────────────────────────────────── */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-text-primary">
          Platform Inventory
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {inventoryMetrics.map((card) => (
            <div
              key={card.label}
              className="bg-bg-surface border border-border-secondary rounded-xl p-5 flex flex-col justify-between min-h-[110px]"
            >
              <div className="text-xs font-medium text-text-muted uppercase tracking-wide">
                {card.label}
              </div>
              {loading ? (
                <div className="mt-2 h-8 w-24 bg-border-primary/40 rounded animate-pulse" />
              ) : (
                <div className="mt-2 text-2xl font-bold text-text-primary">
                  {card.value}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── Platform Activity ──────────────────────────────────── */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-text-primary">
          Platform Activity
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {activityMetrics.map((card) => (
            <div
              key={card.label}
              className="bg-bg-surface border border-border-secondary rounded-xl p-5 flex flex-col justify-between min-h-[110px]"
            >
              <div className="text-xs font-medium text-text-muted uppercase tracking-wide">
                {card.label}
              </div>
              {loading ? (
                <div className="mt-2 h-8 w-24 bg-border-primary/40 rounded animate-pulse" />
              ) : (
                <div className="mt-2 text-2xl font-bold text-text-primary">
                  {card.value}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}
