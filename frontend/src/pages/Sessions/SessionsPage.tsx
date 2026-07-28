/**
 * SessionsPage — Sessions list (/sessions).
 *
 * Operational Mode: INVESTIGATE
 *
 * Promoted from orphaned route to primary sidebar navigation in Phase 1
 * per ADR-022 / 11-implementation-roadmap.md.
 *
 * Refactored to use shared <MetricCard>, <PageHeader>, and <ErrorState>
 * components extracted as part of the application shell PR.
 *
 * ADR-022 / 08-page-specifications.md: Page 3 — Sessions List.
 */

import { useState } from 'react'
import { useSessions } from '../../hooks/useSessions'
import SessionTable from './components/SessionTable'
import PageHeader from '../../components/ui/PageHeader'
import MetricCard from '../../components/common/MetricCard'
import ErrorState from '../../components/common/ErrorState'

export default function SessionsPage() {
  const { sessions, loading, error } = useSessions()
  const [search, setSearch] = useState<string>('')

  // ── Derived Metrics ────────────────────────────────────────────────
  const totalSessions = sessions.length
  const uniqueAgents  = new Set(sessions.map((s) => s.agentId)).size

  // ── Client-side search filtering ───────────────────────────────────
  const query = search.trim().toLowerCase()
  const filteredSessions = sessions.filter((session) =>
    session.id.toLowerCase().includes(query) ||
    session.agentId.toLowerCase().includes(query)
  )

  return (
    <div className="space-y-6">

      <PageHeader
        title="Sessions"
        description="Active and historical agent execution sessions registered within the platform runtime."
      />

      {error && <ErrorState message={error} />}

      {/* ── Summary Metrics ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl">
        <MetricCard label="Total Sessions" value={totalSessions} loading={loading} />
        <MetricCard label="Unique Agents"  value={uniqueAgents}  loading={loading} />
      </div>

      {/* ── Search ───────────────────────────────────────────────── */}
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

      {/* ── Table ────────────────────────────────────────────────── */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        <SessionTable sessions={filteredSessions} loading={loading} />
      </div>

    </div>
  )
}
