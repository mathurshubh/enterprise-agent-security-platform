/**
 * Enterprise Management API — Axios Client
 *
 * REACT CONCEPT: "Services" / "API Layer"
 * ──────────────────────────────────────────────────────────────────
 * In React applications, we separate data-fetching logic from UI
 * components.  This file creates a pre-configured Axios instance
 * that all future service modules will import.
 *
 * Think of this as the equivalent of a `requests.Session()` in
 * Python — it holds base URL, default headers, timeouts, and
 * interceptors in one place so individual API calls don't have
 * to repeat the configuration.
 *
 * ADR-009 COMPLIANCE:
 *   - The baseURL points to the Management API (/api/v1).
 *   - The client NEVER targets Runtime API endpoints.
 *   - No authentication headers are configured yet (ADR-009 states
 *     JWT enforcement is a prerequisite for production releases).
 *
 * This client is created but intentionally unused in PR #48.
 * Future PRs will build typed service wrappers around it.
 */

import axios from 'axios'

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 10_000,
  headers: {
    'Content-Type': 'application/json',
  },
})

export default apiClient
