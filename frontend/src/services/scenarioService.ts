/**
 * ScenarioService — Scenario registry visibility operations.
 *
 * REACT CONCEPT: "Service Abstraction Layer"
 * ──────────────────────────────────────────────────────────────────
 * Consumes the GET /api/v1/scenarios Management API endpoint.
 *
 * DTO Mapping & Normalization:
 *   - Verifies response data is a valid array.
 *   - Maps snake_case API properties to camelCase UI models.
 *   - Sorts scenarios immutably by scenario_id.
 */

import apiClient from '../api/apiClient'
import type { Scenario, ScenarioCategory, ScenarioSeverity } from '../types/scenario'

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
  tags: string[]
  enabled: boolean
}

/**
 * Fetch all registered scenarios from the Management API.
 */
export const getScenarios = async (): Promise<Scenario[]> => {
  const response = await apiClient.get<ScenarioResponse[]>('/scenarios')

  // Safe DTO validation check
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
    expectedTools: dto.expected_tools,
    expectedDetectionRules: dto.expected_detection_rules,
    expectedResponse: dto.expected_response,
    tags: dto.tags,
    enabled: dto.enabled,
  }))

  // Immutable sorting ascending by scenario ID (e.g. attack-001, attack-002)
  return [...mapped].sort((a, b) => a.id.localeCompare(b.id))
}
