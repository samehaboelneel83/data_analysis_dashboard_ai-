/*
 * Minimal service worker. Its job is installability plus a usable offline shell —
 * not aggressive caching.
 *
 * Two rules matter here and are deliberate:
 *
 *  1. Nothing under /api/ is ever cached. Responses are per-user and row-level-
 *     security filtered, so a cached response could be replayed to a different
 *     user in the same browser profile after a logout/login. Those requests are
 *     passed straight through and never touched.
 *
 *  2. Navigations are network-first. A cache-first shell would keep serving the
 *     previous deploy's index.html after a release, which then loads hashed asset
 *     names that no longer exist — a blank page that only a hard refresh fixes.
 *     The cached copy is a fallback for genuine offline only.
 */
const VERSION = 'v1'
const SHELL = `datalytics-shell-${VERSION}`
const ASSETS = `datalytics-assets-${VERSION}`

const SHELL_URL = '/index.html'

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(SHELL).then(c => c.addAll([SHELL_URL, '/manifest.webmanifest'])).catch(() => {})
  )
  self.skipWaiting()
})

self.addEventListener('activate', event => {
  // Drop caches from older versions so a deploy cannot leave a mixed set behind.
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== SHELL && k !== ASSETS).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', event => {
  const { request } = event
  const url = new URL(request.url)

  // Never touch API traffic, cross-origin requests, or non-GET methods.
  if (request.method !== 'GET') return
  if (url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api/')) return

  // Navigations: network first, cached shell only as an offline fallback.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(response => {
          caches.open(SHELL).then(c => c.put(SHELL_URL, response.clone())).catch(() => {})
          return response
        })
        .catch(() => caches.match(SHELL_URL).then(hit => hit ?? Response.error()))
    )
    return
  }

  // Build output is content-hashed, so a hit is always valid for that exact URL.
  event.respondWith(
    caches.match(request).then(hit => hit ?? fetch(request).then(response => {
      if (response.ok && response.type === 'basic') {
        const copy = response.clone()
        caches.open(ASSETS).then(c => c.put(request, copy)).catch(() => {})
      }
      return response
    }))
  )
})
