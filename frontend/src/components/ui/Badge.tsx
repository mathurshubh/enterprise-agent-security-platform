/**
 * Badge — Standardized status pill component.
 *
 * Renders semantic status badges for Agent Status, Risk Level,
 * Audit Decisions, Enforcement Actions, and Threat Categories.
 *
 * Variants map to the OKLCH design tokens defined in src/styles/index.css:
 *   active  → --color-status-active  (green)
 *   warning → --color-status-warning (amber)
 *   error   → --color-status-error   (red)
 *   info    → --color-accent-primary (blue)
 *   muted   → --color-text-muted     (grey)
 *
 * ADR-022 / 09-ui-component-architecture.md: Tier 1 Design System Primitive.
 */

type BadgeVariant = 'active' | 'warning' | 'error' | 'info' | 'muted'

interface BadgeProps {
  label: string
  variant?: BadgeVariant
  className?: string
}

const variantStyles: Record<BadgeVariant, string> = {
  active:  'bg-status-active/15  text-status-active  border-status-active/30',
  warning: 'bg-status-warning/15 text-status-warning border-status-warning/30',
  error:   'bg-status-error/15   text-status-error   border-status-error/30',
  info:    'bg-accent-primary/15 text-accent-primary border-accent-primary/30',
  muted:   'bg-bg-surface        text-text-muted     border-border-secondary',
}

export default function Badge({ label, variant = 'muted', className = '' }: BadgeProps) {
  return (
    <span
      className={[
        'inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold',
        'uppercase tracking-wider border',
        variantStyles[variant],
        className,
      ].join(' ')}
    >
      {label}
    </span>
  )
}
