/**
 * ToolsPage — Enterprise Tool Registry Console.
 *
 * REACT CONCEPT: "Custom Hook Consumption & Component Composition"
 * ──────────────────────────────────────────────────────────────────
 * Consumes useTools hook and wires it with the presentational ToolTable.
 */

import { useState } from 'react'
import { useTools } from '../../hooks/useTools'
import ToolTable from './components/ToolTable'

export default function ToolsPage() {
  const { tools, loading, error } = useTools()
  const [search, setSearch] = useState<string>('')

  // ── Metrics Calculations ─────────────────────────────────────────
  // Total tools is derived from actual API returns. Unexposed metrics
  // show "Not Available" as instructed.
  const totalTools = tools.length
  const enabledTools = 'Not Available'
  const requiresApproval = 'Not Available'
  const categories = 'Not Available'

  // ── Client Search Filtering ──────────────────────────────────────
  const filteredTools = tools.filter((tool) => {
    const query = search.trim().toLowerCase()
    return (
      tool.name.toLowerCase().includes(query) ||
      tool.id.toLowerCase().includes(query) ||
      tool.description.toLowerCase().includes(query)
    )
  })

  return (
    <div className="space-y-6">

      {/* ── Page Title ─────────────────────────────────────────── */}
      <div>
        <h2 className="text-xl font-bold text-text-primary">
          Tool Inventory
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          Audit and govern executable capability tools registered in the enterprise environment.
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
          { label: 'Total Tools',       value: totalTools },
          { label: 'Enabled Tools',     value: enabledTools },
          { label: 'Requires Approval', value: requiresApproval },
          { label: 'Categories',       value: categories },
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
            placeholder="Search tools by ID, name, or description..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            disabled={loading || !!error}
            aria-label="Search tools by ID, name, or description"
            className="w-full bg-bg-surface border border-border-secondary rounded-lg px-4 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-primary disabled:opacity-50"
          />
        </div>
      </div>

      {/* ── Tool Table / Loading / Empty Container ────────────── */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        <ToolTable tools={filteredTools} loading={loading} />
      </div>
    </div>
  )
}
