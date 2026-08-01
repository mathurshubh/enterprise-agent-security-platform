/**
 * QueryProvider — TanStack Query client provider.
 *
 * Wraps the component tree with QueryClientProvider using the application-wide
 * QueryClient singleton defined in src/api/queryClient.ts.
 *
 * QueryClient configuration (staleTime, gcTime, retry, refetchOnWindowFocus,
 * refetchOnReconnect) is documented in src/api/queryClient.ts.
 *
 * DevTools:
 *   ReactQueryDevtools are rendered in development mode only.
 *   They are automatically excluded from production builds via
 *   import.meta.env.DEV (Vite's compile-time environment flag).
 *
 * The QueryClient singleton is exported from src/api/queryClient.ts (not here)
 * to satisfy the react-refresh/only-export-components lint rule which requires
 * files to export only React components for reliable fast-refresh behaviour.
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import type { ReactNode } from 'react'
import { queryClient } from '../api/queryClient'

interface QueryProviderProps {
  children: ReactNode
}

export default function QueryProvider({ children }: QueryProviderProps) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {import.meta.env.DEV && (
        <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-right" />
      )}
    </QueryClientProvider>
  )
}
