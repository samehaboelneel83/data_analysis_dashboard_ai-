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
