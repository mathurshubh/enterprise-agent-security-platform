/**
 * useAuditEvents — Audit event trail data hook.
 *
 * Fetches behavioral audit events from the Management API using
 * TanStack Query. Migrated from the manual useApiResource pattern (PR #70).
 *
 * TanStack Query provides automatic caching, background refetch, and
 * deduplication of concurrent requests across page components.
 *
 * Return API:
 *   Preserves the existing { events, loading, error } shape so all page
 *   components require zero changes.
 *
 * QueryKey:
 *   queryKeys.auditEvents.all → ['auditEvents']
 *   Defined in src/api/queryKeys.ts to avoid scattered string literals.
 *
 * Future (PR #68 — Behavioral Telemetry):
 *   This hook will be updated to consume the live BehavioralEvent stream
 *   from GET /api/v1/telemetry/events when the Telemetry Pipeline ships.
 *   The queryKey and return shape are forward-compatible.
 *
 * ADR-022: No authorization logic in hooks.
 */

import { useQuery } from '@tanstack/react-query'
import { getAuditEvents } from '../services/auditService'
import { queryKeys } from '../api/queryKeys'
import type { AuditEvent } from '../types/auditEvent'
import type { ApiError } from '../types/api'

export function useAuditEvents() {
  const { data, isLoading, error } = useQuery<AuditEvent[], ApiError>({
    queryKey: queryKeys.auditEvents.all,
    queryFn: getAuditEvents,
  })

  return {
    events: data ?? [],
    loading: isLoading,
    error: error?.message ?? null,
  }
}
