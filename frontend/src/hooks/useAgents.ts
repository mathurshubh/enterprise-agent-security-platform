/**
 * useAgents — Agent inventory data hook.
 *
 * Fetches the registered agent inventory from the Management API using
 * TanStack Query. Migrated from the manual useApiResource pattern (PR #70).
 *
 * TanStack Query provides:
 *   - Automatic background refetch when data goes stale (30s staleTime).
 *   - In-memory cache shared across all components that call this hook.
 *     Multiple components on the same page receive the same data with
 *     zero duplicate network requests.
 *   - Single retry on transient failure, then surfaces the error.
 *
 * Return API:
 *   Preserves the existing { agents, loading, error } shape so all page
 *   components require zero changes.
 *
 * QueryKey:
 *   queryKeys.agents.all → ['agents']
 *   Defined in src/api/queryKeys.ts to avoid scattered string literals.
 *
 * ADR-022: No authorization logic in hooks. The hook fetches and returns
 * data only; security enforcement is on the backend.
 */

import { useQuery } from '@tanstack/react-query'
import { getAgents } from '../services/agentService'
import { queryKeys } from '../api/queryKeys'
import type { Agent } from '../types/agent'
import type { ApiError } from '../types/api'

export function useAgents() {
  const { data, isLoading, error } = useQuery<Agent[], ApiError>({
    queryKey: queryKeys.agents.all,
    queryFn: getAgents,
  })

  return {
    agents: data ?? [],
    loading: isLoading,
    error: error?.message ?? null,
  }
}
