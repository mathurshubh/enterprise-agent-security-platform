/**
 * NavIcon — Thin SVG icon wrappers for the primary navigation sidebar.
 *
 * All 9 navigation icons are defined here as a single replaceable unit.
 * When a production icon library (e.g. lucide-react) is introduced in a
 * future UI refinement PR, this file is the only location that needs to change.
 *
 * Constraints:
 *   - No external icon library dependency.
 *   - All SVG paths use consistent 16×16 viewBox, 1.5px stroke, currentColor.
 *   - aria-hidden="true" on all icons (labels are provided by parent NavLink).
 *
 * ADR-022 / 09-ui-component-architecture.md: Tier 1 Design System Primitive.
 * Icon library replacement: targeted UI refinement PR (post Phase 1).
 */

const SVG_PROPS = {
  className: 'w-4 h-4 shrink-0',
  viewBox: '0 0 16 16',
  fill: 'none' as const,
  stroke: 'currentColor' as const,
  strokeWidth: 1.5,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true as const,
}

export function IconCommandCenter() {
  return (
    <svg {...SVG_PROPS}>
      <rect x="1" y="1" width="6" height="6" rx="1" />
      <rect x="9" y="1" width="6" height="6" rx="1" />
      <rect x="1" y="9" width="6" height="6" rx="1" />
      <rect x="9" y="9" width="6" height="6" rx="1" />
    </svg>
  )
}

export function IconApprovalQueue() {
  return (
    <svg {...SVG_PROPS}>
      <circle cx="8" cy="8" r="6.5" />
      <path d="M5 8l2 2 4-4" />
    </svg>
  )
}

export function IconSessions() {
  return (
    <svg {...SVG_PROPS}>
      <path d="M1.5 5.5L8 2l6.5 3.5-6.5 3.5L1.5 5.5z" />
      <path d="M1.5 9L8 12.5 14.5 9" />
    </svg>
  )
}

export function IconFindings() {
  return (
    <svg {...SVG_PROPS}>
      <path d="M8 2L1 14h14L8 2z" />
      <path d="M8 6v4" />
      <circle cx="8" cy="12" r="0.5" fill="currentColor" />
    </svg>
  )
}

export function IconAuditTrail() {
  return (
    <svg {...SVG_PROPS}>
      <circle cx="8" cy="8" r="6.5" />
      <path d="M8 4.5V8l2.5 2.5" />
    </svg>
  )
}

export function IconAgents() {
  return (
    <svg {...SVG_PROPS}>
      <circle cx="8" cy="5" r="3" />
      <path d="M1.5 14.5c0-3.5 3-5.5 6.5-5.5s6.5 2 6.5 5.5" />
    </svg>
  )
}

export function IconTools() {
  return (
    <svg {...SVG_PROPS}>
      <path d="M13.5 2.5a3.5 3.5 0 00-4.9 4.9L2.5 13.5a1 1 0 001.4 1.4l6.1-6.1a3.5 3.5 0 004.9-4.9l-2.1 2.1-1.4-1.4 2.1-2.1z" />
    </svg>
  )
}

export function IconDetectionRules() {
  return (
    <svg {...SVG_PROPS}>
      <path d="M8 1.5L1.5 4v4c0 3.5 3 6 6.5 6.5C14.5 14 14.5 8 14.5 8V4L8 1.5z" />
    </svg>
  )
}

export function IconScenarios() {
  return (
    <svg {...SVG_PROPS}>
      <circle cx="8" cy="8" r="6.5" />
      <path d="M6.5 5.5l4 2.5-4 2.5V5.5z" strokeLinejoin="round" />
    </svg>
  )
}
