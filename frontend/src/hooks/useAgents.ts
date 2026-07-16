/**
 * useAgents — Custom hook for managing agent inventory state.
 *
 * REACT CONCEPT: "Custom Hooks & Composition"
 * ──────────────────────────────────────────────────────────────────
 * Wraps the generic useApiResource hook, supplying Agents-specific
 * error messages, logs, and renaming domain data.
 *
 * TODO: Once we migrate to a feature-based frontend architecture,
 * this hook should move to `features/agents/hooks/useAgents.ts`.
 */

import { getAgents } from '../services/agentService'
import { useApiResource } from './useApiResource'
import type { Agent } from '../types/agent'

export function useAgents() {
  const { data, loading, error } = useApiResource<Agent>(
    getAgents,
    'Unable to retrieve agents from the Management API. Please verify that the backend service is running and reachable.',
    'Failed to query registered agents:'
  )

  return {
    agents: data,
    loading,
    error,
  }
}
