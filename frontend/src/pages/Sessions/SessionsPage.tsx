/**
 * SessionsPage — Sessions list (/sessions).
 *
 * Operational Mode: INVESTIGATE
 *
 * Read-only Session Explorer connected directly to the backend Management API (GET /api/v1/sessions).
 *
 * Architecture layering:
 *   UI (SessionsPage / SessionTable)
 *   ↓
 *   React Query Hook (useSessions)
 *   ↓
 *   Service Layer (sessionService)
 *   ↓
 *   API Client (apiClient)
 *   ↓
 *   FastAPI Management API (GET /api/v1/sessions)
 */

import { useState, useMemo } from 'react'
import { useSessions } from '../../hooks/useSessions'
import SessionTable from './components/SessionTable'
import type { SortField, SortDirection } from './components/SessionTable'
import PageHeader from '../../components/ui/PageHeader'
import MetricCard from '../../components/common/MetricCard'
import ErrorState from '../../components/common/ErrorState'

export default function SessionsPage() {
  const { sessions, loading, error } = useSessions()
  const [search, setSearch] = useState<string>('')
  const [sortField, setSortField] = useState<SortField | null>(null)
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')

  // ── Derived Metrics ────────────────────────────────────────────────
  const totalSessions = sessions.length
  const uniqueAgents  = new Set(sessions.map((s) => s.agentId)).size

  // ── Client-side search filtering ───────────────────────────────────
  const query = search.trim().toLowerCase()
  const filteredSessions = useMemo(() => {
    return sessions.filter((session) =>
      session.id.toLowerCase().includes(query) ||
      session.agentId.toLowerCase().includes(query)
    )
  }, [sessions, query])

  // ── Client-side deterministic sorting ─────────────────────────────
  const sortedSessions = useMemo(() => {
    if (!sortField) return filteredSessions

    return [...filteredSessions].sort((a, b) => {
      let comparison = 0

      switch (sortField) {
        case 'id':
          comparison = a.id.localeCompare(b.id) || a.agentId.localeCompare(b.agentId)
          break
        case 'agentId':
          comparison = a.agentId.localeCompare(b.agentId) || a.id.localeCompare(b.id)
          break
        case 'startedAt':
          comparison = (new Date(a.startedAt).getTime() - new Date(b.startedAt).getTime()) || a.id.localeCompare(b.id)
          break
      }

      return sortDirection === 'asc' ? comparison : -comparison
    })
  }, [filteredSessions, sortField, sortDirection])

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
        title="Sessions"
        description="Active and historical agent execution sessions registered within the platform runtime."
      />

      {error && <ErrorState message={error} />}

      {/* ── Summary Metrics ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl">
        <MetricCard label="Total Sessions" value={totalSessions} loading={loading} />
        <MetricCard label="Unique Agents"  value={uniqueAgents}  loading={loading} />
      </div>

      {/* ── Search Bar ───────────────────────────────────────────── */}
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
        <SessionTable
          sessions={sortedSessions}
          loading={loading}
          sortField={sortField}
          sortDirection={sortDirection}
          onSort={handleSort}
        />
      </div>

    </div>
  )
}
