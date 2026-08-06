/**
 * AgentsPage — Agent Registry (/agents).
 *
 * Operational Mode: GOVERN
 *
 * Governance interface for registered Enterprise Agent identities,
 * risk tiers, status, and approved tool permissions.
 *
 * Architecture layering:
 *   UI (AgentsPage / AgentTable)
 *   ↓
 *   React Query Hook (useAgents)
 *   ↓
 *   Service Layer (agentService)
 *   ↓
 *   API Client (apiClient)
 *   ↓
 *   FastAPI Management API (GET /api/v1/agents)
 */

import { useState, useMemo } from 'react'
import { useAgents } from '../../hooks/useAgents'
import AgentTable from './components/AgentTable'
import type { SortField, SortDirection } from './components/AgentTable'
import PageHeader from '../../components/ui/PageHeader'
import MetricCard from '../../components/common/MetricCard'
import ErrorState from '../../components/common/ErrorState'

const STATUS_RANK: Record<string, number> = {
  ACTIVE: 1,
  REGISTERED: 2,
  SUSPENDED: 3,
  DISABLED: 4,
}

const RISK_RANK: Record<string, number> = {
  CRITICAL: 1,
  HIGH: 2,
  MEDIUM: 3,
  LOW: 4,
}

export default function AgentsPage() {
  const { agents, loading, error } = useAgents()
  const [search, setSearch] = useState<string>('')
  const [sortField, setSortField] = useState<SortField | null>(null)
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')

  // ── Derived Metrics ────────────────────────────────────────────────
  const totalAgents   = agents.length
  const healthyAgents = agents.filter((a) => a.status === 'ACTIVE').length
  const highRiskAgents = agents.filter(
    (a) => a.riskLevel === 'HIGH' || a.riskLevel === 'CRITICAL'
  ).length
  const offlineAgents = agents.filter(
    (a) => a.status === 'DISABLED' || a.status === 'SUSPENDED'
  ).length

  // ── Client-side search filtering ───────────────────────────────────
  const query = search.trim().toLowerCase()
  const filteredAgents = useMemo(() => {
    return agents.filter((agent) =>
      agent.name.toLowerCase().includes(query) ||
      agent.id.toLowerCase().includes(query) ||
      agent.owner.toLowerCase().includes(query)
    )
  }, [agents, query])

  // ── Client-side sorting ───────────────────────────────────────────
  const sortedAgents = useMemo(() => {
    if (!sortField) return filteredAgents

    return [...filteredAgents].sort((a, b) => {
      let comparison = 0

      switch (sortField) {
        case 'name':
          comparison = a.name.localeCompare(b.name)
          break
        case 'owner':
          comparison = a.owner.localeCompare(b.owner) || a.name.localeCompare(b.name)
          break
        case 'status':
          comparison = ((STATUS_RANK[a.status] ?? 99) - (STATUS_RANK[b.status] ?? 99)) || a.name.localeCompare(b.name)
          break
        case 'riskLevel':
          comparison = ((RISK_RANK[a.riskLevel] ?? 99) - (RISK_RANK[b.riskLevel] ?? 99)) || a.name.localeCompare(b.name)
          break
        case 'approvedTools':
          comparison = (a.approvedTools.length - b.approvedTools.length) || a.name.localeCompare(b.name)
          break
      }

      return sortDirection === 'asc' ? comparison : -comparison
    })
  }, [filteredAgents, sortField, sortDirection])

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
        title="Agent Registry"
        description="Audit and govern autonomous AI agent instances registered in the enterprise environment."
      />

      {error && <ErrorState message={error} />}

      {/* ── Summary Metrics ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="Total Agents"     value={totalAgents}   loading={loading} />
        <MetricCard label="Healthy Agents"   value={healthyAgents}  loading={loading} />
        <MetricCard label="High Risk Agents" value={highRiskAgents} loading={loading} />
        <MetricCard label="Offline Agents"   value={offlineAgents}  loading={loading} />
      </div>

      {/* ── Search Bar ───────────────────────────────────────────── */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <input
            type="text"
            placeholder="Search agents by ID, name, or owner..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            disabled={loading || !!error}
            aria-label="Search agents by ID, name, or owner"
            className="w-full bg-bg-surface border border-border-secondary rounded-lg px-4 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-primary disabled:opacity-50"
          />
        </div>
      </div>

      {/* ── Table ────────────────────────────────────────────────── */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        <AgentTable
          agents={sortedAgents}
          loading={loading}
          sortField={sortField}
          sortDirection={sortDirection}
          onSort={handleSort}
        />
      </div>

    </div>
  )
}
