/**
 * AgentsPage — Registered agent catalog.
 *
 * ADR-009: "A searchable catalog listing all registered agents,
 * their current status (Active, Suspended, etc.), designated owner,
 * risk tier, and their allowed tool authorization scopes."
 *
 * This is a placeholder.  A future PR will implement the agent
 * table backed by GET /api/v1/agents.
 */

export default function AgentsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-text-primary">
          Agent Registry
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          Registered AI agents, their risk tiers, and authorization scopes.
        </p>
      </div>

      {/* Table placeholder */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        {/* Column headers */}
        <div className="grid grid-cols-5 gap-4 px-5 py-3 border-b border-border-secondary text-xs font-semibold uppercase tracking-wide text-text-muted">
          <span>Agent ID</span>
          <span>Name</span>
          <span>Owner</span>
          <span>Risk Tier</span>
          <span>Status</span>
        </div>

        {/* Empty state */}
        <div className="px-5 py-12 text-center">
          <p className="text-sm text-text-muted">
            Agent data will be populated from the Enterprise Management API.
          </p>
        </div>
      </div>
    </div>
  )
}
