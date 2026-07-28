/**
 * ApprovalQueuePage — Approval Queue placeholder (/approvals).
 *
 * Operational Mode: MONITOR
 *
 * Purpose: Work queue enabling authorized SOC analysts to review, approve,
 * reject, or escalate agent sessions held in REQUIRE_APPROVAL or HOLD_SESSION
 * states per ADR-019 (Behavioral Enforcement Engine) and ADR-020 (AgentSecOps).
 *
 * Phase 2 gated: The interactive approval workflow will be implemented in
 * Phase 2 (v0.13.0) when the backend Approval Queue APIs ship:
 *   GET  /api/v1/approvals/pending
 *   POST /api/v1/approvals/:id/release
 *   POST /api/v1/approvals/:id/reject
 *
 * ADR-022 / 08-page-specifications.md: Page 2 — Approval Queue.
 */

import GatedPlaceholderPage from '../../components/common/GatedPlaceholderPage'

export default function ApprovalQueuePage() {
  return (
    <GatedPlaceholderPage
      title="Approval Queue"
      description="Review, approve, or reject agent sessions held pending human authorization."
      requiredApi="GET /api/v1/approvals/pending"
      emptyTitle="No pending approvals"
      emptyDescription="Sessions requiring human review will appear here once the Behavioral Enforcement Engine is connected."
    />
  )
}
