/**
 * Installability guards for the PWA.
 *
 * A manifest with a typo, a missing icon size, or an icon path that 404s fails
 * silently: the browser simply never offers "Install app" and nothing in the UI
 * says why. These assert against the real files, pulled in through Vite's own
 * `?raw` and `import.meta.glob` so no Node type packages are needed.
 */
import { describe, it, expect } from 'vitest'
import manifestRaw from '../public/manifest.webmanifest?raw'
import swRaw from '../public/sw.js?raw'
import indexRaw from '../index.html?raw'

const manifest = JSON.parse(manifestRaw)

// Keys are repo-relative paths of every PNG actually present in public/.
const publicPngs = new Set(
  Object.keys(import.meta.glob('../public/*.png')).map(p => p.replace('../public/', '')),
)

describe('web app manifest', () => {
  it('declares the fields a browser requires before offering installation', () => {
    expect(manifest.name).toBeTruthy()
    expect(manifest.short_name).toBeTruthy()
    expect(manifest.start_url).toBe('/')
    expect(manifest.display).toBe('standalone')
    expect(manifest.background_color).toMatch(/^#[0-9a-fA-F]{6}$/)
    expect(manifest.theme_color).toMatch(/^#[0-9a-fA-F]{6}$/)
  })

  it('ships both icon sizes Chrome and Android require', () => {
    const sizes = (manifest.icons ?? []).map((i: { sizes: string }) => i.sizes)
    expect(sizes).toContain('192x192')
    expect(sizes).toContain('512x512')
  })

  it('includes a maskable icon so Android does not letterbox it', () => {
    const maskable = (manifest.icons ?? []).filter((i: { purpose?: string }) =>
      (i.purpose ?? '').split(' ').includes('maskable'))
    expect(maskable.length).toBeGreaterThan(0)
  })

  it('points every icon at a file that actually exists', () => {
    for (const icon of manifest.icons ?? []) {
      const name = icon.src.replace(/^\//, '')
      expect(publicPngs.has(name), `missing icon file: ${icon.src}`).toBe(true)
    }
  })
})

describe('index.html', () => {
  it('links the manifest, without which the browser never reads it', () => {
    expect(indexRaw).toMatch(/<link[^>]+rel="manifest"[^>]+href="\/manifest\.webmanifest"/)
  })

  it('sets a theme colour matching the manifest', () => {
    expect(indexRaw).toContain(`<meta name="theme-color" content="${manifest.theme_color}"`)
  })

  it('serves its favicon from public/ so the production build includes it', () => {
    const match = indexRaw.match(/<link rel="icon"[^>]+href="([^"]+)"/)
    expect(match).toBeTruthy()
    expect(publicPngs.has(match![1].replace(/^\//, ''))).toBe(true)
  })
})

describe('service worker', () => {
  it('has a fetch handler, which Chrome requires for installability', () => {
    expect(swRaw).toMatch(/addEventListener\(\s*['"]fetch['"]/)
  })

  it('is network-first for navigations so a deploy is never served stale HTML', () => {
    expect(swRaw).toMatch(/navigate/)
  })

  it('never caches API responses, which are per-user and RLS-filtered', () => {
    expect(swRaw).toMatch(/\/api\//)
  })
})
