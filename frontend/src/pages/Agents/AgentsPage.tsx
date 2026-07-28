/**
 * AgentsPage — Agent Registry (/agents).
 *
 * Operational Mode: GOVERN
 *
 * Governance interface for registered Enterprise Agent identities,
 * risk tiers, and approved tool permissions.
 *
 * Refactored to use shared <MetricCard>, <PageHeader>, and <ErrorState>
 * components extracted as part of the application shell PR.
 *
 * ADR-022 / 08-page-specifications.md: Page 7 — Agent Registry.
 */

import { useState } from 'react'
import { useAgents } from '../../hooks/useAgents'
import AgentTable from './components/AgentTable'
import PageHeader from '../../components/ui/PageHeader'
import MetricCard from '../../components/common/MetricCard'
import ErrorState from '../../components/common/ErrorState'

export default function AgentsPage() {
  const { agents, loading, error } = useAgents()
  const [search, setSearch] = useState<string>('')

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
  const filteredAgents = agents.filter((agent) =>
    agent.name.toLowerCase().includes(query) ||
    agent.id.toLowerCase().includes(query) ||
    agent.owner.toLowerCase().includes(query)
  )

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

      {/* ── Search ───────────────────────────────────────────────── */}
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
        <AgentTable agents={filteredAgents} loading={loading} />
      </div>

    </div>
  )
}
