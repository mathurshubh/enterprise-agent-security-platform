/**
 * useRiskAssessments — Dynamic Risk Engine data hook.
 *
 * Fetches risk assessments from the Management API using TanStack Query.
 *
 * TanStack Query provides automatic caching, background refetch, and
 * deduplication of concurrent requests across page components.
 *
 * Return API:
 *   { riskAssessments, loading, error, refetch }
 *
 * QueryKey:
 *   queryKeys.risk.all / queryKeys.risk.bySession / queryKeys.risk.byAgent
 *
 * ADR-022: No authorization logic in hooks.
 */

import { useQuery } from '@tanstack/react-query'
import { getRiskAssessments, type RiskAssessmentFilters } from '../services/riskAssessmentService'
import { queryKeys } from '../api/queryKeys'
import type { RiskAssessment } from '../types/riskAssessment'
import type { ApiError } from '../types/api'

export function useRiskAssessments(filters?: RiskAssessmentFilters) {
  const queryKey = filters
    ? [...queryKeys.risk.bySession(filters.session_id || 'all'), filters]
    : queryKeys.risk.bySession('all')

  const { data, isLoading, error, refetch } = useQuery<RiskAssessment[], ApiError>({
    queryKey,
    queryFn: () => getRiskAssessments(filters),
  })

  return {
    riskAssessments: data ?? [],
    loading: isLoading,
    error: error?.message ?? null,
    refetch,
  }
}
