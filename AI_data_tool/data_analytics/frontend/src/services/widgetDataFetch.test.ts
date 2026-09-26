/**
 * The widget-data fetch discipline in api.ts: in-flight dedup, the 30s TTL
 * cache, the fresh bypass, and the 6-wide concurrency gate. axios is mocked
 * at the instance level; each test asserts on POST call counts.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const { post } = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('axios', () => ({
  default: {
    create: () => ({
      post,
      get: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
      defaults: { headers: { common: {} } },
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    }),
  },
}))

import {
  widgetDataApi, clearWidgetDataClientCache,
  WIDGET_DATA_TTL_MS, WIDGET_DATA_MAX_CONCURRENT,
} from './api'

beforeEach(() => {
  vi.useFakeTimers()
  post.mockReset()
  clearWidgetDataClientCache()
})
afterEach(() => { vi.useRealTimers() })

const cfg = (n: number) => ({ dimension: 'region', limit: n })

describe('widget-data fetch discipline', () => {
  it('dedups identical concurrent requests into one POST', async () => {
    post.mockResolvedValue({ data: { rows: [1] } })
    const [a, b] = await Promise.all([
      widgetDataApi.query(1, cfg(10)),
      widgetDataApi.query(1, cfg(10)),
    ])
    expect(post).toHaveBeenCalledTimes(1)
    expect(a).toEqual(b)
  })

  it('different configs are different requests', async () => {
    post.mockResolvedValue({ data: { rows: [1] } })
    await Promise.all([widgetDataApi.query(1, cfg(10)), widgetDataApi.query(1, cfg(11))])
    expect(post).toHaveBeenCalledTimes(2)
  })

  it('serves repeats from the TTL cache, then refetches after expiry', async () => {
    post.mockResolvedValue({ data: { rows: [1] } })
    await widgetDataApi.query(1, cfg(10))
    await widgetDataApi.query(1, cfg(10))
    expect(post).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(WIDGET_DATA_TTL_MS + 1)
    await widgetDataApi.query(1, cfg(10))
    expect(post).toHaveBeenCalledTimes(2)
  })

  it('fresh: true bypasses the cache', async () => {
    post.mockResolvedValue({ data: { rows: [1] } })
    await widgetDataApi.query(1, cfg(10))
    await widgetDataApi.query(1, cfg(10), [], 'bar', { fresh: true })
    expect(post).toHaveBeenCalledTimes(2)
  })

  it('a failed request is not cached', async () => {
    post.mockRejectedValueOnce(new Error('boom'))
    await expect(widgetDataApi.query(1, cfg(10))).rejects.toThrow('boom')
    post.mockResolvedValue({ data: { rows: [1] } })
    await widgetDataApi.query(1, cfg(10))
    expect(post).toHaveBeenCalledTimes(2)
  })

  it(`never runs more than ${WIDGET_DATA_MAX_CONCURRENT} POSTs at once`, async () => {
    let inFlight = 0
    let peak = 0
    const resolvers: (() => void)[] = []
    post.mockImplementation(() => new Promise(resolve => {
      inFlight += 1
      peak = Math.max(peak, inFlight)
      resolvers.push(() => { inFlight -= 1; resolve({ data: { ok: true } }) })
    }))

    const all = Promise.all(
      Array.from({ length: 20 }, (_, i) => widgetDataApi.query(1, cfg(i))))
    // drain: release whatever is in flight until all 20 settle
    for (let round = 0; round < 40 && resolvers.length + 0 >= 0; round++) {
      await Promise.resolve()  // let queued acquires run
      const batch = resolvers.splice(0)
      if (batch.length === 0 && inFlight === 0 && post.mock.calls.length >= 20) break
      batch.forEach(r => r())
    }
    await all
    expect(post).toHaveBeenCalledTimes(20)
    expect(peak).toBeLessThanOrEqual(WIDGET_DATA_MAX_CONCURRENT)
  })
})

describe('letting go of a widget request (E14)', () => {
  /** A POST that stays in flight until released, and rejects the way axios
   *  does when its signal aborts. */
  function pendingPosts() {
    const releases: (() => void)[] = []
    post.mockImplementation((_url: string, _body: unknown, cfg?: { signal?: AbortSignal }) =>
      new Promise((resolve, reject) => {
        cfg?.signal?.addEventListener('abort', () =>
          reject(Object.assign(new Error('canceled'), { code: 'ERR_CANCELED' })))
        releases.push(() => resolve({ data: { ok: true } }))
      }))
    return releases
  }
  const flush = async () => { for (let i = 0; i < 5; i++) await Promise.resolve() }
  const signalOf = (call: number) => (post.mock.calls[call][2] as { signal: AbortSignal }).signal

  it('a queued request whose widget let go is never sent', async () => {
    const releases = pendingPosts()
    const busy = Array.from({ length: WIDGET_DATA_MAX_CONCURRENT }, (_, i) => widgetDataApi.query(1, cfg(i)))
    const ctl = new AbortController()
    const left = widgetDataApi.query(1, cfg(99), [], 'bar', { signal: ctl.signal })
    await flush()
    expect(post).toHaveBeenCalledTimes(WIDGET_DATA_MAX_CONCURRENT)
    ctl.abort()
    await expect(left).rejects.toMatchObject({ code: 'ERR_CANCELED' })
    releases.forEach(r => r())
    await Promise.all(busy)
    await flush()
    expect(post).toHaveBeenCalledTimes(WIDGET_DATA_MAX_CONCURRENT)
  })

  it('an in-flight request is aborted when its only widget lets go, and frees its slot', async () => {
    const releases = pendingPosts()
    const ctl = new AbortController()
    const p = widgetDataApi.query(1, cfg(1), [], 'bar', { signal: ctl.signal })
    await flush()
    ctl.abort()
    await expect(p).rejects.toMatchObject({ code: 'ERR_CANCELED' })
    expect(signalOf(0).aborted).toBe(true)
    // The slot is free again: a full set of new requests all go out.
    const next = Array.from({ length: WIDGET_DATA_MAX_CONCURRENT }, (_, i) => widgetDataApi.query(2, cfg(i)))
    await flush()
    expect(post).toHaveBeenCalledTimes(1 + WIDGET_DATA_MAX_CONCURRENT)
    releases.forEach(r => r())
    await Promise.all(next)
  })

  it('a shared request lives while another widget still holds it', async () => {
    const releases = pendingPosts()
    const a = new AbortController(), b = new AbortController()
    const pa = widgetDataApi.query(1, cfg(1), [], 'bar', { signal: a.signal })
    const pb = widgetDataApi.query(1, cfg(1), [], 'bar', { signal: b.signal })
    await flush()
    expect(post).toHaveBeenCalledTimes(1)
    a.abort()
    await expect(pa).rejects.toMatchObject({ code: 'ERR_CANCELED' })
    expect(signalOf(0).aborted).toBe(false)
    releases[0]()
    await expect(pb).resolves.toEqual({ ok: true })
  })

  it('is aborted when the last holder lets go, and asked for afresh next time', async () => {
    const releases = pendingPosts()
    const a = new AbortController(), b = new AbortController()
    const pa = widgetDataApi.query(1, cfg(1), [], 'bar', { signal: a.signal })
    const pb = widgetDataApi.query(1, cfg(1), [], 'bar', { signal: b.signal })
    await flush()
    a.abort(); b.abort()
    await expect(pa).rejects.toBeTruthy(); await expect(pb).rejects.toBeTruthy()
    expect(signalOf(0).aborted).toBe(true)
    const again = widgetDataApi.query(1, cfg(1))
    await flush()
    expect(post).toHaveBeenCalledTimes(2)
    releases[1]()
    await expect(again).resolves.toEqual({ ok: true })
  })

  it('a caller without a signal keeps the request alive', async () => {
    const releases = pendingPosts()
    const a = new AbortController()
    const pa = widgetDataApi.query(1, cfg(1), [], 'bar', { signal: a.signal })
    const pinned = widgetDataApi.query(1, cfg(1))
    await flush()
    a.abort()
    await expect(pa).rejects.toBeTruthy()
    expect(signalOf(0).aborted).toBe(false)
    releases[0]()
    await expect(pinned).resolves.toEqual({ ok: true })
  })
})
