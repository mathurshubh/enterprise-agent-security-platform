/**
 * useDetectionRules — Custom hook for managing active rule state.
 *
 * REACT CONCEPT: "Custom Hooks & Composition"
 * ──────────────────────────────────────────────────────────────────
 * Wraps the generic useApiResource hook, supplying Rules-specific
 * error messages, logs, and renaming domain data.
 */

import { getDetectionRules } from '../services/detectionRuleService'
import { useApiResource } from './useApiResource'
import type { DetectionRule } from '../types/detectionRule'

export function useDetectionRules() {
  const { data, loading, error } = useApiResource<DetectionRule>(
    getDetectionRules,
    'Unable to retrieve detection rules from the Management API. Please verify that the backend service is running and reachable.',
    'Failed to query active detection rules:'
  )

  return {
    rules: data,
    loading,
    error,
  }
}
