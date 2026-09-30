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
  /**
   * The tool identity the request named. Always present, including when the request was
   * malformed or named a tool that does not exist — recording what was asked for is the
   * point. This is what the "Tool" column means.
   */
  requestedToolId: string
  /**
   * The tool family the security pipeline resolved, or null when it resolved none.
   * Nullable deliberately: a request refused at a trust boundary established no tool
   * identity at all. Never substituted into the requested field.
   */
  toolId: string | null
  /**
   * The concrete version that resolved, or null when no implementation was established.
   * Null while `toolId` is set means the family resolved but the version did not.
   */
  toolVersion: string | null
  decision: AuditDecision
  timestamp: string // ISO-8601 string
}
