/**
 * queryClient.ts — Singleton TanStack QueryClient instance.
 *
 * The QueryClient is defined here and imported by QueryProvider.tsx.
 * Separating the client from the provider component satisfies the
 * react-refresh/only-export-components lint rule (fast-refresh requires
 * component-only exports per file).
 *
 * This separation also makes the client importable for imperative cache
 * operations (e.g. post-mutation invalidation) without importing the
 * provider component.
 *
 * Usage for imperative invalidation (future approval workflows, PR #71):
 *   import { queryClient } from '../api/queryClient'
 *   queryClient.invalidateQueries({ queryKey: queryKeys.approvals.pending })
 */

import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      /**
       * Data is considered fresh for 30 seconds after it is fetched.
       * No background refetch occurs while data is fresh.
       */
      staleTime: 30_000,

      /**
       * Unused cache entries are garbage-collected after 5 minutes.
       * Must be >= staleTime to avoid premature cache eviction.
       */
      gcTime: 300_000,

      /**
       * Retry failed requests exactly once before surfacing an error.
       * Handles transient backend restarts gracefully.
       */
      retry: 1,

      /**
       * Do not refetch when the browser window regains focus.
       * Prevents disruptive data re-renders during active SOC analysis.
       */
      refetchOnWindowFocus: false,

      /**
       * Refetch stale queries when the network reconnects.
       * Keeps the console current after connectivity interruptions.
       */
      refetchOnReconnect: true,
    },
  },
})
