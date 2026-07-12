/**
 * Tool — Type definition for the UI tool representation.
 *
 * TYPESCRIPT CONCEPT: "Interfaces & Optional Properties"
 * ──────────────────────────────────────────────────────────────────
 * Defines the contract for tool elements inside the React UI.
 *
 * By declaring unexposed backend parameters as optional (`?`) and
 * allowing `null` values, we cleanly represent missing metadata in our
 * data model rather than hardcoding presentation strings in the service layer.
 */

export interface Tool {
  // Mapped directly from backend ToolResponse
  id: string
  name: string
  description: string
  version: string

  // Optional/Nullable fields (Unexposed in current Management API schema)
  riskLevel?: string | null
  status?: string | null
  category?: string | null
  owner?: string | null
  timeoutSeconds?: number | null
  approvalRequired?: boolean | null
}
