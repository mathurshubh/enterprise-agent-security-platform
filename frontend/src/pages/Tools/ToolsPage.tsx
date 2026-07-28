/**
 * ToolsPage — Tool Registry (/tools).
 *
 * Operational Mode: GOVERN
 *
 * Inventory of executable tools, parameter definitions, and capability policies.
 *
 * Refactored to use shared <MetricCard>, <PageHeader>, and <ErrorState>
 * components extracted as part of the application shell PR.
 *
 * ADR-022 / 08-page-specifications.md: Page 8 — Tool Registry.
 */

import { useState } from 'react'
import { useTools } from '../../hooks/useTools'
import ToolTable from './components/ToolTable'
import PageHeader from '../../components/ui/PageHeader'
import MetricCard from '../../components/common/MetricCard'
import ErrorState from '../../components/common/ErrorState'

export default function ToolsPage() {
  const { tools, loading, error } = useTools()
  const [search, setSearch] = useState<string>('')

  // ── Derived Metrics ────────────────────────────────────────────────
  const totalTools = tools.length

  // ── Client-side search filtering ───────────────────────────────────
  const query = search.trim().toLowerCase()
  const filteredTools = tools.filter((tool) =>
    tool.name.toLowerCase().includes(query) ||
    tool.id.toLowerCase().includes(query) ||
    tool.description.toLowerCase().includes(query)
  )

  return (
    <div className="space-y-6">

      <PageHeader
        title="Tool Registry"
        description="Audit and govern executable capability tools registered in the enterprise environment."
      />

      {error && <ErrorState message={error} />}

      {/* ── Summary Metrics ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="Total Tools"       value={totalTools}       loading={loading} />
        <MetricCard label="Enabled Tools"     value="Not Available"    loading={loading} />
        <MetricCard label="Requires Approval" value="Not Available"    loading={loading} />
        <MetricCard label="Categories"        value="Not Available"    loading={loading} />
      </div>

      {/* ── Search ───────────────────────────────────────────────── */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <input
            type="text"
            placeholder="Search tools by ID, name, or description..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            disabled={loading || !!error}
            aria-label="Search tools by ID, name, or description"
            className="w-full bg-bg-surface border border-border-secondary rounded-lg px-4 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-primary disabled:opacity-50"
          />
        </div>
      </div>

      {/* ── Table ────────────────────────────────────────────────── */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        <ToolTable tools={filteredTools} loading={loading} />
      </div>

    </div>
  )
}
