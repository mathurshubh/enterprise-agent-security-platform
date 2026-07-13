/**
 * useDetectionRules — Custom hook for managing active rule state.
 *
 * REACT CONCEPT: "Custom Hooks"
 * ──────────────────────────────────────────────────────────────────
 * Encapsulates loaders, exception state, and asynchronous API calls.
 */

import { useState, useEffect } from 'react'
import { getDetectionRules } from '../services/detectionRuleService'
import type { DetectionRule } from '../types/detectionRule'

export function useDetectionRules() {
  const [rules, setRules] = useState<DetectionRule[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true

    const loadData = async () => {
      try {
        setLoading(true)
        setError(null)
        const data = await getDetectionRules()
        if (isMounted) {
          setRules(data)
        }
      } catch (err: unknown) {
        if (isMounted) {
          console.error('Failed to query active detection rules:', err)
          setError(
            'Unable to retrieve detection rules from the Management API. Please verify that the backend service is running and reachable.'
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
    rules,
    loading,
    error,
  }
}
