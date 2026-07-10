/**
 * ToolsPage — Tool inventory.
 *
 * ADR-009: "An inventory displaying registered tools, version
 * metadata, descriptions, capability levels, and associated
 * governance/operational profiles."
 *
 * ADR-005: Only ToolMetadata is exposed through the management
 * plane — executable BaseTool instances are never surfaced.
 *
 * This is a placeholder.  A future PR will implement the tool
 * table backed by GET /api/v1/tools.
 */

export default function ToolsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-text-primary">
          Tool Registry
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          Registered tools and their metadata. Executable tool objects are never exposed through the management plane.
        </p>
      </div>

      {/* Table placeholder */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        <div className="grid grid-cols-4 gap-4 px-5 py-3 border-b border-border-secondary text-xs font-semibold uppercase tracking-wide text-text-muted">
          <span>Tool ID</span>
          <span>Name</span>
          <span>Description</span>
          <span>Version</span>
        </div>

        <div className="px-5 py-12 text-center">
          <p className="text-sm text-text-muted">
            Tool metadata will be populated from the Enterprise Management API.
          </p>
        </div>
      </div>
    </div>
  )
}
