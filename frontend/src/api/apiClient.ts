/**
 * apiClient.ts — Enterprise Management API Axios client.
 *
 * Pre-configured Axios instance shared by all service modules.
 * Equivalent to a `requests.Session()` in Python — holds base URL,
 * default headers, timeout, and interceptors in one place.
 *
 * ADR-009 Compliance:
 *   - baseURL targets the Management API (/api/v1) exclusively.
 *   - This client NEVER targets Runtime API endpoints.
 *   - No security decisions are made in the frontend. The backend
 *     enforces authorization for every request independently.
 *
 * Interceptors:
 *   Request — JWT Authorization header stub (Phase 3 integration point).
 *   Response — Error normalization into ApiError shape.
 *
 * Error Normalization:
 *   All HTTP and network errors are translated into a consistent
 *   ApiError structure before reaching hooks and components.
 *   This decouples error display components from Axios internals.
 */

import axios, { type AxiosError } from 'axios'
import type { ApiError } from '../types/api'

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 10_000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ── Request Interceptor ──────────────────────────────────────────────────────

/**
 * JWT Authorization header injection stub.
 *
 * Phase 3 integration point: When JWT authentication is introduced per
 * ADR-009, replace this stub with a call to the AuthContext token accessor:
 *
 *   const token = authStore.getAccessToken()
 *   if (token) {
 *     config.headers.Authorization = `Bearer ${token}`
 *   }
 *
 * Until JWT enforcement is introduced, all requests are sent unauthenticated.
 */
apiClient.interceptors.request.use(
  (config) => {
    // TODO (Phase 3 — ADR-009): Inject JWT Authorization header here.
    return config
  },
  (error) => Promise.reject(error)
)

// ── Response Interceptor ─────────────────────────────────────────────────────

/**
 * Normalize all Axios errors into a consistent ApiError shape.
 *
 * Catches both HTTP error responses (4xx, 5xx) and network-level failures
 * (timeouts, DNS resolution failures, CORS) and maps them to ApiError so
 * that hooks and components never need to inspect Axios internals.
 */
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string; message?: string }>) => {
    const apiError: ApiError = {
      status: error.response?.status ?? 0,
      message: deriveErrorMessage(error),
      detail: error.response?.data?.detail,
    }
    // Attach the normalized error to the rejection so hooks can inspect it.
    return Promise.reject(apiError)
  }
)

/**
 * Derive a human-readable error message from an AxiosError.
 * Priority: backend message → HTTP status text → network error → generic.
 */
function deriveErrorMessage(error: AxiosError<{ detail?: string; message?: string }>): string {
  if (error.response) {
    const backendMsg = error.response.data?.message ?? error.response.data?.detail
    if (backendMsg) return backendMsg
    if (error.response.status === 404) return 'Resource not found.'
    if (error.response.status === 403) return 'Access denied.'
    if (error.response.status === 401) return 'Authentication required.'
    if (error.response.status >= 500) return 'Backend service error. Please try again.'
    return `Request failed with status ${error.response.status}.`
  }
  if (error.code === 'ECONNABORTED') return 'Request timed out. Verify the backend service is reachable.'
  if (error.message) return error.message
  return 'Unable to reach the Management API. Verify the backend service is running.'
}

export default apiClient
