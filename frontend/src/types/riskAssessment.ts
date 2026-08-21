/**
 * riskAssessment.ts — Dynamic Risk Assessment domain types.
 *
 * Type contracts for process-local risk assessments produced by the
 * Dynamic Risk Engine (ADR-018).
 *
 * Backend sources:
 *   GET /api/v1/risk-assessments
 *   GET /api/v1/risk-assessments/:session_id
 *
 * Feature gate: RISK_ENGINE_ENABLED (src/config/featureFlags.ts)
 */

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

export interface RiskAssessment {
  session_id: string
  agent_id: string
  risk_score: number
  risk_level: RiskLevel
  finding_count: number
  assessed_at: string
}
