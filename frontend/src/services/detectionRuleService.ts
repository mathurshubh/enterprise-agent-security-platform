/**
 * DetectionRuleService — active detection rule visibility.
 *
 * REACT CONCEPT: "Service Abstraction Layer"
 * ──────────────────────────────────────────────────────────────────
 * Consumes the GET /api/v1/detection/rules Management API endpoint.
 *
 * DTO Mapping & Normalization:
 *   - Verifies response data is a valid array. If not, it safely returns
 *     an empty list `[]` to prevent client crashes.
 *   - Normalizes category enums to literal unions, reverting unrecognized
 *     values to a safe fallback 'UNKNOWN'.
 *   - Utilizes a dedicated sub-mapper `mapSecurityControl` for controls.
 */

import apiClient from '../api/apiClient'
import type { DetectionRule, DetectionCategory, SecurityControlReference } from '../types/detectionRule'

interface SecurityControlResponse {
  framework: string
  control_id: string
  title: string
  version: string
}

interface DetectionRuleResponse {
  name: string
  category: string
  description: string
  controls: SecurityControlResponse[]
}

const VALID_CATEGORIES: Set<DetectionCategory> = new Set([
  'PROMPT_SECURITY',
  'DATA_SECURITY',
  'TOOL_SECURITY',
  'IDENTITY_SECURITY',
  'BEHAVIORAL_SECURITY',
  'POLICY_SECURITY',
])

/**
 * Dedicated sub-mapper function for mapping nested security framework controls.
 */
const mapSecurityControl = (dto: SecurityControlResponse): SecurityControlReference => ({
  framework: dto.framework,
  controlId: dto.control_id,
  title: dto.title,
  version: dto.version,
})

/**
 * Fetch all active detection rules from the Management API.
 */
export const getDetectionRules = async (): Promise<DetectionRule[]> => {
  const response = await apiClient.get<DetectionRuleResponse[]>('/detection/rules')
  
  // Safe DTO validation check
  if (!Array.isArray(response.data)) {
    console.error('Unexpected detection rules API response format:', response.data)
    return []
  }

  return response.data.map((dto) => {
    // Normalization & Default fallbacks for category
    const categoryUpper = dto.category.toUpperCase() as DetectionCategory
    const categoryVal = VALID_CATEGORIES.has(categoryUpper) ? categoryUpper : 'UNKNOWN'

    return {
      name: dto.name,
      category: categoryVal,
      description: dto.description,
      controls: Array.isArray(dto.controls) ? dto.controls.map(mapSecurityControl) : [],
      status: null,
    }
  })
}
