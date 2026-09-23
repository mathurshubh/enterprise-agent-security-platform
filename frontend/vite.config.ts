import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { readFileSync } from 'node:fs'
import type { IncomingMessage } from 'node:http'
import type { TLSSocket } from 'node:tls'

const appVersion = readFileSync(new URL('../VERSION', import.meta.url), 'utf-8').trim()

/**
 * Local development JWT for the console's backend requests.
 *
 * Deliberately NOT prefixed with `VITE_`: Vite exposes only `VITE_*` variables to
 * client code through `import.meta.env`, so this value stays inside the Node dev
 * server process and never reaches browser JavaScript or the bundle.
 */
const DEV_API_TOKEN_ENV = 'EASP_DEV_API_TOKEN'

/**
 * Backend origin the dev proxy forwards `/api` requests to.
 *
 * `scripts/dev-start.sh` sets this so the console follows the backend it started, on
 * whichever port. Like the token, it is deliberately not a `VITE_*` variable.
 */
const DEV_API_TARGET_ENV = 'EASP_DEV_API_TARGET'
const DEFAULT_API_TARGET = 'http://127.0.0.1:8000'

// Hostnames that resolve to this machine, as they appear in a URL.
const LOOPBACK_HOSTNAMES = new Set(['localhost', '127.0.0.1', '[::1]', '::1'])

/**
 * Resolve the backend origin, refusing any target off this machine.
 *
 * The proxy attaches a credential to everything it forwards, so a target beyond
 * loopback would send development credentials to another host.
 */
function resolveApiTarget(): string {
  const configured = process.env[DEV_API_TARGET_ENV]?.trim()
  if (!configured) {
    return DEFAULT_API_TARGET
  }

  let hostname: string
  try {
    hostname = new URL(configured).hostname
  } catch {
    throw new Error(`${DEV_API_TARGET_ENV} is not a valid URL: ${configured}`)
  }

  if (!LOOPBACK_HOSTNAMES.has(hostname)) {
    throw new Error(
      `${DEV_API_TARGET_ENV} must point at this machine, but is ${configured}. ` +
        'The dev proxy attaches local development credentials to every request it forwards.',
    )
  }

  return configured
}

// `server.host` values that keep the dev server on loopback. Vite treats both an
// unset host and `false` as localhost.
const LOOPBACK_HOSTS = new Set<string | boolean | undefined>([
  undefined,
  false,
  'localhost',
  '127.0.0.1',
  '::1',
  '[::1]',
])

// `none` is a user-initiated navigation; absent means a non-browser client or a
// browser that does not send the header.
const TRUSTED_FETCH_SITES = new Set([undefined, 'same-origin', 'none'])

/**
 * CSRF defence for the credential the dev proxy attaches.
 *
 * Browsers never attach a bearer token on their own, but the proxy attaches one to
 * every request it forwards. Without this check, any web page open in the developer's
 * browser could send credentialed requests to the backend through the proxy.
 *
 * Both conditions must hold. Browsers set these headers; page scripts cannot.
 * - `Sec-Fetch-Site` is same-origin, none, or absent.
 * - `Origin`, when present, is the origin the request was sent to. This also covers
 *   browsers that do not send `Sec-Fetch-Site`. Opaque origins (`null`) never match.
 *   The Host header is safe to compare against because Vite's host validation, which
 *   runs before the proxy, admits only localhost and IP addresses by default.
 */
function isTrustedLocalRequest(req: IncomingMessage): boolean {
  if (!TRUSTED_FETCH_SITES.has(req.headers['sec-fetch-site'] as string | undefined)) {
    return false
  }

  const { origin, host } = req.headers
  if (origin === undefined) {
    return true
  }

  const scheme = (req.socket as TLSSocket).encrypted ? 'https' : 'http'
  return origin === `${scheme}://${host}`
}

/**
 * LOCAL DEVELOPMENT ONLY — attaches a JWT to proxied console API requests.
 *
 * The backend requires a JWT on every /api route and the browser client holds no
 * credentials. When `EASP_DEV_API_TOKEN` is set while running the `vite` dev server,
 * the /api proxy adds `Authorization: Bearer <token>` to trusted local-origin requests
 * on their way to the backend. The browser never sees the token.
 *
 * Guardrails:
 * - Active only for `vite` dev serving: never for `vite build`, and never for
 *   `vite preview`, which otherwise reuses the dev server proxy.
 * - Inactive when the variable is absent or blank; the proxy is left unchanged.
 * - Credentials only trusted local-origin requests (see `isTrustedLocalRequest`).
 * - Refuses to start when the dev server is explicitly exposed beyond loopback or
 *   accepts any Host header, because every request reaching the proxy would act as
 *   the token's principal.
 * - The token lives in a closure rather than a config value, so it does not appear
 *   in resolved config output. It is never logged or included in errors.
 *
 * This is not a production authentication mechanism.
 */
function localDevApiAuth(): Plugin {
  let injectingToken = false

  return {
    name: 'easp-local-dev-api-auth',

    config(_config, { command, isPreview }) {
      const token = process.env[DEV_API_TOKEN_ENV]?.trim()
      if (!token || command !== 'serve' || isPreview) {
        return
      }

      injectingToken = true

      return {
        server: {
          proxy: {
            '/api': {
              configure: (proxy) => {
                proxy.on('proxyReq', (proxyReq, req) => {
                  if (isTrustedLocalRequest(req)) {
                    proxyReq.setHeader('Authorization', `Bearer ${token}`)
                  }
                })
              },
            },
          },
        },
      }
    },

    configResolved(resolved) {
      if (!injectingToken) {
        return
      }

      const { host, allowedHosts } = resolved.server
      if (!LOOPBACK_HOSTS.has(host) || allowedHosts === true) {
        throw new Error(
          `${DEV_API_TOKEN_ENV} is set, but the dev server is configured to listen beyond ` +
            'loopback or to accept any Host header. Refusing to proxy local development ' +
            `credentials. Unset ${DEV_API_TOKEN_ENV} or keep the dev server on localhost.`,
        )
      }
    },
  }
}

// Enterprise Security Console — Vite Configuration
// ADR-009: Vite serves as the build tooling and development server.
// Configures a dev server proxy to forward all API calls to the FastAPI backend.
export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
  },
  plugins: [
    react(),
    tailwindcss(),
    localDevApiAuth(),
  ],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: resolveApiTarget(),
        changeOrigin: true,
      },
      '/version': {
        target: resolveApiTarget(),
        changeOrigin: true,
      },
      '/health': {
        target: resolveApiTarget(),
        changeOrigin: true,
      },
    },
  },
})
