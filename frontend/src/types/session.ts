/**
 * Session Interface contract.
 *
 * TYPESCRIPT CONCEPT: "Interfaces"
 * ──────────────────────────────────────────────────────────────────
 * Defines the contract for active agent interaction sessions.
 */

export interface Session {
  id: string
  agentId: string
  startedAt: string // ISO-8601 string
}
