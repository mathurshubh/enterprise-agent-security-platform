/**
 * Agent Status and Risk Tier Literal Union Types
 *
 * TYPESCRIPT CONCEPT: "Literal Union Types"
 * ──────────────────────────────────────────────────────────────────
 * Instead of representing state codes as plain strings, TypeScript allows
 * us to specify a set of exact, allowed string literal values.  This is
 * the equivalent of a python `Enum` or `Literal` type.
 *
 * It provides strict compile-time validation: if we attempt to set status
 * to "ONLINE" or riskLevel to "VERY_HIGH" (which aren't defined below),
 * the TypeScript compiler will immediately fail the build.
 */

export type AgentStatus = 'REGISTERED' | 'ACTIVE' | 'SUSPENDED' | 'DISABLED'

export type RiskTier = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

/**
 * Agent UI Representation Interface
 *
 * This decouples UI consumption from raw backend DTO shapes.
 */
export interface Agent {
  id: string
  name: string
  status: AgentStatus
  riskLevel: RiskTier
  framework: string
  provider: string
  owner: string
  lastSeen: string
  approvedTools: string[]
}
