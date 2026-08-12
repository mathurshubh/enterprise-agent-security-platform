/**
 * DetectionRulesPage — Detection Rules (/detection).
 *
 * Operational Mode: GOVERN
 *
 * Active threat detection rules catalog directly consumed from the
 * backend Management API (GET /api/v1/detection/rules).
 *
 * Architecture layering:
 *   UI (DetectionRulesPage / DetectionRuleTable)
 *   ↓
 *   React Query Hook (useDetectionRules)
 *   ↓
 *   Service Layer (detectionRuleService)
 *   ↓
 *   API Client (apiClient)
 *   ↓
 *   FastAPI Management API (GET /api/v1/detection/rules)
 */

import { useState, useMemo } from 'react'
import { useDetectionRules } from '../../hooks/useDetectionRules'
import DetectionRuleTable from './components/DetectionRuleTable'
import type { SortField, SortDirection } from './components/DetectionRuleTable'
import PageHeader from '../../components/ui/PageHeader'
import MetricCard from '../../components/common/MetricCard'
import ErrorState from '../../components/common/ErrorState'

export default function DetectionRulesPage() {
  const { rules, loading, error } = useDetectionRules()
  const [search, setSearch] = useState<string>('')
  const [sortField, setSortField] = useState<SortField | null>(null)
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')

  // ── Derived Metrics ────────────────────────────────────────────────
  const totalRules          = rules.length
  const categoriesCount     = new Set(rules.map((r) => r.category)).size
  const totalControlsMapped = rules.reduce((sum, r) => sum + r.controls.length, 0)

  // ── Client-side search filtering ───────────────────────────────────
  const query = search.trim().toLowerCase()
  const filteredRules = useMemo(() => {
    return rules.filter((rule) =>
      rule.name.toLowerCase().includes(query) ||
      rule.category.toLowerCase().includes(query) ||
      rule.description.toLowerCase().includes(query) ||
      rule.controls.some(
        (ctrl) =>
          ctrl.controlId.toLowerCase().includes(query) ||
          ctrl.framework.toLowerCase().includes(query) ||
          ctrl.title.toLowerCase().includes(query)
      )
    )
  }, [rules, query])

  // ── Client-side deterministic sorting ─────────────────────────────
  const sortedRules = useMemo(() => {
    if (!sortField) return filteredRules

    return [...filteredRules].sort((a, b) => {
      let comparison = 0

      switch (sortField) {
        case 'name':
          comparison = a.name.localeCompare(b.name)
          break
        case 'category':
          comparison = a.category.localeCompare(b.category) || a.name.localeCompare(b.name)
          break
        case 'description':
          comparison = a.description.localeCompare(b.description) || a.name.localeCompare(b.name)
          break
        case 'controls':
          comparison = (a.controls.length - b.controls.length) || a.name.localeCompare(b.name)
          break
      }

      return sortDirection === 'asc' ? comparison : -comparison
    })
  }, [filteredRules, sortField, sortDirection])

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDirection('asc')
    }
  }

  return (
    <div className="space-y-6">

      <PageHeader
        title="Detection Rules"
        description="Active security detection rules and their industry framework mappings (OWASP LLM Top 10, MITRE ATLAS, MITRE ATT&CK)."
      />

      {error && <ErrorState message={error} />}

      {/* ── Summary Metrics (Backend-supported metrics only) ───────── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-3xl">
        <MetricCard label="Total Rules"  value={totalRules}          loading={loading} />
        <MetricCard label="Categories"   value={categoriesCount}     loading={loading} />
        <MetricCard label="Controls"     value={totalControlsMapped} loading={loading} />
      </div>

      {/* ── Search Bar ───────────────────────────────────────────── */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <input
            type="text"
            placeholder="Search rules by name, category, description, or control ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            disabled={loading || !!error}
            aria-label="Search rules by name, category, description, or control ID"
            className="w-full bg-bg-surface border border-border-secondary rounded-lg px-4 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-primary disabled:opacity-50"
          />
        </div>
      </div>

      {/* ── Table ────────────────────────────────────────────────── */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        <DetectionRuleTable
          rules={sortedRules}
          loading={loading}
          sortField={sortField}
          sortDirection={sortDirection}
          onSort={handleSort}
        />
      </div>

    </div>
  )
}
