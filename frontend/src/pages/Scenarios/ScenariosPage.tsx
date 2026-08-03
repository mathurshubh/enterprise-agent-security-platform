/**
 * ScenariosPage — Scenario Library (/scenarios).
 *
 * Operational Mode: GOVERN
 *
 * Promoted from orphaned route to primary sidebar navigation in Phase 1
 * per ADR-022 / 11-implementation-roadmap.md.
 *
 * Library of security validation benchmarks and prompt injection /
 * data exfiltration attack scenarios per ADR-010.
 *
 * Refactored to use shared <MetricCard>, <PageHeader>, and <ErrorState>
 * components extracted as part of the application shell PR.
 *
 * ADR-022 / 08-page-specifications.md: Page 10 — Scenario Library.
 */

import { useState, useMemo } from 'react'
import { useScenarios } from '../../hooks/useScenarios'
import ScenarioTable from './components/ScenarioTable'
import PageHeader from '../../components/ui/PageHeader'
import MetricCard from '../../components/common/MetricCard'
import ErrorState from '../../components/common/ErrorState'

export default function ScenariosPage() {
  const { scenarios, loading, error } = useScenarios()
  const [search, setSearch] = useState<string>('')
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL')

  // ── Derived Metrics ────────────────────────────────────────────────
  const totalScenarios    = scenarios.length
  const benignScenarios   = useMemo(() => scenarios.filter((s) => s.category === 'BENIGN').length, [scenarios])
  const attackScenarios   = useMemo(() => scenarios.filter((s) => s.category !== 'BENIGN').length, [scenarios])
  const criticalScenarios = useMemo(() => scenarios.filter((s) => s.severity === 'CRITICAL' || s.severity === 'HIGH').length, [scenarios])

  const categories = [
    'ALL',
    'PROMPT_INJECTION',
    'DATA_EXFILTRATION',
    'AUTHORIZATION',
    'SENSITIVE_DATA',
    'TOOL_ABUSE',
    'PROVIDER_FAILURE',
    'SESSION_BEHAVIOR',
    'WORKFLOW_SECURITY',
    'BENIGN',
  ]

  // ── Client-side search + category filtering ───────────────────────
  const query = search.trim().toLowerCase()
  const filteredScenarios = scenarios.filter((scenario) => {
    const matchesCategory = selectedCategory === 'ALL' || scenario.category === selectedCategory
    const matchesSearch =
      scenario.name.toLowerCase().includes(query) ||
      scenario.id.toLowerCase().includes(query) ||
      scenario.description.toLowerCase().includes(query) ||
      scenario.tags.some((tag) => tag.toLowerCase().includes(query))
    return matchesCategory && matchesSearch
  })

  return (
    <div className="space-y-6">

      <PageHeader
        title="Scenario Library"
        description="Security validation benchmarks and attack scenarios for policy and detection rule verification."
      />

      {error && <ErrorState message={error} />}

      {/* ── Summary Metrics ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="Total Scenarios"    value={totalScenarios} loading={loading} />
        <MetricCard label="Benign Baselines"        value={benignScenarios} loading={loading} />
        <MetricCard label="Attack Scenarios"        value={attackScenarios} loading={loading} />
        <MetricCard label="High/Critical Risk"      value={criticalScenarios} loading={loading} />
      </div>

      {/* ── Category Filter Pills ──────────────────────────────────── */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => setSelectedCategory(cat)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              selectedCategory === cat
                ? 'bg-accent-primary text-white'
                : 'bg-bg-surface border border-border-secondary text-text-secondary hover:border-border-primary'
            }`}
          >
            {cat.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* ── Search + Table ────────────────────────────────────────── */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        <div className="p-4 border-b border-border-secondary">
          <div className="max-w-md">
            <label htmlFor="scenario-search" className="sr-only">Search scenarios</label>
            <input
              id="scenario-search"
              type="text"
              placeholder="Search scenarios by name, stable ID, description, or tag..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full px-3 py-2 text-xs bg-bg-surface border border-border-secondary rounded-lg focus:outline-none focus:border-border-primary text-text-primary placeholder:text-text-muted transition-colors"
            />
          </div>
        </div>
        <ScenarioTable scenarios={filteredScenarios} loading={loading} />
      </div>

    </div>
  )
}
