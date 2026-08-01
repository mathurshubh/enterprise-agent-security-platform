/**
 * main.tsx — Application entry point.
 *
 * Bootstraps the React application with all required top-level providers:
 *   1. QueryProvider  — TanStack Query server-state cache (PR #70)
 *   2. StrictMode     — Development-mode double-render safety checks
 *
 * Provider ordering is intentional. QueryProvider wraps App so that any
 * component in the tree (including future context providers) may call
 * TanStack Query hooks without provider ordering issues.
 *
 * ADR-009 / ADR-022 Compliance:
 *   - No authentication state or security logic is initialized here.
 *   - No authorization context is established at the entry point.
 *   - The backend remains the sole security enforcement point.
 */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import QueryProvider from './providers/QueryProvider'

/* Import the global stylesheet (Tailwind + theme tokens) */
import './styles/index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryProvider>
      <App />
    </QueryProvider>
  </StrictMode>,
)
