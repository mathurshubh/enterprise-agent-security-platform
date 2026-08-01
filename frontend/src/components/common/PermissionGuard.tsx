/**
 * PermissionGuard — Authorization enforcement stub.
 *
 * Structural placeholder for future JWT-based permission enforcement.
 *
 * CURRENT BEHAVIOR (PR #70):
 *   Renders children unconditionally. No authorization logic is applied.
 *   The backend remains the sole authorization enforcement point (ADR-009).
 *
 * FUTURE BEHAVIOR (Phase 3 — JWT Enforcement):
 *   When JWT authentication is introduced per ADR-009, this component will:
 *   1. Read decoded JWT claims from an AuthContext provider.
 *   2. Evaluate whether the current user holds the required `permission`.
 *   3. Render `children` if authorized, or an "Insufficient Permissions"
 *      fallback if not.
 *
 * IMPORTANT — Security Invariant:
 *   This component controls UI *presentation* only. It does not constitute
 *   an authorization boundary. Backend API endpoints independently enforce
 *   authorization for every request. A client-side bypass of this guard
 *   does not grant access to protected backend resources.
 *
 * ADR-009: JWT enforcement is a prerequisite for production releases.
 * ADR-022: No authorization logic lives in frontend components.
 *
 * Usage:
 *   <PermissionGuard permission="approvals:write">
 *     <ReleaseButton ... />
 *   </PermissionGuard>
 */

interface PermissionGuardProps {
  /**
   * The permission string required to render children.
   * Format: '<resource>:<action>' (e.g. 'approvals:write', 'agents:read').
   * Not evaluated until JWT enforcement is introduced in Phase 3.
   */
  permission: string
  /** Content to render when the user holds the required permission. */
  children: React.ReactNode
  /**
   * Optional fallback rendered when the user lacks the required permission.
   * Defaults to null (silent hide).
   */
  fallback?: React.ReactNode
}

export default function PermissionGuard({ children }: PermissionGuardProps) {
  // TODO (Phase 3): Evaluate `permission` against decoded JWT claims.
  // Until JWT enforcement is introduced, all users see all UI surfaces.
  return <>{children}</>
}
