/**
 * PageHeader — Reusable page title and subtitle header.
 *
 * Provides a consistent top-of-page presentation across all console pages.
 * Replaces the duplicated <h2>/<p> pattern found in every existing page.
 *
 * An optional `action` slot supports future use cases such as a refresh
 * button or export trigger without altering the base component.
 *
 * ADR-022 / 09-ui-component-architecture.md: Tier 1 Design System Primitive.
 */

interface PageHeaderProps {
  title: string
  description?: string
  action?: React.ReactNode
}

export default function PageHeader({ title, description, action }: PageHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h2 className="text-xl font-bold text-text-primary">
          {title}
        </h2>
        {description && (
          <p className="mt-1 text-sm text-text-secondary leading-relaxed">
            {description}
          </p>
        )}
      </div>
      {action && (
        <div className="shrink-0 pt-0.5">
          {action}
        </div>
      )}
    </div>
  )
}
