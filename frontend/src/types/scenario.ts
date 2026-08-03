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
  | 'AUTHORIZATION'
  | 'SENSITIVE_DATA'
  | 'PROVIDER_FAILURE'
  | 'SESSION_BEHAVIOR'
  | 'WORKFLOW_SECURITY'

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
  expectedRisk: string
  expectedFindings: string[]
  toolSequence: string[]
  tags: string[]
  enabled: boolean
  version: string
  schemaVersion: string
}

export interface ScenarioExecutionResult {
  executionId: string
  scenarioId: string
  sessionId: string
  executionMode: 'TOOL_SEQUENCE' | 'PROMPT' | string
  status: 'COMPLETED' | 'FAILED' | string
  passed: boolean | null
  observedDecision: string | null
  observedResponse: string | null
  observedRiskLevel: string | null
  observedFindings: string[]
  mismatches: string[]
  errorMessage: string | null
  startedAt: string
  finishedAt: string | null
}
