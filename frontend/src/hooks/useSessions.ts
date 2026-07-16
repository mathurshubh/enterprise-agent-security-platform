/**
 * useSessions — Custom hook for managing sessions state.
 *
 * REACT CONCEPT: "Custom Hooks & Composition"
 * ──────────────────────────────────────────────────────────────────
 * Wraps the generic useApiResource hook, supplying Sessions-specific
 * error messages, logs, and renaming domain data.
 */

import { getSessions } from '../services/sessionService'
import { useApiResource } from './useApiResource'
import type { Session } from '../types/session'

export function useSessions() {
  const { data, loading, error } = useApiResource<Session>(
    getSessions,
    'Unable to retrieve sessions from the Management API. Please verify that the backend service is running and reachable.',
    'Failed to query active sessions:'
  )

  return {
    sessions: data,
    loading,
    error,
  }
}
