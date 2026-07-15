/**
 * SessionService — platform session registry connector.
 *
 * REACT CONCEPT: "Service Abstraction Layer"
 * ──────────────────────────────────────────────────────────────────
 * Consumes the GET /api/v1/sessions Management API endpoint.
 *
 * DTO Mapping & Normalization:
 *   - Verifies response data is a valid array. If not, it safely returns
 *     an empty list `[]` to prevent client crashes.
 *   - Normalizes keys to matching camels: session_id to id, agent_id to agentId.
 *   - Clones mapping arrays before sorting.
 */

import apiClient from '../api/apiClient'
import type { Session } from '../types/session'

interface SessionResponse {
  session_id: string
  agent_id: string
  started_at: string // ISO-8601 string
}

/**
 * Fetch all platform active sessions from the Management API.
 */
export const getSessions = async (): Promise<Session[]> => {
  const response = await apiClient.get<SessionResponse[]>('/sessions')
  
  // Safe DTO validation check
  if (!Array.isArray(response.data)) {
    console.error('Unexpected sessions API response format:', response.data)
    return []
  }

  const mapped = response.data.map((dto) => ({
    id: dto.session_id,
    agentId: dto.agent_id,
    startedAt: dto.started_at,
  }))

  // Immutable sorting: Newest to Oldest (descending by startedAt)
  return [...mapped].sort((a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime())
}
