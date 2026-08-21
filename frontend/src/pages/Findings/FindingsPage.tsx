/**
 * FindingsPage — Findings & Alerts Console (/findings).
 *
 * Operational Mode: INVESTIGATE
 *
 * Centralized catalog of threat detection rule firings and behavioral
 * anomalies produced by the Behavioral Detection Engine (ADR-017).
 *
 * Connected to backend Management API:
 *   GET /api/v1/findings
 *
 * Architecture layering:
 *   UI (FindingsPage / FindingTable)
 *   ↓
 *   React Query Hook (useFindings)
 *   ↓
 *   Service Layer (findingService)
 *   ↓
 *   API Client (apiClient)
 *   ↓
 *   FastAPI Management API (GET /api/v1/findings)
 */

import { useState } from 'react'
import { useFindings } from '../../hooks/useFindings'
import FindingTable from './components/FindingTable'
import PageHeader from '../../components/ui/PageHeader'
import MetricCard from '../../components/common/MetricCard'
import ErrorState from '../../components/common/ErrorState'
import type { FindingSeverity, FindingCategory, FindingStatus } from '../../types/finding'

export default function FindingsPage() {
  const [severityFilter, setSeverityFilter] = useState<FindingSeverity | ''>('')
  const [categoryFilter, setCategoryFilter] = useState<FindingCategory | ''>('')
  const [statusFilter, setStatusFilter] = useState<FindingStatus | ''>('')

  // Pass active filters to backend API via query params
  const { findings, loading, error } = useFindings({
    severity: severityFilter || undefined,
    category: categoryFilter || undefined,
    status: statusFilter || undefined,
  })

  // ── Derived Metrics ────────────────────────────────────────────────
  const totalFindings    = findings.length
  const highRiskFindings = findings.filter((f) => f.severity === 'CRITICAL' || f.severity === 'HIGH').length
  const openFindings     = findings.filter((f) => f.status === 'OPEN').length
  const categoriesCount  = new Set(findings.map((f) => f.category)).size

  return (
    <div className="space-y-6">
      <PageHeader
        title="Findings & Alerts"
        description="Behavioral threat detection rule firings and anomaly findings recorded across all agent sessions."
      />

      {error && <ErrorState message={error} />}

      {/* ── Summary Metrics ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="Total Findings"      value={totalFindings}    loading={loading} />
        <MetricCard label="High / Critical"      value={highRiskFindings} loading={loading} />
        <MetricCard label="Open Findings"        value={openFindings}     loading={loading} />
        <MetricCard label="Categories Triggered" value={categoriesCount} loading={loading} />
      </div>

      {/* ── Simple Filter Controls ─────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-4 bg-bg-surface border border-border-secondary rounded-xl p-4">
        <div className="flex items-center gap-2">
          <label htmlFor="severity-filter" className="text-xs font-semibold text-text-muted uppercase">
            Severity:
          </label>
          <select
            id="severity-filter"
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value as FindingSeverity | '')}
            disabled={loading}
            className="bg-bg-secondary border border-border-secondary rounded-lg px-3 py-1.5 text-xs text-text-primary focus:outline-none focus:border-accent-primary"
          >
            <option value="">All Severities</option>
            <option value="CRITICAL">Critical</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
            <option value="INFO">Info</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor="category-filter" className="text-xs font-semibold text-text-muted uppercase">
            Category:
          </label>
          <select
            id="category-filter"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value as FindingCategory | '')}
            disabled={loading}
            className="bg-bg-secondary border border-border-secondary rounded-lg px-3 py-1.5 text-xs text-text-primary focus:outline-none focus:border-accent-primary"
          >
            <option value="">All Categories</option>
            <option value="PROMPT_INJECTION">Prompt Injection</option>
            <option value="DATA_EXFILTRATION">Data Exfiltration</option>
            <option value="PRIVILEGE_ESCALATION">Privilege Escalation</option>
            <option value="UNAUTHORIZED_TOOL">Unauthorized Tool</option>
            <option value="SENSITIVE_FILE_ACCESS">Sensitive File Access</option>
            <option value="BROWSER_ABUSE">Browser Abuse</option>
            <option value="SECRET_LEAKAGE">Secret Leakage</option>
            <option value="MULTI_STEP_ATTACK">Multi-Step Attack</option>
            <option value="UNKNOWN">Unknown</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor="status-filter" className="text-xs font-semibold text-text-muted uppercase">
            Status:
          </label>
          <select
            id="status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as FindingStatus | '')}
            disabled={loading}
            className="bg-bg-secondary border border-border-secondary rounded-lg px-3 py-1.5 text-xs text-text-primary focus:outline-none focus:border-accent-primary"
          >
            <option value="">All Statuses</option>
            <option value="OPEN">Open</option>
            <option value="ACKNOWLEDGED">Acknowledged</option>
            <option value="RESOLVED">Resolved</option>
            <option value="FALSE_POSITIVE">False Positive</option>
          </select>
        </div>

        {(severityFilter || categoryFilter || statusFilter) && (
          <button
            onClick={() => {
              setSeverityFilter('')
              setCategoryFilter('')
              setStatusFilter('')
            }}
            className="text-xs text-accent-primary hover:underline ml-auto"
          >
            Reset Filters
          </button>
        )}
      </div>

      {/* ── Table ────────────────────────────────────────────────── */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl overflow-hidden">
        <FindingTable findings={findings} loading={loading} />
      </div>
    </div>
  )
}
