/**
 * api.ts — Shared API contract types.
 *
 * Defines the shared structural types for Management API responses and errors.
 * All service modules map backend DTOs to these shared types before returning
 * data to hooks or components.
 *
 * ADR-009 Compliance:
 *   - No authorization or security logic lives here.
 *   - Types are pure structural contracts; they carry no behavior.
 *
 * Future PRs:
 *   - PaginatedResponse<T> is ready for use when the Management API adopts
 *     cursor-based or offset pagination (Phase 3).
 *   - ApiError.status enables HTTP-status-aware error display in ErrorState.
 */

/**
 * Normalized API error surfaced to hooks and components.
 *
 * The API client interceptor (src/api/apiClient.ts) translates all
 * Axios/HTTP errors into this shape before they reach application code.
 */
export interface ApiError {
  /** HTTP status code (e.g. 400, 404, 500). 0 for network-level failures. */
  status: number
  /** Human-readable error summary for display in ErrorState components. */
  message: string
  /** Optional additional context from the backend error payload. */
  detail?: string
}

/**
 * Generic paginated list response envelope.
 *
 * Matches the FastAPI-standard response structure used by the Management API
 * for collection endpoints that support pagination.
 *
 * @template T — The item type contained in the page.
 */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
