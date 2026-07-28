/**
 * AuditTimelinePage — Audit Trail (/audit).
 *
 * Operational Mode: INVESTIGATE
 *
 * Immutable chronological log of authoritative runtime security decisions.
 *
 * Refactored to use shared <MetricCard>, <PageHeader>, and <ErrorState>
 * components extracted as part of the application shell PR.
 *
 * ADR-022 / 08-page-specifications.md: Page 6 — Audit Trail.
 */

import { useState } from 'react'
import { useAuditEvents } from '../../hooks/useAuditEvents'
import AuditTable from './components/AuditTable'
import PageHeader from '../../components/ui/PageHeader'
import MetricCard from '../../components/common/MetricCard'
import ErrorState from '../../components/common/ErrorState'

export default function AuditTimelinePage() {
  const { events, loading, error } = useAuditEvents()
  const [search, setSearch] = useState<string>('')

  // ── Derived Metrics ────────────────────────────────────────────────
  const totalEvents      = events.length
  const deniedDecisions  = events.filter((e) => e.decision === 'DENY').length
  const activeAgents     = new Set(events.map((e) => e.agentId)).size
  const toolsReferenced  = new Set(events.map((e) => e.toolId)).size

  // ── Client-side search filtering ───────────────────────────────────
  const query = search.trim().toLowerCase()
  const filteredEvents = events.filter((event) =>
    event.id.toLowerCase().includes(query) ||
    event.agentId.toLowerCase().includes(query) ||
    event.toolId.toLowerCase().includes(query) ||
    event.decision.toLowerCase().includes(query)
  )

  return (
    <div className="space-y-6">

      <PageHeader
        title="Audit Trail"
        description="Immutable chronological record of all runtime tool execution security decisions."
      />

      {error && <ErrorState message={error} />}

      {/* ── Summary Metrics ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="Total Events"     value={totalEvents}     loading={loading} />
        <MetricCard label="Denied Decisions" value={deniedDecisions} loading={loading} />
        <MetricCard label="Active Agents"    value={activeAgents}    loading={loading} />
        <MetricCard label="Tools Referenced" value={toolsReferenced} loading={loading} />
      </div>

      {/* ── Search ───────────────────────────────────────────────── */}
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

      {/* ── Table ────────────────────────────────────────────────── */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        <AuditTable events={filteredEvents} loading={loading} />
      </div>

    </div>
  )
}
