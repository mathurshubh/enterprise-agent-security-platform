/**
 * ErrorBoundary — React Error Boundary for page-level crash isolation.
 *
 * React Error Boundaries must be implemented as class components.
 * This component wraps the layout <Outlet /> to isolate individual
 * page crashes from bringing down the entire application shell.
 *
 * Behavior:
 *   - Catches synchronous rendering errors thrown by child components.
 *   - Does NOT catch: async errors, event handlers, server errors.
 *   - Renders a structured fallback UI that preserves the sidebar and
 *     header navigation, allowing the user to navigate away.
 *
 * Placement:
 *   Wraps <Outlet /> in AppLayout.tsx. Each page is an independent
 *   error isolation boundary. A crash in /agents does not affect /tools.
 *
 * ADR-022 / 09-ui-component-architecture.md: Tier 1 Layout Shell.
 */

import { Component, type ErrorInfo, type ReactNode } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
  /**
   * Optional custom fallback. If not provided, the built-in structured
   * error UI is rendered.
   */
  fallback?: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Log to console for local debugging. Future PRs may route this to
    // an observability pipeline (e.g. OpenTelemetry) when Phase 4 ships.
    console.error('[ErrorBoundary] Unhandled render error:', error, info.componentStack)
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null })
  }

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="flex flex-col items-center justify-center py-24 px-6 text-center gap-4">
          {/* Error indicator */}
          <div className="w-12 h-12 rounded-full bg-status-error/10 border border-status-error/30 flex items-center justify-center">
            <span className="text-status-error text-xl select-none" aria-hidden="true">!</span>
          </div>

          <div className="space-y-1.5">
            <div className="text-sm font-semibold text-text-primary">
              Page Error
            </div>
            <p className="text-xs text-text-secondary max-w-sm leading-relaxed">
              This page encountered an unexpected error. Other console pages are unaffected.
            </p>
            {this.state.error?.message && (
              <code className="block text-[10px] text-text-muted font-mono mt-2 max-w-md truncate">
                {this.state.error.message}
              </code>
            )}
          </div>

          <button
            onClick={this.handleReset}
            id="error-boundary-retry-btn"
            className="px-4 py-2 text-xs font-medium rounded-lg bg-bg-surface border border-border-secondary text-text-primary hover:border-accent-primary hover:text-accent-primary transition-colors"
          >
            Retry
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
