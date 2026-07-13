/**
 * DetectionRulesPage — Enterprise Threat Detection Registry.
 *
 * REACT CONCEPT: "Custom Hook Consumption & Component Composition"
 * ──────────────────────────────────────────────────────────────────
 * Consumes useDetectionRules hook and wires it with the presentational
 * DetectionRuleTable component.
 */

import { useState } from 'react'
import { useDetectionRules } from '../../hooks/useDetectionRules'
import DetectionRuleTable from './components/DetectionRuleTable'

export default function DetectionRulesPage() {
  const { rules, loading, error } = useDetectionRules()
  const [search, setSearch] = useState<string>('')

  // ── Metrics Calculations ─────────────────────────────────────────
  const totalRules = rules.length
  
  const categoriesCount = new Set(
    rules.map((r) => r.category)
  ).size

  const totalControlsMapped = rules.reduce(
    (sum, rule) => sum + rule.controls.length,
    0
  )

  const rulesStatus = 'Not Available'

  // ── Client Search Filtering ──────────────────────────────────────
  const filteredRules = rules.filter((rule) => {
    const query = search.trim().toLowerCase()
    return (
      rule.name.toLowerCase().includes(query) ||
      rule.category.toLowerCase().includes(query) ||
      rule.description.toLowerCase().includes(query)
    )
  })

  return (
    <div className="space-y-6">

      {/* ── Page Title ─────────────────────────────────────────── */}
      <div>
        <h2 className="text-xl font-bold text-text-primary">
          Detection Rules
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          Audit active security detection rules and their standard industry framework mappings.
        </p>
      </div>

      {/* ── Operator Error Indicator ───────────────────────────── */}
      {error && (
        <div className="bg-status-error/10 border border-status-error/30 rounded-xl p-4">
          <div className="text-xs font-semibold text-status-error uppercase tracking-wider">
            Connection Failure
          </div>
          <p className="text-xs text-text-secondary mt-1 leading-relaxed">
            {error}
          </p>
        </div>
      )}

      {/* ── Summary Cards Grid ─────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Total Rules', value: totalRules },
          { label: 'Categories',  value: categoriesCount },
          { label: 'Controls',    value: totalControlsMapped },
          { label: 'Status',      value: rulesStatus },
        ].map((card) => (
          <div
            key={card.label}
            className="bg-bg-surface border border-border-secondary rounded-xl p-5 flex flex-col justify-between min-h-[110px]"
          >
            <div className="text-xs font-medium text-text-muted uppercase tracking-wide">
              {card.label}
            </div>
            {loading ? (
              <div className="mt-2 h-8 w-16 bg-border-primary/40 rounded animate-pulse" />
            ) : (
              <div className="mt-2 text-2xl font-bold text-text-primary">
                {card.value}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ── Search Bar ─────────────────────────────────────────── */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <input
            type="text"
            placeholder="Search rules by name, category, or description..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            disabled={loading || !!error}
            aria-label="Search rules by name, category, or description"
            className="w-full bg-bg-surface border border-border-secondary rounded-lg px-4 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-primary disabled:opacity-50"
          />
        </div>
      </div>

      {/* ── Rule Table / Loading / Empty Container ────────────── */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        <DetectionRuleTable rules={filteredRules} loading={loading} />
      </div>
    </div>
  )
}
