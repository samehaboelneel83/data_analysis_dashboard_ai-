import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { NAVIGATION, visibleSections, type NavPermission } from './navigation'

/**
 * The rail's permission for a destination must match the ROUTE GUARD that
 * actually enforces it.
 *
 * Two failure directions, both real: a rail entry stricter than its guard hides
 * a page the user may open; a rail entry looser than its guard advertises one
 * the router will refuse -- the dead-control defect, with a 403 at the end of
 * it. Since navigation.ts and App.tsx are two statements of the same fact, this
 * reads both and asserts they agree, the way test_frontend_constant_mirrors.py
 * pins the backend/frontend constant pairs.
 */

const APP = fs.readFileSync(path.join(__dirname, '..', 'App.tsx'), 'utf8')

/** Which guard block a given route path sits inside, read from App.tsx. */
function guardFor(routePath: string): NavPermission {
  // Routes are declared relative to the "/" layout route: "/reports" -> "reports".
  const rel = routePath === '/' ? '' : routePath.replace(/^\//, '')
  const marker = rel === ''
    ? '<Route index'
    : `<Route path="${rel}"`
  const at = APP.indexOf(marker)
  expect(at, `route not declared in App.tsx: ${routePath}`).toBeGreaterThan(-1)

  const before = APP.slice(0, at)
  // The nearest preceding guard opener that has not been closed before `at`.
  const lastAdmin = before.lastIndexOf('<RequireAdmin />')
  const lastSuper = before.lastIndexOf('<RequireSuperAdmin />')
  const lastClose = before.lastIndexOf('</Route>')
  if (lastSuper > lastAdmin && lastSuper > lastClose) return 'super_admin'
  if (lastAdmin > lastClose) return 'org_admin'
  return 'member'
}

const allItems = NAVIGATION.flatMap(s => s.items)

describe('the rail agrees with the router', () => {
  it.each(allItems.map(i => [i.label, i.to] as const))(
    '%s (%s) is gated exactly as its route is',
    (_label, to) => {
      const item = allItems.find(i => i.to === to)!
      expect(item.permission).toBe(guardFor(to))
    },
  )

  it('every navigation route exists in App.tsx', () => {
    // Guard-the-guard: if the parser above silently matched nothing, the
    // per-item assertions would all compare 'member' to 'member' and pass.
    expect(allItems.length).toBeGreaterThanOrEqual(15)
    for (const item of allItems) {
      const rel = item.to === '/' ? '' : item.to.replace(/^\//, '')
      const marker = rel === '' ? '<Route index' : `<Route path="${rel}"`
      expect(APP.includes(marker), item.to).toBe(true)
    }
  })

  it('finds both guard kinds in App.tsx', () => {
    // Proves the parser can distinguish them at all.
    expect(APP).toContain('<RequireAdmin />')
    expect(APP).toContain('<RequireSuperAdmin />')
    expect(allItems.some(i => i.permission === 'org_admin')).toBe(true)
    expect(allItems.some(i => i.permission === 'super_admin')).toBe(true)
  })
})

describe('visibleSections filters by viewer', () => {
  it('a member sees no Monitoring, Admin or Platform section', () => {
    const titles = visibleSections({ isOrgAdmin: false, isSuperAdmin: false }).map(s => s.title)
    expect(titles).not.toContain('Monitoring')
    expect(titles).not.toContain('Admin')
    expect(titles).not.toContain('Platform')
    expect(titles).toContain('Analyse')
    expect(titles).toContain('Data sources')
  })

  it('an org admin sees Monitoring and Admin but not Platform', () => {
    const titles = visibleSections({ isOrgAdmin: true, isSuperAdmin: false }).map(s => s.title)
    expect(titles).toContain('Monitoring')
    expect(titles).toContain('Admin')
    expect(titles).not.toContain('Platform')
  })

  it('super-admin power does not by itself grant org administration', () => {
    // RequireAdmin reads is_org_admin, so the rail must not infer it from
    // is_super_admin -- that would show entries the router then refuses.
    const titles = visibleSections({ isOrgAdmin: false, isSuperAdmin: true }).map(s => s.title)
    expect(titles).toContain('Platform')
    expect(titles).not.toContain('Admin')
  })

  it('drops a section whose every item was filtered out', () => {
    const sections = visibleSections({ isOrgAdmin: false, isSuperAdmin: false })
    expect(sections.every(s => s.items.length > 0)).toBe(true)
  })
})
