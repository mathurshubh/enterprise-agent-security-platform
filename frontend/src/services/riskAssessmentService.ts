/**
 * RiskAssessmentService — Dynamic Risk Engine client.
 *
 * REACT CONCEPT: "Service Abstraction Layer"
 * ──────────────────────────────────────────────────────────────────
 * Consumes the GET /api/v1/risk-assessments Management API endpoint.
 *
 * DTO Mapping & Normalization:
 *   - Verifies response data is a valid array. If not, it safely returns
 *     an empty list `[]` to prevent client crashes.
 *   - Normalizes risk level enums to literal unions, reverting unrecognized
 *     values to a safe fallback 'LOW'.
 */

import apiClient from '../api/apiClient'
import { ApiRoutes } from '../api/routes'
import type { RiskAssessment, RiskLevel } from '../types/riskAssessment'

interface RiskAssessmentDto {
  session_id: string
  agent_id: string
  risk_score: number
  risk_level: string
  finding_count: number
  assessed_at: string
}

export interface RiskAssessmentFilters {
  session_id?: string
  agent_id?: string
  risk_level?: RiskLevel | ''
}

const VALID_RISK_LEVELS: Set<RiskLevel> = new Set(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'])

/**
 * Fetch all process-local risk assessments from the Management API.
 */
export const getRiskAssessments = async (filters?: RiskAssessmentFilters): Promise<RiskAssessment[]> => {
  const params: Record<string, string> = {}
  if (filters?.session_id) params.session_id = filters.session_id
  if (filters?.agent_id) params.agent_id = filters.agent_id
  if (filters?.risk_level) params.risk_level = filters.risk_level

  const response = await apiClient.get<RiskAssessmentDto[]>(ApiRoutes.management.riskAssessments, { params })

  // Safe DTO validation check
  if (!Array.isArray(response.data)) {
    console.error('Unexpected risk assessments API response format:', response.data)
    return []
  }

  return response.data.map((dto): RiskAssessment => {
    const levelUpper = dto.risk_level?.toUpperCase() as RiskLevel
    const levelVal: RiskLevel = VALID_RISK_LEVELS.has(levelUpper) ? levelUpper : 'LOW'

    return {
      session_id: dto.session_id,
      agent_id: dto.agent_id,
      risk_score: dto.risk_score,
      risk_level: levelVal,
      finding_count: dto.finding_count,
      assessed_at: dto.assessed_at,
    }
  })
}

/**
 * Fetch the latest risk assessment for a specific session ID.
 */
export const getRiskAssessmentBySession = async (sessionId: string): Promise<RiskAssessment | null> => {
  const response = await apiClient.get<RiskAssessmentDto>(ApiRoutes.management.riskAssessment(sessionId))
  const dto = response.data
  if (!dto || !dto.session_id) return null

  const levelUpper = dto.risk_level?.toUpperCase() as RiskLevel
  const levelVal: RiskLevel = VALID_RISK_LEVELS.has(levelUpper) ? levelUpper : 'LOW'

  return {
    session_id: dto.session_id,
    agent_id: dto.agent_id,
    risk_score: dto.risk_score,
    risk_level: levelVal,
    finding_count: dto.finding_count,
    assessed_at: dto.assessed_at,
  }
}
