/**
 * DashboardService — Observability data fetching operations.
 *
 * REACT CONCEPT: "Service Layer" / "API Integration"
 * ──────────────────────────────────────────────────────────────────
 * In clean architecture, we isolate all network communication and
 * API consumption from our presentation layer (the React components).
 * Components should focus entirely on layout, state lifecycle, and
 * user interaction — they should never need to know the details
 * of HTTP requests, API routes, or request headers.
 *
 * By defining `getPlatformInfo` here:
 *   1. We isolate the endpoint path (`/info`) from the pages.
 *   2. We type the output using our `PlatformInfo` interface.
 *   3. We hide the Axios library completely from the UI code.
 *
 * If we ever swap Axios for `fetch` or update the API route path,
 * we only need to change it in this file, keeping all dashboard
 * UI components completely untouched.
 *
 * ADR-009 / ADR-008 COMPLIANCE:
 *   - Restricts API access to the read-only control plane (`/info`).
 *   - Interacts only with `apiClient`, which governs target URLs.
 */

import apiClient from '../api/apiClient'
import type { PlatformInfo } from '../types/platformInfo'

/**
 * Fetch platform overview statistics and version information.
 *
 * TYPESCRIPT CONCEPT: "Promise<T>"
 * ──────────────────────────────────────────────────────────────────
 * An asynchronous function returns a `Promise`.  A `Promise<PlatformInfo>`
 * represents a value that will eventually be resolved (the backend response)
 * or rejected (a network error).  This is equivalent to using `await` with
 * coroutines in Python (`async def`).
 */
export const getPlatformInfo = async (): Promise<PlatformInfo> => {
  const response = await apiClient.get<PlatformInfo>('/info')
  return response.data
}
