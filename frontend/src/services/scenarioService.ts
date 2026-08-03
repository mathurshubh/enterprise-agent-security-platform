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
  ScenarioExecutionResult,
  ScenarioSeverity,
} from '../types/scenario'

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
  observed_decision: string | null
  observed_response: string | null
  observed_risk_level: string | null
  observed_findings: string[]
  mismatches: string[]
  error_message: string | null
  started_at: string
  finished_at: string | null
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
    observedDecision: dto.observed_decision,
    observedResponse: dto.observed_response,
    observedRiskLevel: dto.observed_risk_level,
    observedFindings: dto.observed_findings ?? [],
    mismatches: dto.mismatches ?? [],
    errorMessage: dto.error_message,
    startedAt: dto.started_at,
    finishedAt: dto.finished_at,
  }
}
