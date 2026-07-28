/**
 * Sidebar — Primary navigation for the Enterprise Security Console.
 *
 * Implements the 3-section, 9-route workflow-centric navigation architecture
 * defined in ADR-022 and docs/architecture/enterprise-security-console/04-navigation-architecture.md.
 *
 * Navigation sections:
 *   MONITOR     — Command Center, Approval Queue
 *   INVESTIGATE — Sessions, Findings, Audit Trail
 *   GOVERN      — Agents, Tools, Detection Rules, Scenarios
 *
 * Route configuration is sourced from src/config/navigation.ts — the single
 * source of truth for all route labels, paths, and icons. Both Sidebar and
 * AppLayout read from that module, eliminating label drift.
 *
 * Icons are sourced from src/components/ui/NavIcon.tsx — a dedicated
 * replaceable unit. When a production icon library is introduced in a future
 * UI refinement PR, only NavIcon.tsx needs to change.
 *
 * Migration from v0.11.0 (flat list):
 *   - All existing URL paths are preserved without breakage.
 *   - /sessions and /scenarios are promoted from orphaned routes to sidebar entries.
 *   - /approvals and /findings are added as new Phase 2-gated routes.
 */

import { NavLink } from 'react-router-dom'
import { NAV_SECTIONS } from '../../config/navigation'

export default function Sidebar() {
  return (
    <aside className="fixed top-0 left-0 h-screen w-60 bg-bg-secondary border-r border-border-primary flex flex-col z-30">

      {/* ── Brand ───────────────────────────────────────────────────── */}
      <div className="px-5 py-5 border-b border-border-primary shrink-0">
        <div className="text-[10px] font-semibold tracking-widest uppercase text-accent-primary">
          Enterprise
        </div>
        <div className="text-sm font-bold text-text-primary mt-0.5">
          Security Console
        </div>
      </div>

      {/* ── Navigation Sections ──────────────────────────────────────── */}
      <nav className="flex-1 px-3 py-3 overflow-y-auto" aria-label="Primary navigation">
        {NAV_SECTIONS.map((group, idx) => (
          <div key={group.section} className={idx > 0 ? 'mt-5' : ''}>

            {/* Section Label */}
            <div className="px-3 pb-1.5 text-[10px] font-semibold tracking-widest uppercase text-text-muted select-none">
              {group.section}
            </div>

            {/* Section Items */}
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.path === '/'}
                  aria-label={item.label}
                  className={({ isActive }) =>
                    [
                      'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors duration-150',
                      isActive
                        ? 'bg-accent-primary/15 text-accent-primary'
                        : 'text-text-secondary hover:bg-bg-surface-hover hover:text-text-primary',
                    ].join(' ')
                  }
                >
                  {item.icon}
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* ── Footer ──────────────────────────────────────────────────── */}
      <div className="px-5 py-4 border-t border-border-primary shrink-0">
        <div className="text-xs text-text-muted">Platform v0.12.0</div>
      </div>

    </aside>
  )
}
