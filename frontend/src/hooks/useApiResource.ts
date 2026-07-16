/**
 * useApiResource — Generic API data fetching hook.
 *
 * REACT CONCEPT: "Custom Hooks & Generics"
 * ──────────────────────────────────────────────────────────────────
 * Centralizes duplicate fetching logic, loading state tracking, and
 * cleanup lifecycles for all platform resources.
 */

import { useState, useEffect } from 'react'

export function useApiResource<T>(
  fetchFn: () => Promise<T[]>,
  errorMessage: string,
  logMessage: string
) {
  const [data, setData] = useState<T[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true

    const loadData = async () => {
      try {
        setLoading(true)
        setError(null)
        const resData = await fetchFn()
        if (isMounted) {
          setData(resData)
        }
      } catch (err: unknown) {
        if (isMounted) {
          console.error(logMessage, err)
          setError(errorMessage)
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
  }, [fetchFn, errorMessage, logMessage])

  return {
    data,
    loading,
    error,
  }
}
