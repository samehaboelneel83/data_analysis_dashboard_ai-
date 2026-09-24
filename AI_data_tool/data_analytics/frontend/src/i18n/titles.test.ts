import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { messageForPath } from './index'

/**
 * Every page inside the app shell must name itself in the top bar.
 *
 * `messageForPath` falls back to "Home" for a path it does not know, and a
 * page that calls itself Home reads as if the navigation had failed -- which is
 * what Custom Connectors and the connection-rules page were doing. That fallback
 * is right for the unknown, but a route the app itself declares is not unknown,
 * so this reads the router and holds every route to having a title.
 *
 * It parses App.tsx rather than importing it: the routes are the source of
 * truth, and a new page that forgets its title should fail here on the day it
 * is added, not after someone notices the bar in a QA pass.
 */
const APP = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../App.tsx'), 'utf8')

/** Routes rendered OUTSIDE <Layout/>, so they have no top bar to title. */
const CHROMELESS = ['/login', '/sso/callback', '/shared/:token', '/embed']

const routePaths = (): string[] => {
  const out: string[] = []
  const re = /<Route\s+path="([^"]+)"([^>]*)>/g
  for (let m = re.exec(APP); m; m = re.exec(APP)) {
    const [, path, rest] = m
    if (rest.includes('<Navigate')) continue   // a redirect renders no page
    if (path === '/') continue                 // the shell itself; index is Home
    const abs = path.startsWith('/') ? path : '/' + path
    if (CHROMELESS.includes(abs)) continue
    out.push(abs)
  }
  return out
}

// A concrete URL for a path pattern, since messageForPath matches on URLs.
const sample = (p: string) => p.replace(/:[^/]+/g, '1')

describe('every routed page has a top-bar title', () => {
  it('found the routes', () => {
    expect(routePaths().length).toBeGreaterThan(15)
  })

  it.each(routePaths())('%s does not fall back to Home', p => {
    expect(messageForPath(sample(p))).not.toBe('nav.home')
  })

  it('still falls back to Home for a path the app does not have', () => {
    expect(messageForPath('/not/a/page')).toBe('nav.home')
  })
})
