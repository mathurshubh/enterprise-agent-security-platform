/**
 * main.tsx — Application entry point.
 *
 * REACT CONCEPT: "Entry Point" and "StrictMode"
 * ──────────────────────────────────────────────────────────────────
 * This is the JavaScript equivalent of `if __name__ == "__main__":`
 * in Python.  It's the first code that runs when the browser loads
 * the application.
 *
 * `createRoot` tells React which DOM element to render into.  The
 * `<div id="root">` in index.html is that element.
 *
 * `StrictMode` is a development-only wrapper that helps catch bugs
 * by intentionally double-rendering components and flagging unsafe
 * patterns.  It has zero effect in production builds.
 */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'

/* Import the global stylesheet (Tailwind + theme tokens) */
import './styles/index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
