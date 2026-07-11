/**
 * PlatformInfo — Type definition for the platform metrics payload.
 *
 * TYPESCRIPT CONCEPT: "Interfaces"
 * ──────────────────────────────────────────────────────────────────
 * An interface in TypeScript defines the structural contract of an
 * object at compile time.  It acts as a schema that ensures any
 * object claiming to be of type `PlatformInfo` must contain these
 * exact properties with their designated types.
 *
 * In Python, you would use Pydantic models (like `BaseModel`) or
 * standard dataclasses to enforce these boundaries.  TypeScript
 * performs this validation during compilation (e.g. when running
 * `npm run build`), which prevents runtime TypeErrors when accessing
 * properties on dynamic API responses.
 *
 * ADR-009 / ADR-008 COMPLIANCE:
 *   - Matches the fields returned by GET /api/v1/info exactly.
 *   - Avoids the use of `any`, ensuring strict type safety.
 */

export interface PlatformInfo {
  platform: string
  version: string
  api_version: string
  registered_agents: number
  registered_tools: number
  registered_detection_rules: number
  audit_events: number
}
