/**
 * DetectionRulesPage — Detection Rules (/detection).
 *
 * Operational Mode: GOVERN
 *
 * Active threat detection rules catalog with OWASP LLM Top 10
 * and MITRE ATLAS/ATT&CK control mappings.
 *
 * Refactored to use shared <MetricCard>, <PageHeader>, and <ErrorState>
 * components extracted as part of the application shell PR.
 *
 * ADR-022 / 08-page-specifications.md: Page 9 — Detection Rules.
 */

import { useState } from 'react'
import { useDetectionRules } from '../../hooks/useDetectionRules'
import DetectionRuleTable from './components/DetectionRuleTable'
import PageHeader from '../../components/ui/PageHeader'
import MetricCard from '../../components/common/MetricCard'
import ErrorState from '../../components/common/ErrorState'

export default function DetectionRulesPage() {
  const { rules, loading, error } = useDetectionRules()
  const [search, setSearch] = useState<string>('')

  // ── Derived Metrics ────────────────────────────────────────────────
  const totalRules          = rules.length
  const categoriesCount     = new Set(rules.map((r) => r.category)).size
  const totalControlsMapped = rules.reduce((sum, r) => sum + r.controls.length, 0)

  // ── Client-side search filtering ───────────────────────────────────
  const query = search.trim().toLowerCase()
  const filteredRules = rules.filter((rule) =>
    rule.name.toLowerCase().includes(query) ||
    rule.category.toLowerCase().includes(query) ||
    rule.description.toLowerCase().includes(query)
  )

  return (
    <div className="space-y-6">

      <PageHeader
        title="Detection Rules"
        description="Active security detection rules and their industry framework mappings (OWASP LLM Top 10, MITRE ATLAS, MITRE ATT&CK)."
      />

      {error && <ErrorState message={error} />}

      {/* ── Summary Metrics ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="Total Rules"  value={totalRules}          loading={loading} />
        <MetricCard label="Categories"   value={categoriesCount}     loading={loading} />
        <MetricCard label="Controls"     value={totalControlsMapped} loading={loading} />
        <MetricCard label="Status"       value="Not Available"       loading={loading} />
      </div>

      {/* ── Search ───────────────────────────────────────────────── */}
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

      {/* ── Table ────────────────────────────────────────────────── */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        <DetectionRuleTable rules={filteredRules} loading={loading} />
      </div>

    </div>
  )
}
