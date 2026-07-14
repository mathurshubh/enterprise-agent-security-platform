/**
 * AuditTimelinePage — Enterprise Chronological Security Log.
 *
 * REACT CONCEPT: "Custom Hook Consumption & Component Composition"
 * ──────────────────────────────────────────────────────────────────
 * Consumes useAuditEvents hook and wires it with the presentational AuditTable.
 */

import { useState } from 'react'
import { useAuditEvents } from '../../hooks/useAuditEvents'
import AuditTable from './components/AuditTable'

export default function AuditTimelinePage() {
  const { events, loading, error } = useAuditEvents()
  const [search, setSearch] = useState<string>('')

  // ── Metrics Calculations ─────────────────────────────────────────
  const totalEvents = events.length
  
  const deniedDecisions = events.filter(
    (e) => e.decision === 'DENY'
  ).length

  const activeAgents = new Set(
    events.map((e) => e.agentId)
  ).size

  const toolsReferenced = new Set(
    events.map((e) => e.toolId)
  ).size

  // ── Client Search Filtering ──────────────────────────────────────
  const filteredEvents = events.filter((event) => {
    const query = search.trim().toLowerCase()
    return (
      event.id.toLowerCase().includes(query) ||
      event.agentId.toLowerCase().includes(query) ||
      event.toolId.toLowerCase().includes(query) ||
      event.decision.toLowerCase().includes(query)
    )
  })

  return (
    <div className="space-y-6">

      {/* ── Page Title ─────────────────────────────────────────── */}
      <div>
        <h2 className="text-xl font-bold text-text-primary">
          Audit Log
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          Immutable chronological record of all runtime tool execution security decisions.
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
          { label: 'Total Events',      value: totalEvents },
          { label: 'Denied Decisions',  value: deniedDecisions },
          { label: 'Active Agents',     value: activeAgents },
          { label: 'Tools Referenced',  value: toolsReferenced },
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
            placeholder="Search events by ID, agent, tool, or decision..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            disabled={loading || !!error}
            aria-label="Search audit events by ID, agent, tool, or decision"
            className="w-full bg-bg-surface border border-border-secondary rounded-lg px-4 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-primary disabled:opacity-50"
          />
        </div>
      </div>

      {/* ── Audit Table / Loading / Empty Container ────────────── */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        <AuditTable events={filteredEvents} loading={loading} />
      </div>
    </div>
  )
}
