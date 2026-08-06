/**
 * ToolTable — List of registered capability tools.
 *
 * Renders the table view for registered tools directly returned by the backend API.
 * Displays only fields that actually exist in the backend DTO:
 * Tool ID, Tool Name, Description, and Version.
 *
 * Feature Folder Pattern:
 *   Located under `pages/Tools/components/` as it is feature-specific.
 */

import type { Tool } from '../../../types/tool'

export type SortField = 'id' | 'name' | 'description' | 'version'
export type SortDirection = 'asc' | 'desc'

interface ToolTableProps {
  tools: Tool[]
  loading: boolean
  sortField: SortField | null
  sortDirection: SortDirection
  onSort: (field: SortField) => void
}

export default function ToolTable({
  tools,
  loading,
  sortField,
  sortDirection,
  onSort,
}: ToolTableProps) {
  if (loading) {
    return (
      <div className="divide-y divide-border-secondary">
        <div className="grid grid-cols-4 gap-4 px-6 py-4 bg-bg-secondary text-xs font-semibold text-text-muted uppercase">
          <span>Tool ID</span>
          <span>Tool Name</span>
          <span>Description</span>
          <span>Version</span>
        </div>
        {[1, 2, 3].map((n) => (
          <div key={n} className="grid grid-cols-4 gap-4 px-6 py-4 items-center">
            <div className="h-4 w-24 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-32 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-48 bg-border-primary/40 rounded animate-pulse" />
            <div className="h-4 w-16 bg-border-primary/40 rounded animate-pulse" />
          </div>
        ))}
      </div>
    )
  }

  if (tools.length === 0) {
    return (
      <div className="px-6 py-16 text-center space-y-2 bg-bg-surface">
        <h3 className="text-sm font-bold text-text-primary">
          No tools registered.
        </h3>
        <p className="text-xs text-text-secondary max-w-sm mx-auto">
          No registered tools were returned by the Management API.
        </p>
      </div>
    )
  }

  const renderSortIndicator = (field: SortField) => {
    if (sortField !== field) return <span className="text-text-muted/40 ml-1">↕</span>
    return <span className="text-accent-primary ml-1">{sortDirection === 'asc' ? '▲' : '▼'}</span>
  }

  return (
    <div className="overflow-x-auto w-full">
      <table className="w-full text-left border-collapse min-w-[650px]">
        <thead>
          <tr className="bg-bg-secondary border-b border-border-secondary text-xs font-semibold text-text-muted uppercase tracking-wider select-none">
            <th className="px-6 py-4 cursor-pointer hover:text-text-primary transition-colors" onClick={() => onSort('id')}>
              <div className="flex items-center">
                Tool ID {renderSortIndicator('id')}
              </div>
            </th>

            <th className="px-6 py-4 cursor-pointer hover:text-text-primary transition-colors" onClick={() => onSort('name')}>
              <div className="flex items-center">
                Tool Name {renderSortIndicator('name')}
              </div>
            </th>

            <th className="px-6 py-4 cursor-pointer hover:text-text-primary transition-colors" onClick={() => onSort('description')}>
              <div className="flex items-center">
                Description {renderSortIndicator('description')}
              </div>
            </th>

            <th className="px-6 py-4 cursor-pointer hover:text-text-primary transition-colors" onClick={() => onSort('version')}>
              <div className="flex items-center">
                Version {renderSortIndicator('version')}
              </div>
            </th>

          </tr>
        </thead>
        <tbody className="divide-y divide-border-secondary text-xs">
          {tools.map((tool) => (
            <tr key={tool.id} className="hover:bg-bg-surface-hover/30 transition-colors">
              
              <td className="px-6 py-4 font-mono text-[11px] text-text-muted">
                {tool.id}
              </td>

              <td className="px-6 py-4 font-semibold text-text-primary">
                {tool.name}
              </td>

              <td className="px-6 py-4 text-text-secondary max-w-md truncate" title={tool.description}>
                {tool.description}
              </td>

              <td className="px-6 py-4 text-text-secondary font-mono">
                {tool.version}
              </td>

            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
