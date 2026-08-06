/**
 * ToolsPage — Tool Registry (/tools).
 *
 * Operational Mode: GOVERN
 *
 * Inventory of registered capability tools directly consumed from the
 * backend Management API (GET /api/v1/tools).
 *
 * Architecture layering:
 *   UI (ToolsPage / ToolTable)
 *   ↓
 *   React Query Hook (useTools)
 *   ↓
 *   Service Layer (toolService)
 *   ↓
 *   API Client (apiClient)
 *   ↓
 *   FastAPI Management API (GET /api/v1/tools)
 */

import { useState, useMemo } from 'react'
import { useTools } from '../../hooks/useTools'
import ToolTable from './components/ToolTable'
import type { SortField, SortDirection } from './components/ToolTable'
import PageHeader from '../../components/ui/PageHeader'
import MetricCard from '../../components/common/MetricCard'
import ErrorState from '../../components/common/ErrorState'

export default function ToolsPage() {
  const { tools, loading, error } = useTools()
  const [search, setSearch] = useState<string>('')
  const [sortField, setSortField] = useState<SortField | null>(null)
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')

  // ── Derived Metrics ────────────────────────────────────────────────
  const totalTools = tools.length

  // ── Client-side search filtering ───────────────────────────────────
  const query = search.trim().toLowerCase()
  const filteredTools = useMemo(() => {
    return tools.filter((tool) =>
      tool.name.toLowerCase().includes(query) ||
      tool.id.toLowerCase().includes(query) ||
      tool.description.toLowerCase().includes(query)
    )
  }, [tools, query])

  // ── Client-side deterministic sorting ─────────────────────────────
  const sortedTools = useMemo(() => {
    if (!sortField) return filteredTools

    return [...filteredTools].sort((a, b) => {
      let comparison = 0

      switch (sortField) {
        case 'id':
          comparison = a.id.localeCompare(b.id) || a.name.localeCompare(b.name)
          break
        case 'name':
          comparison = a.name.localeCompare(b.name) || a.id.localeCompare(b.id)
          break
        case 'description':
          comparison = a.description.localeCompare(b.description) || a.name.localeCompare(b.name) || a.id.localeCompare(b.id)
          break
        case 'version':
          comparison = a.version.localeCompare(b.version) || a.name.localeCompare(b.name) || a.id.localeCompare(b.id)
          break
      }

      return sortDirection === 'asc' ? comparison : -comparison
    })
  }, [filteredTools, sortField, sortDirection])

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
        title="Tool Registry"
        description="Audit and govern executable capability tools registered in the enterprise environment."
      />

      {error && <ErrorState message={error} />}

      {/* ── Summary Metrics (Backend-supported metrics only) ───────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="Total Tools" value={totalTools} loading={loading} />
      </div>

      {/* ── Search Bar ───────────────────────────────────────────── */}
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
        <ToolTable
          tools={sortedTools}
          loading={loading}
          sortField={sortField}
          sortDirection={sortDirection}
          onSort={handleSort}
        />
      </div>

    </div>
  )
}
