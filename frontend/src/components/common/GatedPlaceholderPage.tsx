/**
 * GatedPlaceholderPage — Reusable placeholder for Phase 2+ gated routes.
 *
 * Both /approvals and /findings share an identical placeholder structure:
 *   1. PageHeader (title + description)
 *   2. Warning notice identifying the required backend APIs
 *   3. Empty state card
 *
 * This component eliminates that duplication. When Phase 2 backend APIs
 * become available, each page is upgraded independently by replacing its
 * GatedPlaceholderPage render with the real implementation.
 *
 * ADR-022 / 11-implementation-roadmap.md:
 *   Phase 2 gating: Approval Queue and Findings pages require backend
 *   Behavioral Intelligence APIs (v0.13.0). This component renders their
 *   Phase 1 placeholder presentation.
 */

import PageHeader from '../ui/PageHeader'
import EmptyState from '../common/EmptyState'

interface GatedPlaceholderPageProps {
  /** Page title rendered in the PageHeader. */
  title: string
  /** Page description rendered in the PageHeader. */
  description: string
  /** Label of the primary backend API endpoint required to unlock this page. */
  requiredApi: string
  /** Empty state title shown in the data card. */
  emptyTitle: string
  /** Empty state description shown below the title. */
  emptyDescription: string
}

export default function GatedPlaceholderPage({
  title,
  description,
  requiredApi,
  emptyTitle,
  emptyDescription,
}: GatedPlaceholderPageProps) {
  return (
    <div className="space-y-6">

      <PageHeader title={title} description={description} />

      {/* Phase 2 gated notice */}
      <div className="bg-status-warning/10 border border-status-warning/30 rounded-xl p-4">
        <div className="text-xs font-semibold text-status-warning uppercase tracking-wider">
          Phase 2 — Backend APIs Required
        </div>
        <p className="text-xs text-text-secondary mt-1 leading-relaxed">
          This page requires{' '}
          <code className="font-mono text-text-primary">{requiredApi}</code>.
          {' '}It will become fully operational in v0.13.0 when those APIs ship.
        </p>
      </div>

      {/* Empty state card */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        <EmptyState title={emptyTitle} description={emptyDescription} />
      </div>

    </div>
  )
}
