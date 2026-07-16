/**
 * useScenarios — Custom hook for managing active scenario catalog state.
 *
 * REACT CONCEPT: "Custom Hooks & Composition"
 * ──────────────────────────────────────────────────────────────────
 * Wraps the generic useApiResource hook, supplying Scenario-specific
 * error messages, logs, and renaming domain data.
 */

import { getScenarios } from '../services/scenarioService'
import { useApiResource } from './useApiResource'
import type { Scenario } from '../types/scenario'

export function useScenarios() {
  const { data, loading, error } = useApiResource<Scenario>(
    getScenarios,
    'Unable to retrieve scenarios from the Management API. Please verify that the backend service is running and reachable.',
    'Failed to query registered scenarios:'
  )

  return {
    scenarios: data,
    loading,
    error,
  }
}
