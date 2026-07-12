/**
 * AgentsPage — Enterprise Agent Governance Console.
 *
 * REACT CONCEPT: "Custom Hook Consumption & Component Composition"
 * ──────────────────────────────────────────────────────────────────
 * Consumes useAgents hook and wires it with the presentational AgentTable.
 */

import { useState } from 'react'
import { useAgents } from '../../hooks/useAgents'
import AgentTable from './components/AgentTable'

export default function AgentsPage() {
  const { agents, loading, error } = useAgents()
  const [search, setSearch] = useState<string>('')

  // ── Metrics Calculations ─────────────────────────────────────────
  const totalAgents = agents.length
  
  const healthyAgents = agents.filter(
    (a) => a.status === 'ACTIVE'
  ).length

  const highRiskAgents = agents.filter(
    (a) => a.riskLevel === 'HIGH' || a.riskLevel === 'CRITICAL'
  ).length

  const offlineAgents = agents.filter(
    (a) => a.status === 'DISABLED' || a.status === 'SUSPENDED'
  ).length

  // ── Client Search Filtering ──────────────────────────────────────
  const filteredAgents = agents.filter((agent) => {
    // Trims whitespace and normalizes query to lower case
    const query = search.trim().toLowerCase()
    return (
      agent.name.toLowerCase().includes(query) ||
      agent.id.toLowerCase().includes(query) ||
      agent.owner.toLowerCase().includes(query)
    )
  })

  return (
    <div className="space-y-6">

      {/* ── Page Title ─────────────────────────────────────────── */}
      <div>
        <h2 className="text-xl font-bold text-text-primary">
          Agent Inventory
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          Audit and govern autonomous AI agent instances registered in the enterprise environment.
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
          { label: 'Total Agents',     value: totalAgents },
          { label: 'Healthy Agents',   value: healthyAgents },
          { label: 'High Risk Agents', value: highRiskAgents },
          { label: 'Offline Agents',   value: offlineAgents },
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
            placeholder="Search agents by ID, name, or owner..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            disabled={loading || !!error}
            aria-label="Search agents by ID, name, or owner"
            className="w-full bg-bg-surface border border-border-secondary rounded-lg px-4 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-primary disabled:opacity-50"
          />
        </div>
      </div>

      {/* ── Agent Table / Loading / Empty Container ────────────── */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        <AgentTable agents={filteredAgents} loading={loading} />
      </div>
    </div>
  )
}
