/**
 * useScenarios — Attack simulation scenario catalog hook.
 *
 * Fetches the registered attack simulation scenarios from the Management API
 * using TanStack Query. Migrated from the manual useApiResource pattern (PR #70).
 *
 * TanStack Query provides automatic caching, background refetch, and
 * deduplication of concurrent requests across page components.
 *
 * Return API:
 *   Preserves the existing { scenarios, loading, error } shape so all page
 *   components require zero changes.
 *
 * QueryKey:
 *   queryKeys.scenarios.all → ['scenarios']
 *   Defined in src/api/queryKeys.ts to avoid scattered string literals.
 *
 * Future (Enterprise Scenario Runner):
 *   Scenario execution (run, cancel, status) will use TanStack Mutation
 *   hooks added alongside the Scenario Runner UI. Cache invalidation via
 *   queryClient.invalidateQueries({ queryKey: queryKeys.scenarios.all })
 *   will refresh the catalog after execution.
 *
 * ADR-022: No authorization logic in hooks.
 */

import { useQuery } from '@tanstack/react-query'
import { getScenarios } from '../services/scenarioService'
import { queryKeys } from '../api/queryKeys'
import type { Scenario } from '../types/scenario'
import type { ApiError } from '../types/api'

export function useScenarios() {
  const { data, isLoading, error } = useQuery<Scenario[], ApiError>({
    queryKey: queryKeys.scenarios.all,
    queryFn: getScenarios,
  })

  return {
    scenarios: data ?? [],
    loading: isLoading,
    error: error?.message ?? null,
  }
}
