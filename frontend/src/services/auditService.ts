/**
 * AuditService — platform execution logging client.
 *
 * REACT CONCEPT: "Service Abstraction Layer & Immutability"
 * ──────────────────────────────────────────────────────────────────
 * Consumes the GET /api/v1/audit/events Management API endpoint.
 *
 * DTO Mapping & Normalization:
 *   - Verifies response data is a valid array. If not, it safely returns
 *     an empty list `[]` to prevent client crashes.
 *   - Normalizes decision enums to literal unions, reverting unrecognized
 *     values to a safe fallback 'UNKNOWN'.
 *   - Sorts events chronologically (Newest first) by default using spread
 *     copier syntax (`[...mapped].sort(...)`) to preserve immutability.
 */

import apiClient from '../api/apiClient'
import type { AuditEvent, AuditDecision } from '../types/auditEvent'

interface AuditEventResponse {
  event_id: string
  agent_id: string
  tool_id: string
  decision: string
  timestamp: string // ISO-8601 string
}

const VALID_DECISIONS: Set<AuditDecision> = new Set(['ALLOW', 'DENY', 'APPROVAL_REQUIRED', 'UNKNOWN'])

/**
 * Fetch all platform audit events from the Management API.
 */
export const getAuditEvents = async (): Promise<AuditEvent[]> => {
  const response = await apiClient.get<AuditEventResponse[]>('/audit/events')
  
  // Safe DTO validation check
  if (!Array.isArray(response.data)) {
    console.error('Unexpected audit events API response format:', response.data)
    return []
  }

  const mapped = response.data.map((dto) => {
    // Normalization & Default fallbacks for decision
    const decisionUpper = dto.decision.toUpperCase() as AuditDecision
    const decisionVal = VALID_DECISIONS.has(decisionUpper) ? decisionUpper : 'UNKNOWN'

    return {
      id: dto.event_id,
      agentId: dto.agent_id,
      toolId: dto.tool_id,
      decision: decisionVal,
      timestamp: dto.timestamp,
    }
  })

  // Immutability: spread mapped array before sorting to avoid side effects
  return [...mapped].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
}
