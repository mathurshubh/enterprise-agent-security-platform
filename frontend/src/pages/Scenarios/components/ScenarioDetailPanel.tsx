import { useState } from 'react'
import type { Scenario, ScenarioExecutionResult } from '../../../types/scenario'
import { useExecuteScenario } from '../../../hooks/useExecuteScenario'

interface ScenarioDetailPanelProps {
  scenario: Scenario
}

export default function ScenarioDetailPanel({ scenario }: ScenarioDetailPanelProps) {
  const { execute, executing, error } = useExecuteScenario()
  const [executionResult, setExecutionResult] = useState<ScenarioExecutionResult | null>(null)

  const handleRunScenario = async () => {
    try {
      const res = await execute(scenario.id)
      setExecutionResult(res)
    } catch {
      // Error handled via hook's error state
    }
  }

  return (
    <div className="p-4 bg-bg-secondary/40 border-t border-border-secondary space-y-4 text-xs">
      
      {/* ── Metadata Grid ────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        
        <div className="space-y-1">
          <span className="text-[10px] uppercase font-semibold text-text-muted">Prompt Input</span>
          <div className="p-2.5 rounded bg-bg-surface border border-border-secondary font-mono text-[11px] text-text-primary whitespace-pre-wrap">
            {scenario.prompt || <span className="italic text-text-muted">No direct prompt (Tool Sequence execution)</span>}
          </div>
        </div>

        <div className="space-y-1">
          <span className="text-[10px] uppercase font-semibold text-text-muted">Expected Outcomes</span>
          <div className="p-2.5 rounded bg-bg-surface border border-border-secondary space-y-1.5 text-[11px]">
            <div className="flex justify-between">
              <span className="text-text-muted">Risk Level:</span>
              <span className="font-semibold text-text-primary">{scenario.expectedRisk}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Response Recommendation:</span>
              <span className="font-semibold text-text-primary">{scenario.expectedResponse}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Expected Tool:</span>
              <span className="font-mono text-text-primary">{scenario.expectedTools[0] || 'None'}</span>
            </div>
          </div>
        </div>

        <div className="space-y-1">
          <span className="text-[10px] uppercase font-semibold text-text-muted">Scenario Details</span>
          <div className="p-2.5 rounded bg-bg-surface border border-border-secondary space-y-1.5 text-[11px]">
            <div className="flex justify-between">
              <span className="text-text-muted">Version:</span>
              <span className="font-mono text-text-primary">v{scenario.version}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Schema Version:</span>
              <span className="font-mono text-text-primary">v{scenario.schemaVersion}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Execution Mode:</span>
              <span className="font-mono text-text-primary">
                {scenario.prompt ? 'PROMPT' : 'TOOL_SEQUENCE'}
              </span>
            </div>
          </div>
        </div>

      </div>

      {/* ── Tags ─────────────────────────────────────────────────── */}
      {scenario.tags.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[10px] uppercase font-semibold text-text-muted mr-1">Tags:</span>
          {scenario.tags.map((tag) => (
            <span
              key={tag}
              className="px-1.5 py-0.5 rounded bg-bg-surface border border-border-primary text-[10px] text-text-secondary font-mono"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* ── Execution Action ──────────────────────────────────────── */}
      <div className="flex items-center justify-between pt-2 border-t border-border-secondary/60">
        <div className="text-text-secondary text-[11px]">
          Runs evaluation through deterministic Runtime Security Pipeline.
        </div>
        <button
          onClick={handleRunScenario}
          disabled={executing}
          className="px-4 py-1.5 rounded-lg bg-accent-primary text-white font-semibold text-xs hover:bg-accent-primary/90 disabled:opacity-50 transition-colors flex items-center gap-1.5"
        >
          {executing && <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />}
          {executing ? 'Executing...' : 'Execute Scenario'}
        </button>
      </div>

      {/* ── Execution Error ────────────────────────────────────────── */}
      {error && (
        <div className="p-3 rounded-lg bg-status-error/10 border border-status-error/30 text-status-error text-xs">
          Execution failed: {error}
        </div>
      )}

      {/* ── Execution Results Display ──────────────────────────────── */}
      {executionResult && (
        <div className="p-3.5 rounded-xl bg-bg-surface border border-border-secondary space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-bold text-text-primary">Evaluation Result:</span>
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                  executionResult.passed
                    ? 'bg-status-active/15 text-status-active border border-status-active/30'
                    : 'bg-status-error/15 text-status-error border border-status-error/30'
                }`}
              >
                {executionResult.passed ? 'PASSED' : 'FAILED'}
              </span>
            </div>
            <span className="text-[10px] font-mono text-text-muted">
              Execution ID: {executionResult.executionId}
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
            <div className="p-2 rounded bg-bg-secondary/40 border border-border-secondary">
              <div className="text-text-muted text-[10px]">Decision</div>
              <div className="font-semibold text-text-primary">{executionResult.observedDecision || '—'}</div>
            </div>
            <div className="p-2 rounded bg-bg-secondary/40 border border-border-secondary">
              <div className="text-text-muted text-[10px]">Observed Risk</div>
              <div className="font-semibold text-text-primary">{executionResult.observedRiskLevel || '—'}</div>
            </div>
            <div className="p-2 rounded bg-bg-secondary/40 border border-border-secondary">
              <div className="text-text-muted text-[10px]">Observed Response</div>
              <div className="font-semibold text-text-primary">{executionResult.observedResponse || '—'}</div>
            </div>
            <div className="p-2 rounded bg-bg-secondary/40 border border-border-secondary">
              <div className="text-text-muted text-[10px]">Findings Count</div>
              <div className="font-semibold text-text-primary">{executionResult.observedFindings.length}</div>
            </div>
          </div>

          {executionResult.mismatches.length > 0 && (
            <div className="space-y-1">
              <span className="text-[10px] font-semibold text-status-error uppercase">Mismatches</span>
              <ul className="list-disc list-inside space-y-0.5 text-text-secondary text-[11px]">
                {executionResult.mismatches.map((mismatch, idx) => (
                  <li key={idx} className="font-mono text-status-error">{mismatch}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

    </div>
  )
}
