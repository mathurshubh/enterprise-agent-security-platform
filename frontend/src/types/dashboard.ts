/**
 * dashboard.ts — Command Center / Dashboard domain types.
 *
 * Type contracts for the Command Center landing surface (/).
 * These aggregate metrics are derived from multiple backend domain APIs.
 *
 * Phase 1 (current):
 *   Dashboard metrics are computed client-side by aggregating data from
 *   individual domain API responses (agents, tools, sessions, audit events).
 *   No dedicated dashboard API exists yet.
 *
 * Phase 2+ (future):
 *   A dedicated GET /api/v1/dashboard/summary endpoint will return
 *   pre-aggregated metrics from the backend, including:
 *   - Live behavioral findings count
 *   - Pending approvals count
 *   - Blocked executions count
 *   - Active session risk distribution
 *   - Runtime latency P95
 *
 * These types establish the target contract for that future API.
 */

/** A single metric card value displayed in the Command Center. */
export interface DashboardMetric {
  /** Display label for the metric. */
  label: string
  /** Current numeric value. */
  value: number
  /** Optional trend indicator vs. previous period. */
  trend?: 'up' | 'down' | 'stable'
  /** Optional change percentage vs. previous period. */
  change_pct?: number
}

/**
 * Full dashboard summary payload.
 *
 * Phase 1: Constructed client-side from domain hook data.
 * Phase 2+: Returned directly from GET /api/v1/dashboard/summary.
 */
export interface DashboardSummary {
  /** Total registered agent count. */
  registered_agents: number
  /** Agents in ACTIVE status. */
  active_agents: number
  /** Agents in HIGH or CRITICAL risk tier. */
  high_risk_agents: number
  /** Total registered tool count. */
  registered_tools: number
  /** Currently active (in-progress) session count. */
  active_sessions: number
  /** Total audit events recorded. */
  audit_event_count: number
  /** Open findings count (Phase 2+). */
  open_findings: number
  /** Pending approval tickets count (Phase 2+). */
  pending_approvals: number
  /** Executions blocked by the Enforcement Engine (Phase 2+). */
  blocked_executions: number
}
