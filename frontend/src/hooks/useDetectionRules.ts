/**
 * useDetectionRules — Detection rule inventory data hook.
 *
 * Fetches the configured detection rule catalog from the Management API
 * using TanStack Query. Migrated from the manual useApiResource pattern (PR #70).
 *
 * TanStack Query provides automatic caching, background refetch, and
 * deduplication of concurrent requests across page components.
 *
 * Return API:
 *   Preserves the existing { rules, loading, error } shape so all page
 *   components require zero changes.
 *
 * QueryKey:
 *   queryKeys.detectionRules.all → ['detectionRules']
 *   Defined in src/api/queryKeys.ts to avoid scattered string literals.
 *
 * ADR-022: No authorization logic in hooks.
 */

import { useQuery } from '@tanstack/react-query'
import { getDetectionRules } from '../services/detectionRuleService'
import { queryKeys } from '../api/queryKeys'
import type { DetectionRule } from '../types/detectionRule'
import type { ApiError } from '../types/api'

export function useDetectionRules() {
  const { data, isLoading, error } = useQuery<DetectionRule[], ApiError>({
    queryKey: queryKeys.detectionRules.all,
    queryFn: getDetectionRules,
  })

  return {
    rules: data ?? [],
    loading: isLoading,
    error: error?.message ?? null,
  }
}
