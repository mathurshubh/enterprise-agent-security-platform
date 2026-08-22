/**
 * ApiRoutes — Centralized API Endpoint Registry.
 *
 * Architecture Invariants:
 * ──────────────────────────────────────────────────────────────────
 * 1. Root Ownership: The `/api` root prefix is owned strictly by `apiClient.ts`.
 * 2. Route Ownership: `ApiRoutes` owns all domain paths and version namespaces:
 *    - Management API endpoints live under `/v1/*`.
 *    - Scenario validation API endpoints live under `/scenarios/*` (outside `/v1`).
 * 3. Parameterized Routes: All parameterized paths use typed helper functions
 *    with `encodeURIComponent()` safety.
 * 4. Zero String Literals: No service file may contain literal endpoint strings.
 */

export const ApiRoutes = {
  management: {
    agents: '/v1/agents',
    agent: (id: string) => `/v1/agents/${encodeURIComponent(id)}`,

    tools: '/v1/tools',
    tool: (id: string) => `/v1/tools/${encodeURIComponent(id)}`,

    sessions: '/v1/sessions',
    session: (id: string) => `/v1/sessions/${encodeURIComponent(id)}`,

    auditEvents: '/v1/audit/events',

    detectionRules: '/v1/detection/rules',

    findings: '/v1/findings',
    finding: (id: string) => `/v1/findings/${encodeURIComponent(id)}`,

    riskAssessments: '/v1/risk-assessments',
    riskAssessment: (sessionId: string, agentId?: string) =>
      `/v1/risk-assessments/${encodeURIComponent(sessionId)}${agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ''}`,
  },
  scenarios: {
    list: '/scenarios',
    detail: (id: string) => `/scenarios/${encodeURIComponent(id)}`,
    execute: (id: string) => `/scenarios/${encodeURIComponent(id)}/execute`,
  },
} as const
