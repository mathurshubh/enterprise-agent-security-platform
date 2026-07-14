/**
 * Audit Decision and Event Types
 *
 * TYPESCRIPT CONCEPT: "Literal Union Types & Interfaces"
 * ──────────────────────────────────────────────────────────────────
 * Defines the contract for logged security pipeline execution results.
 */

export type AuditDecision = 'ALLOW' | 'DENY' | 'APPROVAL_REQUIRED' | 'UNKNOWN'

export interface AuditEvent {
  // Mapped directly from API DTO
  id: string
  agentId: string
  toolId: string
  decision: AuditDecision
  timestamp: string // ISO-8601 string
}
