/**
 * FindingService — Behavioral threat detection findings client.
 *
 * REACT CONCEPT: "Service Abstraction Layer"
 * ──────────────────────────────────────────────────────────────────
 * Consumes the GET /api/v1/findings Management API endpoint.
 *
 * DTO Mapping & Normalization:
 *   - Verifies response data is a valid array. If not, it safely returns
 *     an empty list `[]` to prevent client crashes.
 *   - Normalizes severity, category, and status enums to literal unions,
 *     reverting unrecognized values to safe fallbacks.
 *   - Sorts findings chronologically (Newest first) by default.
 */

import apiClient from '../api/apiClient'
import { ApiRoutes } from '../api/routes'
import type { Finding, FindingSeverity, FindingCategory, FindingStatus } from '../types/finding'

/**
 * Backend API response structure for GET /api/v1/findings.
 */
interface FindingResponseDto {
  id: string
  session_id: string
  agent_id: string
  rule_id: string
  rule_name: string
  severity: string
  category: string
  status: string
  description: string
  detected_at: string
  mitre_techniques?: string[]
}

export interface FindingFilters {
  session_id?: string
  agent_id?: string
  severity?: FindingSeverity | ''
  category?: FindingCategory | ''
  status?: FindingStatus | ''
  rule_id?: string
}

const VALID_SEVERITIES: Set<FindingSeverity> = new Set(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'])

const VALID_CATEGORIES: Set<FindingCategory> = new Set([
  'PROMPT_INJECTION',
  'DATA_EXFILTRATION',
  'PRIVILEGE_ESCALATION',
  'UNAUTHORIZED_TOOL',
  'SENSITIVE_FILE_ACCESS',
  'BROWSER_ABUSE',
  'SECRET_LEAKAGE',
  'MULTI_STEP_ATTACK',
  'UNKNOWN',
])

const VALID_STATUSES: Set<FindingStatus> = new Set(['OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'FALSE_POSITIVE'])

/**
 * Fetch all behavioral detection findings from the Management API.
 */
export const getFindings = async (filters?: FindingFilters): Promise<Finding[]> => {
  const params: Record<string, string> = {}
  if (filters?.session_id) params.session_id = filters.session_id
  if (filters?.agent_id) params.agent_id = filters.agent_id
  if (filters?.severity) params.severity = filters.severity
  if (filters?.category) params.category = filters.category
  if (filters?.status) params.status = filters.status
  if (filters?.rule_id) params.rule_id = filters.rule_id

  const response = await apiClient.get<FindingResponseDto[]>(ApiRoutes.management.findings, { params })

  // Safe DTO validation check
  if (!Array.isArray(response.data)) {
    console.error('Unexpected findings API response format:', response.data)
    return []
  }

  const mapped = response.data.map((dto): Finding => {
    const sevUpper = dto.severity?.toUpperCase() as FindingSeverity
    const severityVal: FindingSeverity = VALID_SEVERITIES.has(sevUpper) ? sevUpper : 'INFO'

    const catUpper = dto.category?.toUpperCase() as FindingCategory
    const categoryVal: FindingCategory = VALID_CATEGORIES.has(catUpper) ? catUpper : 'UNKNOWN'

    const statUpper = dto.status?.toUpperCase() as FindingStatus
    const statusVal: FindingStatus = VALID_STATUSES.has(statUpper) ? statUpper : 'OPEN'

    return {
      id: dto.id,
      session_id: dto.session_id,
      agent_id: dto.agent_id,
      rule_id: dto.rule_id,
      rule_name: dto.rule_name,
      severity: severityVal,
      category: categoryVal,
      status: statusVal,
      description: dto.description,
      detected_at: dto.detected_at,
      mitre_techniques: Array.isArray(dto.mitre_techniques) ? dto.mitre_techniques : [],
    }
  })

  // Immutability: spread mapped array before sorting chronologically (newest first)
  return [...mapped].sort((a, b) => new Date(b.detected_at).getTime() - new Date(a.detected_at).getTime())
}
