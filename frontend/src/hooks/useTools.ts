/**
 * useTools — Custom hook for managing tool inventory state.
 *
 * REACT CONCEPT: "Custom Hooks"
 * ──────────────────────────────────────────────────────────────────
 * Encapsulates loaders, exception state, and asynchronous API calls.
 *
 * TODO: Once we migrate to a feature-based frontend architecture,
 * this hook should move to `features/tools/hooks/useTools.ts`.
 */

import { useState, useEffect } from 'react'
import { getTools } from '../services/toolService'
import type { Tool } from '../types/tool'

export function useTools() {
  const [tools, setTools] = useState<Tool[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true

    const loadData = async () => {
      try {
        setLoading(true)
        setError(null)
        const data = await getTools()
        if (isMounted) {
          setTools(data)
        }
      } catch (err: unknown) {
        if (isMounted) {
          console.error('Failed to query registered tools:', err)
          setError(
            'Unable to retrieve tools from the Management API. Please verify that the backend service is running and reachable.'
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
    tools,
    loading,
    error,
  }
}
