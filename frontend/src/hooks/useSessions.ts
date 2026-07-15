/**
 * useSessions — Custom hook for managing sessions state.
 *
 * REACT CONCEPT: "Custom Hooks"
 * ──────────────────────────────────────────────────────────────────
 * Encapsulates loaders, exception state, and asynchronous API calls.
 */

import { useState, useEffect } from 'react'
import { getSessions } from '../services/sessionService'
import type { Session } from '../types/session'

export function useSessions() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true

    const loadData = async () => {
      try {
        setLoading(true)
        setError(null)
        const data = await getSessions()
        if (isMounted) {
          setSessions(data)
        }
      } catch (err: unknown) {
        if (isMounted) {
          console.error('Failed to query active sessions:', err)
          setError(
            'Unable to retrieve sessions from the Management API. Please verify that the backend service is running and reachable.'
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
    sessions,
    loading,
    error,
  }
}
