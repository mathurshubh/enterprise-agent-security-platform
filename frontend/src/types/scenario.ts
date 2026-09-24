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

export type IntentSource = 'DETERMINISTIC_SEQUENCE' | 'UNTRUSTED_LLM_PARSER'

export interface ScenarioToolInvocation {
  toolId: string
  resource?: string | null
}

export interface ScenarioRequestEvidence {
  agentId: string
  executionMode: string
  userPrompt?: string | null
  intentSource: IntentSource
  toolSequence?: string[]
  toolInvocation?: ScenarioToolInvocation | null
}

export interface ScenarioAuthorizationCheck {
  name: string
  key: string
  status: 'passed' | 'failed' | 'not_evaluated'
  reason: string
  details: Record<string, string>
}

export interface ScenarioAuthorizationEvidence {
  decision: string
  reason: string
  checks: ScenarioAuthorizationCheck[]
}

export interface ScenarioFindingSummary {
  ruleName: string
  severity: string
  findingId: string
  description: string
}

export interface ScenarioDetectionEvidence {
  findings: ScenarioFindingSummary[]
  findingCount: number
}

export interface ScenarioRiskEvidence {
  level: string
  score: number
  findingCount: number
}

export interface ScenarioResponseEvidence {
  action: string
  reason: string
}

export interface ScenarioAuditEvidence {
  eventId: string
}

export interface ScenarioFinalDecisionEvidence {
  decision: string
}

export interface ScenarioExecutionEvidence {
  request: ScenarioRequestEvidence
  authorization?: ScenarioAuthorizationEvidence | null
  detection?: ScenarioDetectionEvidence | null
  risk?: ScenarioRiskEvidence | null
  response?: ScenarioResponseEvidence | null
  audit?: ScenarioAuditEvidence | null
  finalDecision?: ScenarioFinalDecisionEvidence | null
  refusalReason?: string | null
}

export interface ScenarioExecutionResult {
  executionId: string
  scenarioId: string
  sessionId: string
  executionMode: 'TOOL_SEQUENCE' | 'PROMPT' | string
  status: 'COMPLETED' | 'FAILED' | string
  passed: boolean | null
  authorizationDecision?: string | null
  finalDecision?: string | null
  observedDecision: string | null
  observedResponse: string | null
  observedRiskLevel: string | null
  observedFindings: string[]
  mismatches: string[]
  errorMessage: string | null
  startedAt: string
  finishedAt: string | null
  evidence?: ScenarioExecutionEvidence | null
}
