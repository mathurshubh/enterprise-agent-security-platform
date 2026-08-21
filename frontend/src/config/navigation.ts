/**
 * navigation.ts — Canonical navigation configuration.
 *
 * Single source of truth for all 9 console routes defined in ADR-022 and
 * docs/architecture/enterprise-security-console/04-navigation-architecture.md.
 *
 * Consumed by:
 *   - src/components/layout/Sidebar.tsx  (renders nav items)
 *   - src/layouts/AppLayout.tsx          (resolves page titles for Header)
 *
 * Centralizing the route configuration eliminates drift between Sidebar
 * nav labels and Header page titles. Both surfaces read from this module.
 *
 * Do NOT add authentication guards, redirects, or route permissions here.
 * All security decisions remain deterministic and backend-enforced.
 */

import React from 'react'
import {
  IconCommandCenter,
  IconApprovalQueue,
  IconSessions,
  IconFindings,
  IconAuditTrail,
  IconAgents,
  IconTools,
  IconDetectionRules,
  IconScenarios,
} from '../components/ui/NavIcon'

export interface NavItem {
  /** Human-readable page label (used in Sidebar and Header). */
  label: string
  /** URL path for React Router and NavLink matching. */
  path: string
  /** Icon element — sourced from NavIcon.tsx; replaceable in a single PR. */
  icon: React.ReactNode
  /**
   * When true, the route is a Phase 2+ gated placeholder.
   * The page renders but indicates backend APIs are not yet available.
   * This flag is informational for developers; no routing behavior changes.
   */
  gated?: boolean
}

export interface NavSection {
  /** Section label displayed above the group (MONITOR, INVESTIGATE, GOVERN). */
  section: string
  items: NavItem[]
}

export const NAV_SECTIONS: NavSection[] = [
  {
    section: 'MONITOR',
    items: [
      { label: 'Command Center', path: '/',          icon: React.createElement(IconCommandCenter) },
      { label: 'Approval Queue', path: '/approvals', icon: React.createElement(IconApprovalQueue), gated: true },
    ],
  },
  {
    section: 'INVESTIGATE',
    items: [
      { label: 'Sessions',    path: '/sessions',  icon: React.createElement(IconSessions) },
      { label: 'Findings',    path: '/findings',  icon: React.createElement(IconFindings) },
      { label: 'Audit Trail', path: '/audit',     icon: React.createElement(IconAuditTrail) },
    ],
  },
  {
    section: 'GOVERN',
    items: [
      { label: 'Agents',          path: '/agents',    icon: React.createElement(IconAgents) },
      { label: 'Tools',           path: '/tools',     icon: React.createElement(IconTools) },
      { label: 'Detection Rules', path: '/detection', icon: React.createElement(IconDetectionRules) },
      { label: 'Scenarios',       path: '/scenarios', icon: React.createElement(IconScenarios) },
    ],
  },
]

/**
 * Flat list of all nav items across all sections.
 * Used for title lookup in AppLayout without re-flattening at runtime.
 */
export const ALL_NAV_ITEMS: NavItem[] = NAV_SECTIONS.flatMap((s) => s.items)

/**
 * Resolves a human-readable page title from a URL pathname.
 *
 * Exact match is tried first. Falls back to prefix match for future
 * dynamic routes such as /sessions/:id (Phase 3 Session Workspace).
 * Returns a default fallback if no match is found.
 */
export function resolvePageTitle(pathname: string): string {
  // 1. Exact match
  const exact = ALL_NAV_ITEMS.find((item) => item.path === pathname)
  if (exact) return exact.label

  // 2. Prefix match (longest wins) — supports future dynamic segments
  const prefix = ALL_NAV_ITEMS
    .filter((item) => item.path !== '/' && pathname.startsWith(item.path))
    .sort((a, b) => b.path.length - a.path.length)[0]
  if (prefix) return prefix.label

  return 'Enterprise Security Console'
}
