/**
 * useTools — Tool inventory data hook.
 *
 * Fetches the registered tool inventory from the Management API using
 * TanStack Query. Migrated from the manual useApiResource pattern (PR #70).
 *
 * TanStack Query provides automatic caching, background refetch, and
 * deduplication of concurrent requests across page components.
 *
 * Return API:
 *   Preserves the existing { tools, loading, error } shape so all page
 *   components require zero changes.
 *
 * QueryKey:
 *   queryKeys.tools.all → ['tools']
 *   Defined in src/api/queryKeys.ts to avoid scattered string literals.
 *
 * ADR-022: No authorization logic in hooks.
 */

import { useQuery } from '@tanstack/react-query'
import { getTools } from '../services/toolService'
import { queryKeys } from '../api/queryKeys'
import type { Tool } from '../types/tool'
import type { ApiError } from '../types/api'

export function useTools() {
  const { data, isLoading, error } = useQuery<Tool[], ApiError>({
    queryKey: queryKeys.tools.all,
    queryFn: getTools,
  })

  return {
    tools: data ?? [],
    loading: isLoading,
    error: error?.message ?? null,
  }
}
