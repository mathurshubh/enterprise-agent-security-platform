/**
 * FindingsPage — Findings & Alerts placeholder (/findings).
 *
 * Operational Mode: INVESTIGATE
 *
 * Purpose: Centralized catalog of threat detection rule firings and behavioral
 * anomalies produced by the Behavioral Detection Engine (ADR-017).
 *
 * Phase 2 gated: The full findings catalog will be implemented in Phase 2
 * (v0.13.0) when the backend Behavioral Intelligence APIs ship:
 *   GET /api/v1/findings
 *   GET /api/v1/findings/:id
 *
 * ADR-022 / 08-page-specifications.md: Page 5 — Findings & Alerts.
 */

import GatedPlaceholderPage from '../../components/common/GatedPlaceholderPage'

export default function FindingsPage() {
  return (
    <GatedPlaceholderPage
      title="Findings"
      description="Behavioral threat detection rule firings and anomaly findings across all agent sessions."
      requiredApi="GET /api/v1/findings"
      emptyTitle="No findings available"
      emptyDescription="Behavioral threat detection findings will appear here once the Behavioral Intelligence backend APIs are connected."
    />
  )
}
