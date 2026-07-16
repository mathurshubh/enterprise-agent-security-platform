/**
 * ScenariosPage — Scenarios library management page.
 *
 * REACT CONCEPT: "State Derivation & Performance" (useMemo)
 * ──────────────────────────────────────────────────────────────────
 * Wraps calculated inventory counts (Benign, Attack, and Critical scenarios)
 * to avoid CPU recalculation cycles.
 *
 * Hoists normalized search query definitions outside array loop iterators.
 */

import { useState, useMemo } from 'react'
import { useScenarios } from '../../hooks/useScenarios'
import ScenarioTable from './components/ScenarioTable'

export default function ScenariosPage() {
  const { scenarios, loading, error } = useScenarios()
  const [search, setSearch] = useState<string>('')

  // ── Metrics Calculations ─────────────────────────────────────────
  const totalScenarios = scenarios.length

  const benignScenarios = useMemo(
    () => scenarios.filter((s) => s.category === 'BENIGN').length,
    [scenarios]
  )

  const attackScenarios = useMemo(
    () => scenarios.filter((s) => s.category !== 'BENIGN').length,
    [scenarios]
  )

  const criticalScenarios = useMemo(
    () => scenarios.filter((s) => s.severity === 'CRITICAL').length,
    [scenarios]
  )

  // ── Client Search Filtering ──────────────────────────────────────
  const query = search.trim().toLowerCase()
  const filteredScenarios = scenarios.filter((scenario) => {
    return (
      scenario.name.toLowerCase().includes(query) ||
      scenario.id.toLowerCase().includes(query) ||
      scenario.description.toLowerCase().includes(query)
    )
  })

  // ── Metrics Cards Configuration ──────────────────────────────────
  const summaryCards = [
    { label: 'Total Scenarios',    value: totalScenarios },
    { label: 'Benign Scenarios',   value: benignScenarios },
    { label: 'Attack Scenarios',   value: attackScenarios },
    { label: 'Critical Scenarios', value: criticalScenarios },
  ]

  return (
    <div className="space-y-6">

      {/* ── Page Title ─────────────────────────────────────────── */}
      <div>
        <h2 className="text-xl font-bold text-text-primary">
          Scenario Library
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          Configure and inspect simulated security scenarios for policy validation.
        </p>
      </div>

      {/* ── Error Indicator ────────────────────────────────────── */}
      {error && (
        <div className="bg-status-error/10 border border-status-error/30 rounded-xl p-4 flex flex-col gap-1.5">
          <div className="text-xs font-semibold text-status-error uppercase tracking-wider">
            Connection Error
          </div>
          <p className="text-xs text-text-secondary leading-relaxed">
            {error}
          </p>
          <div className="text-[10px] text-text-muted mt-1">
            Ensure the Enterprise Agent Security Platform backend service is running and accessible at the management port.
          </div>
        </div>
      )}

      {/* ── Metrics Cards Grid ─────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {summaryCards.map((card) => (
          <div
            key={card.label}
            className="bg-bg-surface border border-border-secondary rounded-xl p-5 flex flex-col justify-between min-h-[110px]"
          >
            <div className="text-xs font-medium text-text-muted uppercase tracking-wide">
              {card.label}
            </div>
            {loading ? (
              <div className="mt-2 h-8 w-24 bg-border-primary/40 rounded animate-pulse" />
            ) : (
              <div className="mt-2 text-2xl font-bold text-text-primary">
                {card.value}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ── Search Input & Presentational Table ─────────────────── */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        
        {/* Search header banner */}
        <div className="p-4 border-b border-border-secondary">
          <div className="max-w-md">
            <label htmlFor="scenario-search" className="sr-only">
              Search scenarios
            </label>
            <input
              id="scenario-search"
              type="text"
              placeholder="Search scenarios by name, ID, or description..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full px-3 py-2 text-xs bg-bg-surface border border-border-secondary rounded-lg focus:outline-none focus:border-border-primary text-text-primary placeholder:text-text-muted transition-colors"
            />
          </div>
        </div>

        <ScenarioTable
          scenarios={filteredScenarios}
          loading={loading}
        />

      </div>

    </div>
  )
}
