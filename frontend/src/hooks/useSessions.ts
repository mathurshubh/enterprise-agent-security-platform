/**
 * useSessions — Active execution sessions data hook.
 *
 * Fetches active agent execution sessions from the Management API using
 * TanStack Query. Migrated from the manual useApiResource pattern (PR #70).
 *
 * TanStack Query provides automatic caching, background refetch, and
 * deduplication of concurrent requests across page components.
 *
 * Return API:
 *   Preserves the existing { sessions, loading, error } shape so all page
 *   components require zero changes.
 *
 * QueryKey:
 *   queryKeys.sessions.all → ['sessions']
 *   Defined in src/api/queryKeys.ts to avoid scattered string literals.
 *
 * Future (PR #72):
 *   A queryKeys.sessions.byId(sessionId) variant will be added to support
 *   the Session Investigation Workspace (/sessions/:id) detail view.
 *
 * ADR-022: No authorization logic in hooks.
 */

import { useQuery } from '@tanstack/react-query'
import { getSessions } from '../services/sessionService'
import { queryKeys } from '../api/queryKeys'
import type { Session } from '../types/session'
import type { ApiError } from '../types/api'

export function useSessions() {
  const { data, isLoading, error } = useQuery<Session[], ApiError>({
    queryKey: queryKeys.sessions.all,
    queryFn: getSessions,
  })

  return {
    sessions: data ?? [],
    loading: isLoading,
    error: error?.message ?? null,
  }
}
