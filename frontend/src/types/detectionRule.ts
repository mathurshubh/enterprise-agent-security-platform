/**
 * Detection Category and Control Types
 *
 * TYPESCRIPT CONCEPT: "Literal Union Types & Nested Interfaces"
 * ──────────────────────────────────────────────────────────────────
 * Defines the contract for active security detection rules.
 */

export type DetectionCategory =
  | 'PROMPT_SECURITY'
  | 'DATA_SECURITY'
  | 'TOOL_SECURITY'
  | 'IDENTITY_SECURITY'
  | 'BEHAVIORAL_SECURITY'
  | 'POLICY_SECURITY'
  | 'UNKNOWN'

export interface SecurityControlReference {
  framework: string
  controlId: string
  title: string
  version: string
}

export interface DetectionRule {
  // Mapped directly from API DTO
  name: string
  category: DetectionCategory
  description: string
  controls: SecurityControlReference[]

  // Optional/Nullable field (Unexposed in current Management API schema)
  status?: string | null
}
