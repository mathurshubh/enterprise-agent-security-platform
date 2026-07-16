/**
 * useTools — Custom hook for managing tool inventory state.
 *
 * REACT CONCEPT: "Custom Hooks & Composition"
 * ──────────────────────────────────────────────────────────────────
 * Wraps the generic useApiResource hook, supplying Tools-specific
 * error messages, logs, and renaming domain data.
 *
 * TODO: Once we migrate to a feature-based frontend architecture,
 * this hook should move to `features/tools/hooks/useTools.ts`.
 */

import { getTools } from '../services/toolService'
import { useApiResource } from './useApiResource'
import type { Tool } from '../types/tool'

export function useTools() {
  const { data, loading, error } = useApiResource<Tool>(
    getTools,
    'Unable to retrieve tools from the Management API. Please verify that the backend service is running and reachable.',
    'Failed to query registered tools:'
  )

  return {
    tools: data,
    loading,
    error,
  }
}
