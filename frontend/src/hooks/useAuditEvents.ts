/**
 * useAuditEvents — Custom hook for managing audit logs state.
 *
 * REACT CONCEPT: "Custom Hooks & Composition"
 * ──────────────────────────────────────────────────────────────────
 * Wraps the generic useApiResource hook, supplying Audit-specific
 * error messages, logs, and renaming domain data.
 */

import { getAuditEvents } from '../services/auditService'
import { useApiResource } from './useApiResource'
import type { AuditEvent } from '../types/auditEvent'

export function useAuditEvents() {
  const { data, loading, error } = useApiResource<AuditEvent>(
    getAuditEvents,
    'Unable to retrieve audit events from the Management API. Please verify that the backend service is running and reachable.',
    'Failed to query active audit events:'
  )

  return {
    events: data,
    loading,
    error,
  }
}
