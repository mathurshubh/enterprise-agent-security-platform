/**
 * SessionsPage — Enterprise Chronological Sessions Management.
 *
 * REACT CONCEPT: "Custom Hook Consumption & Component Composition"
 * ──────────────────────────────────────────────────────────────────
 * Consumes useSessions hook and wires it with the presentational SessionTable.
 */

import { useState } from 'react'
import { useSessions } from '../../hooks/useSessions'
import SessionTable from './components/SessionTable'

export default function SessionsPage() {
  const { sessions, loading, error } = useSessions()
  const [search, setSearch] = useState<string>('')

  // ── Metrics Calculations ─────────────────────────────────────────
  const totalSessions = sessions.length
  const uniqueAgents = new Set(sessions.map((s) => s.agentId)).size

  // ── Client Search Filtering ──────────────────────────────────────
  const query = search.trim().toLowerCase()
  const filteredSessions = sessions.filter((session) => {
    return (
      session.id.toLowerCase().includes(query) ||
      session.agentId.toLowerCase().includes(query)
    )
  })

  return (
    <div className="space-y-6">

      {/* ── Page Title ─────────────────────────────────────────── */}
      <div>
        <h2 className="text-xl font-bold text-text-primary">
          Sessions
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          Active agent execution sessions registered within the platform runtime.
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
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl">
        {[
          { label: 'Total Sessions', value: totalSessions },
          { label: 'Unique Agents',  value: uniqueAgents },
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
            placeholder="Search sessions by ID or agent ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            disabled={loading || !!error}
            aria-label="Search sessions by ID or agent ID"
            className="w-full bg-bg-surface border border-border-secondary rounded-lg px-4 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-primary disabled:opacity-50"
          />
        </div>
      </div>

      {/* ── Table Container ────────────────────────────────────── */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        <SessionTable sessions={filteredSessions} loading={loading} />
      </div>
    </div>
  )
}
