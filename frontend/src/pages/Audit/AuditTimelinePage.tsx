/**
 * AuditTimelinePage — Immutable audit event log.
 *
 * ADR-009: "An immutable chronological log showing runtime tool
 * invocation decisions (Allow/Deny/Approval Required) mapped
 * against timestamps.  In initial versions, this page visualizes
 * Audit Events as flat records."
 *
 * This is a placeholder.  A future PR will implement the audit
 * event table backed by GET /api/v1/audit/events.
 */

export default function AuditTimelinePage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-text-primary">
          Audit Timeline
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          Immutable chronological record of all runtime security decisions.
        </p>
      </div>

      {/* Table placeholder */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        <div className="grid grid-cols-5 gap-4 px-5 py-3 border-b border-border-secondary text-xs font-semibold uppercase tracking-wide text-text-muted">
          <span>Event ID</span>
          <span>Agent ID</span>
          <span>Tool ID</span>
          <span>Decision</span>
          <span>Timestamp</span>
        </div>

        <div className="px-5 py-12 text-center">
          <p className="text-sm text-text-muted">
            Audit events will be populated from the Enterprise Management API.
          </p>
          <p className="text-xs text-text-muted mt-2">
            Session correlation is planned for future versions once session identity
            is integrated into the audit event model.
          </p>
        </div>
      </div>
    </div>
  )
}
