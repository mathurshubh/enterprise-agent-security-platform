/**
 * AgentService — Agent governance visibility operations.
 *
 * REACT CONCEPT: "Service Abstraction Layer"
 * ──────────────────────────────────────────────────────────────────
 * Isolates endpoint details and maps API responses to strongly-typed
 * UI schemas.
 *
 * DTO Validation & Normalization:
 *   - Verifies response data is a valid array. If not (e.g. backend error
 *     or malformed payload), it safely returns an empty array `[]`
 *     to prevent runtime crashes.
 *   - Normalizes status and risk_tier values to safe literal union defaults.
 */

import apiClient from '../api/apiClient'
import type { Agent, AgentStatus, RiskTier } from '../types/agent'

/**
 * Raw data structure returned by the backend GET /api/v1/agents endpoint.
 */
interface AgentResponse {
  agent_id: string
  name: string
  owner: string
  risk_tier: string
  status: string
  approved_tools: string[]
}

const VALID_STATUSES: Set<AgentStatus> = new Set(['REGISTERED', 'ACTIVE', 'SUSPENDED', 'DISABLED'])
const VALID_RISKS: Set<RiskTier> = new Set(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'])

/**
 * Fetch all registered agents from the Management API.
 */
export const getAgents = async (): Promise<Agent[]> => {
  const response = await apiClient.get<AgentResponse[]>('/agents')
  
  // Safe validation check: ensure response data is a valid array
  if (!Array.isArray(response.data)) {
    console.error('Invalid response format returned by agents API, expected array:', response.data)
    return []
  }

  return response.data.map((dto) => {
    // Normalization & Default fallbacks for status
    const statusUpper = dto.status.toUpperCase() as AgentStatus
    const statusVal = VALID_STATUSES.has(statusUpper) ? statusUpper : 'REGISTERED'

    // Normalization & Default fallbacks for risk tier
    const riskUpper = dto.risk_tier.toUpperCase() as RiskTier
    const riskVal = VALID_RISKS.has(riskUpper) ? riskUpper : 'LOW'

    return {
      id: dto.agent_id,
      name: dto.name,
      status: statusVal,
      riskLevel: riskVal,
      framework: 'Pending',
      provider: 'Pending',
      owner: dto.owner,
      lastSeen: 'N/A',
      approvedTools: dto.approved_tools,
    }
  })
}
