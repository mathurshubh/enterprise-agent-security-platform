import { useMutation } from '@tanstack/react-query'
import { executeScenario } from '../services/scenarioService'
import type { ScenarioExecutionResult } from '../types/scenario'
import type { ApiError } from '../types/api'

export function useExecuteScenario() {
  const mutation = useMutation<ScenarioExecutionResult, ApiError, string>({
    mutationFn: (scenarioId: string) => executeScenario(scenarioId),
  })

  return {
    execute: mutation.mutateAsync,
    executing: mutation.isPending,
    result: mutation.data ?? null,
    error: mutation.error?.message ?? null,
    reset: mutation.reset,
  }
}
