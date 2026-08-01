/**
 * useApiResource — Generic manual data fetching hook.
 *
 * @deprecated
 *   This hook is superseded by TanStack Query (PR #70).
 *   All domain hooks (useAgents, useTools, useSessions, useAuditEvents,
 *   useDetectionRules, useScenarios) have been migrated to useQuery().
 *
 *   This file is retained for reference only. Do not use it in new hooks.
 *   It will be removed in a future cleanup PR once all consumers are confirmed
 *   to have migrated.
 *
 *   Migration pattern:
 *
 *   BEFORE (useApiResource):
 *     const { data, loading, error } = useApiResource<T>(fetchFn, 'error msg', 'log msg')
 *
 *   AFTER (TanStack Query):
 *     const { data, isLoading, error } = useQuery<T[], ApiError>({
 *       queryKey: queryKeys.myDomain.all,
 *       queryFn: fetchFn,
 *     })
 *
 * REACT CONCEPT: "Custom Hooks & Generics"
 * ──────────────────────────────────────────────────────────────────
 * Originally centralized duplicate fetching logic, loading state tracking,
 * and cleanup lifecycles for all platform resources. TanStack Query now
 * handles these concerns with superior caching, deduplication, and
 * background refetch capabilities.
 */

import { useState, useEffect } from 'react'

/** @deprecated Use TanStack Query useQuery() instead. See file-level JSDoc. */
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
