/**
 * queryKeys.ts — Centralized TanStack Query key registry.
 *
 * All query keys used across the application are defined here.
 * This eliminates scattered inline key literals that are error-prone
 * and impossible to trace during cache invalidation.
 *
 * Usage:
 *   import { queryKeys } from '../api/queryKeys'
 *   useQuery({ queryKey: queryKeys.agents.all, queryFn: getAgents })
 *
 * Key Structure Convention:
 *   - Root key  = domain name (e.g. 'agents', 'tools')
 *   - Scope key = query variant (e.g. 'all', 'byId', 'bySession')
 *   - Detail keys include identifier parameters
 *
 * Cache Invalidation:
 *   To invalidate an entire domain after a mutation:
 *     queryClient.invalidateQueries({ queryKey: queryKeys.agents.all })
 *
 *   To invalidate a specific resource:
 *     queryClient.invalidateQueries({ queryKey: queryKeys.sessions.byId(id) })
 *
 * Roadmap — Query keys will be extended as vertical slices ship:
 *   PR #68  — queryKeys.auditEvents (live behavioral telemetry feed)
 *   PR #69  — queryKeys.findings    (findings console)
 *   PR #70  — queryKeys.risk        (risk state by agent/session)
 *   PR #71  — queryKeys.approvals   (pending approval queue)
 *   PR #72  — queryKeys.sessionEvents (timeline replay)
 */

export const queryKeys = {
  /** Registered agent inventory (GET /api/v1/agents) */
  agents: {
    all: ['agents'] as const,
    byId: (agentId: string) => ['agents', agentId] as const,
  },

  /** Registered tool inventory (GET /api/v1/tools) */
  tools: {
    all: ['tools'] as const,
    byId: (toolId: string) => ['tools', toolId] as const,
  },

  /** Active execution sessions (GET /api/v1/sessions) */
  sessions: {
    all: ['sessions'] as const,
    byId: (sessionId: string) => ['sessions', sessionId] as const,
    /** Phase 3 — Session event timeline (GET /api/v1/sessions/:id/events) */
    events: (sessionId: string) => ['sessions', sessionId, 'events'] as const,
  },

  /**
   * Behavioral audit event trail (GET /api/v1/audit/events).
   * Phase 2 PR #68: Updated to consume live BehavioralEvent stream.
   */
  auditEvents: {
    all: ['auditEvents'] as const,
  },

  /** Detection rule inventory (GET /api/v1/detection/rules) */
  detectionRules: {
    all: ['detectionRules'] as const,
    byId: (ruleId: string) => ['detectionRules', ruleId] as const,
  },

  /** Attack simulation scenarios (GET /api/v1/scenarios) */
  scenarios: {
    all: ['scenarios'] as const,
    byId: (scenarioId: string) => ['scenarios', scenarioId] as const,
  },

  /**
   * Behavioral detection findings (GET /api/v1/findings).
   * Phase 2 PR #69 — Findings & Alerts Console.
   * Feature gate: FINDINGS_ENABLED
   */
  findings: {
    all: ['findings'] as const,
    byId: (findingId: string) => ['findings', findingId] as const,
    bySession: (sessionId: string) => ['findings', 'session', sessionId] as const,
    byAgent: (agentId: string) => ['findings', 'agent', agentId] as const,
  },

  /**
   * Dynamic risk state (GET /api/v1/risk/...).
   * Phase 2 PR #70 vertical slice — Risk Engine.
   * Feature gate: RISK_ENGINE_ENABLED
   */
  risk: {
    bySession: (sessionId: string) => ['risk', 'session', sessionId] as const,
    byAgent: (agentId: string) => ['risk', 'agent', agentId] as const,
  },

  /**
   * Pending approval tickets (GET /api/v1/approvals/pending).
   * Phase 2 PR #71 — Approval Queue.
   * Feature gate: ENFORCEMENT_ENGINE_ENABLED
   */
  approvals: {
    pending: ['approvals', 'pending'] as const,
    byId: (approvalId: string) => ['approvals', approvalId] as const,
  },

  /**
   * Command Center dashboard summary (GET /api/v1/dashboard/summary).
   * Phase 2+ — Aggregated live metrics endpoint.
   * Currently computed client-side from domain hooks.
   */
  dashboard: {
    summary: ['dashboard', 'summary'] as const,
  },
} as const
