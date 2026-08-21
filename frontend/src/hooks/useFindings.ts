/**
 * useFindings — Behavioral threat detection findings data hook.
 *
 * Fetches the detection findings catalog from the Management API
 * using TanStack Query.
 *
 * TanStack Query provides automatic caching, background refetch, and
 * deduplication of concurrent requests across page components.
 *
 * Return API:
 *   { findings, loading, error, refetch }
 *
 * QueryKey:
 *   queryKeys.findings.all → ['findings']
 *   Defined in src/api/queryKeys.ts to avoid scattered string literals.
 *
 * ADR-022: No authorization logic in hooks.
 */

import { useQuery } from '@tanstack/react-query'
import { getFindings, type FindingFilters } from '../services/findingService'
import { queryKeys } from '../api/queryKeys'
import type { Finding } from '../types/finding'
import type { ApiError } from '../types/api'

export function useFindings(filters?: FindingFilters) {
  const queryKey = filters
    ? [...queryKeys.findings.all, filters]
    : queryKeys.findings.all

  const { data, isLoading, error, refetch } = useQuery<Finding[], ApiError>({
    queryKey,
    queryFn: () => getFindings(filters),
  })

  return {
    findings: data ?? [],
    loading: isLoading,
    error: error?.message ?? null,
    refetch,
  }
}
