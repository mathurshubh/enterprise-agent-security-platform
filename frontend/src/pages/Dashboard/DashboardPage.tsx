/**
 * DashboardPage — Central platform visibility dashboard.
 *
 * REACT CONCEPT: "State Lifecycle" (useState)
 * ──────────────────────────────────────────────────────────────────
 * React components are state machines.  When state variables change,
 * React automatically schedules a re-render to update the DOM.
 *
 * `useState<T>(initialValue)` returns a tuple containing:
 *   1. The current state value (read-only).
 *   2. A setter function to update the value.
 *
 * We define three states to govern our data loading lifecycle:
 *   - `info` (PlatformInfo | null): The live statistics.
 *   - `loading` (boolean): Flag indicating if an API request is active.
 *   - `error` (string | null): Holds the error message if the API fails.
 *
 * REACT CONCEPT: "Side Effects" (useEffect)
 * ──────────────────────────────────────────────────────────────────
 * By default, React components are pure functions that only render
 * UI.  Interacting with the outside world (like fetching API data)
 * is called a "side effect".
 *
 * `useEffect(callback, dependencyArray)` allows us to schedule side
 * effects.  The dependency array `[]` tells React to run this effect
 * EXACTLY ONCE when the component "mounts" (is first rendered on
 * screen).  This matches the lifecycle of `componentDidMount` in
 * class-based React.
 *
 * ADR-009 / ADR-008 COMPLIANCE:
 *   - Does NOT import Axios or formulate URL strings directly.
 *   - Communicates only with the abstract `DashboardService`.
 *   - Implements error recovery to prevent application crashes.
 */

import { useState, useEffect } from 'react'
import { getPlatformInfo } from '../../services/dashboardService'
import type { PlatformInfo } from '../../types/platformInfo'

export default function DashboardPage() {
  const [info, setInfo] = useState<PlatformInfo | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true

    const loadData = async () => {
      try {
        setLoading(true)
        setError(null)
        const data = await getPlatformInfo()
        
        // Prevent state updates if component unmounts before response finishes
        if (isMounted) {
          setInfo(data)
        }
      } catch (err: unknown) {
        if (isMounted) {
          console.error('Failed to load dashboard metrics:', err)
          setError(
            err instanceof Error 
              ? err.message 
              : 'An unexpected connection error occurred while querying the platform.'
          )
        }
      } finally {
        if (isMounted) {
          setLoading(false)
        }
      }
    }

    loadData()

    return () => {
      isMounted = false
    }
  }, [])

  return (
    <div className="space-y-6">

      {/* ── Page Header ────────────────────────────────────────── */}
      <div>
        <h2 className="text-xl font-bold text-text-primary">
          Security Overview
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          High-level security metrics for the Enterprise Agent Security Platform.
        </p>
      </div>

      {/* ── Error Indicator ────────────────────────────────────── */}
      {error && (
        <div className="bg-status-error/10 border border-status-error/30 rounded-xl p-4 flex flex-col gap-1.5">
          <div className="text-xs font-semibold text-status-error uppercase tracking-wider">
            Connection Error
          </div>
          <p className="text-xs text-text-secondary leading-relaxed">
            {error}
          </p>
          <div className="text-[10px] text-text-muted mt-1">
            Ensure the Enterprise Agent Security Platform backend service is running and accessible at the management port.
          </div>
        </div>
      )}

      {/* ── Metrics Grid ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { 
            label: 'Active Agents', 
            value: info?.registered_agents,
            fallback: '—'
          },
          { 
            label: 'Registered Tools', 
            value: info?.registered_tools,
            fallback: '—'
          },
          { 
            label: 'Detection Rules', 
            value: info?.registered_detection_rules,
            fallback: '—'
          },
          { 
            label: 'Audit Events', 
            value: info?.audit_events,
            fallback: '—'
          },
        ].map((card) => (
          <div
            key={card.label}
            className="bg-bg-surface border border-border-secondary rounded-xl p-5 flex flex-col justify-between min-h-[110px]"
          >
            <div className="text-xs font-medium text-text-muted uppercase tracking-wide">
              {card.label}
            </div>
            
            {/* 
              REACT CONCEPT: "Conditional Rendering" / "Loading Skeletons"
              ──────────────────────────────────────────────────────────────
              While the request is pending, we render an animated skeleton card
              to prevent layout shifting.  Once data is loaded, we replace the
              skeleton with the actual numeric values.
            */}
            {loading ? (
              <div className="mt-2 h-8 w-24 bg-border-primary/40 rounded animate-pulse" />
            ) : (
              <div className="mt-2 text-2xl font-bold text-text-primary">
                {card.value !== undefined ? card.value : card.fallback}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ── Platform Information Card ──────────────────────────── */}
      <div className="bg-bg-surface border border-border-secondary rounded-xl p-6 space-y-4">
        <h3 className="text-sm font-semibold text-text-primary">
          Platform Identity
        </h3>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="space-y-1">
            <span className="text-[10px] text-text-muted uppercase tracking-wider font-semibold">
              Platform Name
            </span>
            <div className="text-xs text-text-secondary">
              {loading ? (
                <div className="h-4 w-48 bg-border-primary/40 rounded animate-pulse" />
              ) : (
                info?.platform ?? 'Enterprise Agent Security Platform'
              )}
            </div>
          </div>

          <div className="space-y-1">
            <span className="text-[10px] text-text-muted uppercase tracking-wider font-semibold">
              Software Version
            </span>
            <div className="text-xs text-text-secondary font-mono">
              {loading ? (
                <div className="h-4 w-16 bg-border-primary/40 rounded animate-pulse" />
              ) : (
                info?.version ?? '0.9.0'
              )}
            </div>
          </div>

          <div className="space-y-1">
            <span className="text-[10px] text-text-muted uppercase tracking-wider font-semibold">
              API Version
            </span>
            <div className="text-xs text-text-secondary font-mono">
              {loading ? (
                <div className="h-4 w-12 bg-border-primary/40 rounded animate-pulse" />
              ) : (
                info?.api_version ?? 'v1'
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
