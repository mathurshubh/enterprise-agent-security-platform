// Tests for the LOCAL DEVELOPMENT ONLY console authentication proxy in vite.config.ts.
//
// Uses Node's built-in test runner with Vite's own resolveConfig and build APIs, so the
// real configuration is exercised without adding a test framework. No real JWT or
// signing secret is involved: the token is an inert sentinel string.

import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { afterEach, describe, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { inspect } from 'node:util'

import { build, resolveConfig } from 'vite'

const FRONTEND_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const CONFIG_FILE = path.join(FRONTEND_ROOT, 'vite.config.ts')
const TOKEN_ENV = 'EASP_DEV_API_TOKEN'
const TARGET_ENV = 'EASP_DEV_API_TARGET'
const SENTINEL = 'sentinel-dev-token-not-a-real-jwt-6f1d2c'
const BACKEND_TARGET = 'http://127.0.0.1:8000'
const CREDENTIAL = { Authorization: `Bearer ${SENTINEL}` }

// A request the console itself makes: same-origin fetch to the dev server.
const CONSOLE_REQUEST = {
  headers: {
    host: 'localhost:3000',
    origin: 'http://localhost:3000',
    'sec-fetch-site': 'same-origin',
  },
}

const originalToken = process.env[TOKEN_ENV]

function setToken(value) {
  if (value === undefined) {
    delete process.env[TOKEN_ENV]
  } else {
    process.env[TOKEN_ENV] = value
  }
}

const originalTarget = process.env[TARGET_ENV]

function setTarget(value) {
  if (value === undefined) {
    delete process.env[TARGET_ENV]
  } else {
    process.env[TARGET_ENV] = value
  }
}

afterEach(() => {
  setToken(originalToken)
  setTarget(originalTarget)
})

function resolveFor({ command = 'serve', isPreview = false, server } = {}) {
  return resolveConfig(
    {
      configFile: CONFIG_FILE,
      root: FRONTEND_ROOT,
      logLevel: 'silent',
      ...(server ? { server } : {}),
    },
    command,
    'development',
    'development',
    isPreview,
  )
}

// Run a proxy's configure hook against a stand-in proxy, emit one outgoing request the
// way Vite's proxy middleware does, and return the headers the hook set on it.
function headersSentBy(proxyOptions, { headers, encrypted = false } = CONSOLE_REQUEST) {
  const sent = {}
  if (typeof proxyOptions?.configure !== 'function') {
    return sent
  }

  const proxy = new EventEmitter()
  proxyOptions.configure(proxy, proxyOptions)
  proxy.emit(
    'proxyReq',
    { setHeader: (name, value) => { sent[name] = value } },
    { headers, socket: { encrypted } },
    {},
    proxyOptions,
  )
  return sent
}

// The credential is neither embedded in resolved configuration (client environment,
// define, static proxy headers) nor attached by any proxy to a trusted console request.
function assertCarriesNoCredential(config) {
  assert.ok(!JSON.stringify(config.env).includes(SENTINEL), 'credential in import.meta.env')
  assert.ok(!JSON.stringify(config.define ?? {}).includes(SENTINEL), 'credential in define')
  assert.ok(!inspect(config, { depth: 8 }).includes(SENTINEL), 'credential in resolved config')

  for (const [name, proxies] of [['server', config.server.proxy], ['preview', config.preview.proxy]]) {
    for (const [context, options] of Object.entries(proxies ?? {})) {
      assert.deepEqual(headersSentBy(options), {}, `${name} proxy '${context}' attaches a credential`)
    }
  }
}

async function listFiles(directory) {
  const entries = await readdir(directory, { recursive: true, withFileTypes: true })
  return entries
    .filter((entry) => entry.isFile())
    .map((entry) => path.join(entry.parentPath, entry.name))
}

describe('local development console authentication proxy', () => {
  describe('token injection', () => {
    test('adds a bearer Authorization header to console requests during dev serving', async () => {
      setToken(SENTINEL)

      const apiProxy = (await resolveFor()).server.proxy['/api']

      assert.equal(apiProxy.target, BACKEND_TARGET)
      assert.equal(apiProxy.changeOrigin, true)
      assert.deepEqual(headersSentBy(apiProxy), CREDENTIAL)
    })

    test('leaves the existing proxy unchanged and uncredentialed when the token is absent', async () => {
      setToken(undefined)

      const config = await resolveFor()

      assert.equal(config.server.proxy['/api'].target, BACKEND_TARGET)
      assert.equal(config.server.proxy['/api'].changeOrigin, true)
      assertCarriesNoCredential(config)
    })

    test('treats a blank token as absent', async () => {
      setToken('   ')

      assertCarriesNoCredential(await resolveFor())
    })
  })

  describe('backend target', () => {
    test('defaults to the loopback backend', async () => {
      setToken(SENTINEL)
      setTarget(undefined)

      const config = await resolveFor()

      assert.equal(config.server.proxy['/api'].target, BACKEND_TARGET)
    })

    test('follows the backend the developer started', async () => {
      setToken(SENTINEL)
      setTarget('http://127.0.0.1:8010')

      const config = await resolveFor()

      assert.equal(config.server.proxy['/api'].target, 'http://127.0.0.1:8010')
      assert.deepEqual(headersSentBy(config.server.proxy['/api']), CREDENTIAL)
    })

    test('refuses to forward credentials off this machine', async () => {
      setToken(SENTINEL)

      for (const target of ['http://backend.example:8000', 'https://10.0.0.5:8000']) {
        await assert.rejects(
          (setTarget(target), resolveFor()),
          (error) => {
            assert.match(error.message, /must point at this machine/)
            assert.ok(!error.message.includes(SENTINEL))
            return true
          },
          target,
        )
      }
    })

    test('refuses a malformed target', async () => {
      setToken(SENTINEL)
      setTarget('not-a-url')

      await assert.rejects(resolveFor(), /is not a valid URL/)
    })
  })

  describe('CSRF protection', () => {
    test('credentials requests whose Origin matches the dev server, on any port or scheme', async () => {
      setToken(SENTINEL)
      const apiProxy = (await resolveFor()).server.proxy['/api']

      const sameOrigin = [
        { headers: { host: 'localhost:5174', origin: 'http://localhost:5174', 'sec-fetch-site': 'same-origin' } },
        { headers: { host: '127.0.0.1:3000', origin: 'http://127.0.0.1:3000', 'sec-fetch-site': 'same-origin' } },
        { headers: { host: 'localhost:3000', origin: 'https://localhost:3000', 'sec-fetch-site': 'same-origin' }, encrypted: true },
        // A browser that sends Origin but not Sec-Fetch-Site.
        { headers: { host: 'localhost:3000', origin: 'http://localhost:3000' } },
      ]

      for (const request of sameOrigin) {
        assert.deepEqual(headersSentBy(apiProxy, request), CREDENTIAL, JSON.stringify(request))
      }
    })

    test('does not credential requests whose Origin differs from the dev server', async () => {
      setToken(SENTINEL)
      const apiProxy = (await resolveFor()).server.proxy['/api']

      const foreignOrigins = [
        'https://attacker.example',
        'http://127.0.0.1:3002', // another local site
        'http://localhost:3001', // another local port
        'https://localhost:3000', // scheme differs from the plain-HTTP dev server
        'null', // opaque origin: sandboxed frame, data: URL
      ]

      for (const origin of foreignOrigins) {
        // Without Sec-Fetch-Site, as from a browser that does not send it.
        const withoutFetchSite = { headers: { host: 'localhost:3000', origin } }
        assert.deepEqual(headersSentBy(apiProxy, withoutFetchSite), {}, origin)

        // With a trusted-looking Sec-Fetch-Site, the Origin check still applies.
        const withFetchSite = { headers: { host: 'localhost:3000', origin, 'sec-fetch-site': 'same-origin' } }
        assert.deepEqual(headersSentBy(apiProxy, withFetchSite), {}, `${origin} with same-origin fetch site`)
      }
    })

    test('keeps the Sec-Fetch-Site behaviour when Origin is absent', async () => {
      setToken(SENTINEL)
      const apiProxy = (await resolveFor()).server.proxy['/api']

      for (const site of ['same-origin', 'none', undefined]) {
        const headers = { host: 'localhost:3000', ...(site ? { 'sec-fetch-site': site } : {}) }
        assert.deepEqual(headersSentBy(apiProxy, { headers }), CREDENTIAL, String(site))
      }
    })

    test('does not credential cross-site or same-site requests, even with a matching Origin', async () => {
      setToken(SENTINEL)
      const apiProxy = (await resolveFor()).server.proxy['/api']

      for (const site of ['cross-site', 'same-site']) {
        const withoutOrigin = { headers: { host: 'localhost:3000', 'sec-fetch-site': site } }
        const withOrigin = { headers: { ...withoutOrigin.headers, origin: 'http://localhost:3000' } }

        assert.deepEqual(headersSentBy(apiProxy, withoutOrigin), {}, site)
        assert.deepEqual(headersSentBy(apiProxy, withOrigin), {}, `${site} with matching Origin`)
      }
    })
  })

  describe('network exposure', () => {
    for (const server of [{ host: true }, { host: '0.0.0.0' }, { host: '192.168.1.20' }, { allowedHosts: true }]) {
      test(`refuses to start with a token for ${JSON.stringify(server)}`, async () => {
        setToken(SENTINEL)

        await assert.rejects(resolveFor({ server }), (error) => {
          assert.match(error.message, /Refusing to proxy local development credentials/)
          assert.ok(!error.message.includes(SENTINEL), 'error message must not contain the token')
          return true
        })
      })
    }

    for (const host of [false, 'localhost', '127.0.0.1', '::1', '[::1]']) {
      test(`allows the loopback host ${JSON.stringify(host)}`, async () => {
        setToken(SENTINEL)

        const config = await resolveFor({ server: { host } })

        assert.deepEqual(headersSentBy(config.server.proxy['/api']), CREDENTIAL)
      })
    }

    test('allows a specific allowedHosts list', async () => {
      setToken(SENTINEL)

      const config = await resolveFor({ server: { allowedHosts: ['.example.test'] } })

      assert.deepEqual(headersSentBy(config.server.proxy['/api']), CREDENTIAL)
    })

    test('does not restrict the host when no token is set', async () => {
      setToken(undefined)

      const config = await resolveFor({ server: { host: true } })

      assert.equal(config.server.host, true)
    })
  })

  describe('production boundary', () => {
    test('vite preview carries no credential', async () => {
      setToken(SENTINEL)

      assertCarriesNoCredential(await resolveFor({ isPreview: true }))
    })

    test('vite build configuration carries no credential', async () => {
      setToken(SENTINEL)

      assertCarriesNoCredential(await resolveFor({ command: 'build' }))
    })

    test('dev serving keeps the token out of the client environment and resolved config output', async () => {
      setToken(SENTINEL)

      const config = await resolveFor()
      const prefixes = [config.envPrefix].flat()

      assert.ok(
        prefixes.every((prefix) => !TOKEN_ENV.startsWith(prefix)),
        `${TOKEN_ENV} must not match a client-exposed env prefix (${prefixes.join(', ')})`,
      )
      assert.ok(!JSON.stringify(config.env).includes(SENTINEL), 'token exposed through import.meta.env')
      assert.ok(!JSON.stringify(config.define ?? {}).includes(SENTINEL), 'token exposed through define')
      assert.ok(!inspect(config, { depth: 8 }).includes(SENTINEL), 'token visible in resolved config output')
    })

    test('the production bundle never contains the token', { timeout: 120_000 }, async () => {
      setToken(SENTINEL)
      const outDir = await mkdtemp(path.join(tmpdir(), 'easp-console-build-'))

      try {
        await build({
          configFile: CONFIG_FILE,
          root: FRONTEND_ROOT,
          logLevel: 'silent',
          build: { outDir, emptyOutDir: true },
        })

        const files = await listFiles(outDir)
        assert.ok(files.length > 0, 'build produced no output')

        for (const file of files) {
          const content = await readFile(file, 'utf-8')
          assert.ok(!content.includes(SENTINEL), `token found in build output: ${path.basename(file)}`)
        }
      } finally {
        await rm(outDir, { recursive: true, force: true })
      }
    })
  })
})
