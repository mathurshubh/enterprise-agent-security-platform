/**
 * ToolService — Tool registry observability operations.
 *
 * REACT CONCEPT: "Service Abstraction Layer"
 * ──────────────────────────────────────────────────────────────────
 * Consumes the GET /api/v1/tools Management API endpoint.
 *
 * DTO Mapping & Normalization:
 *   Maps unexposed domain fields to `null` values.  Keeps presentation
 *   logic (such as rendering "—" stubs) isolated inside the UI components.
 */

import apiClient from '../api/apiClient'
import type { Tool } from '../types/tool'

/**
 * Raw data structure returned by the backend GET /api/v1/tools endpoint.
 */
interface ToolResponse {
  tool_id: string
  name: string
  description: string
  version: string
}

/**
 * Fetch all registered tools from the Management API.
 */
export const getTools = async (): Promise<Tool[]> => {
  const response = await apiClient.get<ToolResponse[]>('/tools')
  
  // Safe DTO validation check
  if (!Array.isArray(response.data)) {
    console.error('Invalid response format returned by tools API, expected array:', response.data)
    return []
  }

  return response.data.map((dto) => ({
    id: dto.tool_id,
    name: dto.name,
    description: dto.description,
    version: dto.version,
    riskLevel: null,
    status: null,
    category: null,
    owner: null,
    timeoutSeconds: null,
    approvalRequired: null,
  }))
}
