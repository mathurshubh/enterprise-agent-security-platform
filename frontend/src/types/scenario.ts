/**
 * Scenario Category and UI Interfaces
 *
 * TYPESCRIPT CONCEPT: "Literal Union Types & Interfaces"
 * ──────────────────────────────────────────────────────────────────
 * Defines the contract for static scenario metadata retrieved from the
 * Management API library.
 */

export type ScenarioCategory =
  | 'BENIGN'
  | 'PROMPT_INJECTION'
  | 'DATA_EXFILTRATION'
  | 'TOOL_ABUSE'
  | 'PRIVILEGE_ESCALATION'
  | 'CROSS_AGENT_TRUST'
  | 'DENIAL_OF_WALLET'
  | 'RUNTIME_REPLAY'

export type ScenarioSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

export interface Scenario {
  id: string
  name: string
  description: string
  category: ScenarioCategory
  severity: ScenarioSeverity
  prompt: string
  expectedTools: string[]
  expectedDetectionRules: string[]
  expectedResponse: string
  tags: string[]
  enabled: boolean
}
