/**
 * featureFlags.ts — Client-side feature flag registry.
 *
 * Defines static boolean flags that gate Phase 2+ capabilities on the
 * availability of backend APIs. Flags are evaluated deterministically at
 * compile time — no LLM, no runtime computation, no server-side evaluation.
 *
 * Security Principle:
 *   These flags control UI *presentation* only. They do not enforce
 *   authorization. Authorization enforcement remains exclusively on the
 *   backend (ADR-009, ADR-022). A flag set to `false` simply prevents
 *   the UI from rendering a surface; it does NOT prevent a determined
 *   user from calling the underlying API directly.
 *
 * Flag Lifecycle:
 *   - `false` in this PR: backend API not yet implemented.
 *   - `true` in the target PR: flipped when the backend API ships and the
 *     full vertical slice (backend + hook + UI) is complete.
 *   - Flags are removed after the feature is stable and universally available.
 *
 * Phase 2 Roadmap:
 *   PR #68 — BEHAVIORAL_TELEMETRY_ENABLED (BehavioralEventStore + /audit live feed)
 *   PR #69 — FINDINGS_ENABLED (/findings console)
 *   PR #70 — RISK_ENGINE_ENABLED (dynamic risk badges)
 *   PR #71 — ENFORCEMENT_ENGINE_ENABLED (/approvals interactive workflow)
 *   PR #72 — SESSION_TIMELINE_ENABLED (/sessions/:id detail view)
 */

/**
 * Behavioral Telemetry Pipeline (ADR-015, ADR-016).
 * Gates live telemetry data on the /audit trail page.
 * Backend API: GET /api/v1/telemetry/events
 */
export const BEHAVIORAL_TELEMETRY_ENABLED = false

/**
 * Behavioral Detection Engine — Findings Console (ADR-017).
 * Gates the /findings page operational mode.
 * Backend API: GET /api/v1/findings
 */
export const FINDINGS_ENABLED = false

/**
 * Behavioral Risk Engine — Dynamic Risk State (ADR-018).
 * Gates dynamic risk badges on /agents, /sessions, and the Command Center.
 * Backend API: GET /api/v1/risk/state/{session_id}
 */
export const RISK_ENGINE_ENABLED = false

/**
 * Behavioral Enforcement Engine — Approval Queue (ADR-019, ADR-020).
 * Gates the interactive approval workflow on /approvals.
 * Backend API: GET /api/v1/approvals/pending
 */
export const ENFORCEMENT_ENGINE_ENABLED = false

/**
 * Session Investigation Workspace — Timeline Replay (ADR-020).
 * Gates the /sessions/:id single-panel session detail view.
 * Backend API: GET /api/v1/sessions/{id}/events
 */
export const SESSION_TIMELINE_ENABLED = false
