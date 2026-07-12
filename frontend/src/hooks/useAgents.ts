/**
 * useAgents — Custom hook for managing agent inventory state.
 *
 * REACT CONCEPT: "Custom Hooks"
 * ──────────────────────────────────────────────────────────────────
 * Custom hooks allow us to extract component state logic into
 * reusable, testable functions.
 *
 * TODO: Once we migrate to a feature-based frontend architecture,
 * this hook should move to `features/agents/hooks/useAgents.ts`.
 */

import { useState, useEffect } from 'react'
import { getAgents } from '../services/agentService'
import type { Agent } from '../types/agent'

export function useAgents() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true

    const loadData = async () => {
      try {
        setLoading(true)
        setError(null)
        const data = await getAgents()
        if (isMounted) {
          setAgents(data)
        }
      } catch (err: unknown) {
        if (isMounted) {
          console.error('Failed to query registered agents:', err)
          setError(
            'Unable to retrieve agents from the Management API. Please verify that the backend service is running and reachable.'
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
    agents,
    loading,
    error,
  }
}
