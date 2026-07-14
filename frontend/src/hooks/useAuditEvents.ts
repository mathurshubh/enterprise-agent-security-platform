/**
 * useAuditEvents — Custom hook for managing audit logs state.
 *
 * REACT CONCEPT: "Custom Hooks"
 * ──────────────────────────────────────────────────────────────────
 * Encapsulates loaders, exception state, and asynchronous API calls.
 */

import { useState, useEffect } from 'react'
import { getAuditEvents } from '../services/auditService'
import type { AuditEvent } from '../types/auditEvent'

export function useAuditEvents() {
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true

    const loadData = async () => {
      try {
        setLoading(true)
        setError(null)
        const data = await getAuditEvents()
        if (isMounted) {
          setEvents(data)
        }
      } catch (err: unknown) {
        if (isMounted) {
          console.error('Failed to query active audit events:', err)
          setError(
            'Unable to retrieve audit events from the Management API. Please verify that the backend service is running and reachable.'
          )
        }
      } finally {
        if (isMounted) {
          setLoading(false)
        }
      }
    }

    loadData()

    return () => {
      isMounted = false
    }
  }, [])

  return {
    events,
    loading,
    error,
  }
}
