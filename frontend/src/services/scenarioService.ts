/**
 * ScenarioService — Scenario registry and execution operations.
 *
 * REACT CONCEPT: "Service Abstraction Layer"
 * ──────────────────────────────────────────────────────────────────
 * Consumes the canonical `/api/scenarios` and `/api/scenarios/{id}/execute`
 * endpoints exposed by the backend scenario router.
 *
 * Routing Note:
 *   Endpoints are defined in ApiRoutes.scenarios and resolved against apiClient's
 *   baseURL (/api). The scenario validation pipeline lives under /scenarios/* outside
 *   the /v1 management namespace.
 *
 * DTO Mapping & Normalization:
 *   - Verifies response data is valid.
 *   - Maps snake_case API properties to camelCase UI models.
 *   - Sorts scenarios immutably by scenario_id.
 */

import apiClient from '../api/apiClient'
import { ApiRoutes } from '../api/routes'
import type {
  Scenario,
  ScenarioCategory,
  ScenarioExecutionEvidence,
  ScenarioExecutionResult,
  ScenarioSeverity,
} from '../types/scenario'

interface ScenarioToolInvocationResponse {
  tool_id: string
  resource?: string | null
}

interface ScenarioRequestEvidenceResponse {
  agent_id: string
  execution_mode: string
  user_prompt?: string | null
  intent_source: 'DETERMINISTIC_SEQUENCE' | 'UNTRUSTED_LLM_PARSER'
  tool_sequence?: string[]
  tool_invocation?: ScenarioToolInvocationResponse | null
}

interface ScenarioAuthorizationCheckResponse {
  name: string
  key: string
  status: 'passed' | 'failed' | 'not_evaluated'
  reason: string
  details?: Record<string, string>
}

interface ScenarioAuthorizationEvidenceResponse {
  decision: string
  reason: string
  checks: ScenarioAuthorizationCheckResponse[]
}

interface ScenarioFindingSummaryResponse {
  rule_name: string
  severity: string
  finding_id: string
  description: string
}

interface ScenarioDetectionEvidenceResponse {
  findings: ScenarioFindingSummaryResponse[]
  finding_count: number
}

interface ScenarioRiskEvidenceResponse {
  level: string
  score: number
  finding_count: number
}

interface ScenarioResponseEvidenceResponse {
  action: string
  reason: string
}

interface ScenarioAuditEvidenceResponse {
  event_id: string
}

interface ScenarioFinalDecisionEvidenceResponse {
  decision: string
}

interface ScenarioExecutionEvidenceResponse {
  request: ScenarioRequestEvidenceResponse
  authorization?: ScenarioAuthorizationEvidenceResponse | null
  detection?: ScenarioDetectionEvidenceResponse | null
  risk?: ScenarioRiskEvidenceResponse | null
  response?: ScenarioResponseEvidenceResponse | null
  audit?: ScenarioAuditEvidenceResponse | null
  final_decision?: ScenarioFinalDecisionEvidenceResponse | null
  refusal_reason?: string | null
}

interface ScenarioResponse {
  scenario_id: string
  name: string
  description: string
  category: string
  severity: string
  prompt: string
  expected_tools: string[]
  expected_detection_rules: string[]
  expected_response: string
  expected_risk: string
  expected_findings: string[]
  tool_sequence: string[]
  tags: string[]
  enabled: boolean
  version: string
  schema_version: string
}

interface ScenarioExecutionResponse {
  execution_id: string
  scenario_id: string
  session_id: string
  execution_mode: string
  status: string
  passed: boolean | null
  authorization_decision?: string | null
  final_decision?: string | null
  observed_decision: string | null
  observed_response: string | null
  observed_risk_level: string | null
  observed_findings: string[]
  mismatches: string[]
  error_message: string | null
  started_at: string
  finished_at: string | null
  evidence?: ScenarioExecutionEvidenceResponse | null
}

/**
 * Fetch all registered scenarios from the Scenario API.
 */
export const getScenarios = async (): Promise<Scenario[]> => {
  const response = await apiClient.get<ScenarioResponse[]>(ApiRoutes.scenarios.list)

  if (!Array.isArray(response.data)) {
    console.error('Invalid response format returned by scenarios API, expected array:', response.data)
    return []
  }

  const mapped = response.data.map((dto) => ({
    id: dto.scenario_id,
    name: dto.name,
    description: dto.description,
    category: dto.category as ScenarioCategory,
    severity: dto.severity as ScenarioSeverity,
    prompt: dto.prompt,
    expectedTools: dto.expected_tools ?? [],
    expectedDetectionRules: dto.expected_detection_rules ?? [],
    expectedResponse: dto.expected_response ?? 'MONITOR',
    expectedRisk: dto.expected_risk ?? 'LOW',
    expectedFindings: dto.expected_findings ?? [],
    toolSequence: dto.tool_sequence ?? [],
    tags: dto.tags ?? [],
    enabled: dto.enabled ?? true,
    version: dto.version ?? '1.0',
    schemaVersion: dto.schema_version ?? '1.0',
  }))

  return [...mapped].sort((a, b) => a.id.localeCompare(b.id))
}

const mapEvidenceResponse = (
  raw?: ScenarioExecutionEvidenceResponse | null
): ScenarioExecutionEvidence | null => {
  if (!raw) return null

  return {
    request: {
      agentId: raw.request.agent_id,
      executionMode: raw.request.execution_mode,
      userPrompt: raw.request.user_prompt ?? null,
      intentSource: raw.request.intent_source,
      toolSequence: raw.request.tool_sequence ?? [],
      toolInvocation: raw.request.tool_invocation
        ? {
            toolId: raw.request.tool_invocation.tool_id,
            resource: raw.request.tool_invocation.resource ?? null,
          }
        : null,
    },
    authorization: raw.authorization
      ? {
          decision: raw.authorization.decision,
          reason: raw.authorization.reason,
          checks: (raw.authorization.checks ?? []).map((c) => ({
            name: c.name,
            key: c.key,
            status: c.status,
            reason: c.reason,
            details: c.details ?? {},
          })),
        }
      : null,
    detection: raw.detection
      ? {
          findingCount: raw.detection.finding_count,
          findings: (raw.detection.findings ?? []).map((f) => ({
            ruleName: f.rule_name,
            severity: f.severity,
            findingId: f.finding_id,
            description: f.description,
          })),
        }
      : null,
    risk: raw.risk
      ? {
          level: raw.risk.level,
          score: raw.risk.score,
          findingCount: raw.risk.finding_count,
        }
      : null,
    response: raw.response
      ? {
          action: raw.response.action,
          reason: raw.response.reason,
        }
      : null,
    audit: raw.audit
      ? {
          eventId: raw.audit.event_id,
        }
      : null,
    finalDecision: raw.final_decision
      ? {
          decision: raw.final_decision.decision,
        }
      : null,
    refusalReason: raw.refusal_reason ?? null,
  }
}

/**
 * Execute a scenario by ID through the Runtime Security Pipeline.
 */
export const executeScenario = async (
  scenarioId: string
): Promise<ScenarioExecutionResult> => {
  const response = await apiClient.post<ScenarioExecutionResponse>(
    ApiRoutes.scenarios.execute(scenarioId)
  )

  const dto = response.data
  return {
    executionId: dto.execution_id,
    scenarioId: dto.scenario_id,
    sessionId: dto.session_id,
    executionMode: dto.execution_mode,
    status: dto.status,
    passed: dto.passed,
    authorizationDecision: dto.authorization_decision ?? null,
    finalDecision: dto.final_decision ?? dto.observed_decision ?? null,
    observedDecision: dto.observed_decision,
    observedResponse: dto.observed_response,
    observedRiskLevel: dto.observed_risk_level,
    observedFindings: dto.observed_findings ?? [],
    mismatches: dto.mismatches ?? [],
    errorMessage: dto.error_message,
    startedAt: dto.started_at,
    finishedAt: dto.finished_at,
    evidence: mapEvidenceResponse(dto.evidence),
  }
}
