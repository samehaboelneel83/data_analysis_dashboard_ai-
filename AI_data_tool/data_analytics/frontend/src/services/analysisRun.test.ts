import { afterEach, describe, expect, it, vi } from 'vitest'
import { analysisCatalogueApi, api } from './api'

/** A slow analysis the server queued: the browser waits for the job and
 *  resolves exactly as if it had run in the request. */
describe('running an analysis that the server queued', () => {
  afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers() })

  it('resolves at once when the server ran it in the request', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: { analysis: 'x', result_kind: 'k', params: {}, result: { a: 1 } } })
    const get = vi.spyOn(api, 'get')
    const got = await analysisCatalogueApi.run(7, 'x', { p: 1 })
    expect(got.result).toEqual({ a: 1 })
    expect(post.mock.calls[0][1]).toEqual({ name: 'x', params: { p: 1 }, background: 'auto' })
    expect(get).not.toHaveBeenCalled()
  })

  it('waits for the job and resolves with its result', async () => {
    vi.useFakeTimers()
    vi.spyOn(api, 'post').mockResolvedValue({ data: { analysis: 'segment', result_kind: 'segment', job_id: 12, state: 'queued' } })
    const get = vi.spyOn(api, 'get')
      .mockResolvedValueOnce({ data: { state: 'running', result: null, error: null } })
      .mockResolvedValueOnce({ data: { state: 'succeeded', error: null,
        result: { analysis: 'segment', result_kind: 'segment', params: {}, result: { rows: [] } } } })
    const queued = vi.fn()
    const pending = analysisCatalogueApi.run(7, 'segment', {}, { onQueued: queued })
    await vi.advanceTimersByTimeAsync(4000)
    const got = await pending
    expect(queued).toHaveBeenCalledWith(12)
    expect(get).toHaveBeenCalledTimes(2)
    expect(get.mock.calls[0][0]).toBe('/jobs/12')
    expect(got.result_kind).toBe('segment')
  })

  it('a job that failed is the same refusal the request would have given', async () => {
    vi.useFakeTimers()
    vi.spyOn(api, 'post').mockResolvedValue({ data: { job_id: 3, state: 'queued' } })
    vi.spyOn(api, 'get').mockResolvedValue({ data: { state: 'failed', result: null, error: 'Only 12 usable rows.' } })
    const pending = analysisCatalogueApi.run(7, 'segment', {}).catch(e => e)
    await vi.advanceTimersByTimeAsync(2000)
    const err = await pending
    expect(err.response.data.detail).toBe('Only 12 usable rows.')
    expect(err.response.status).toBe(400)
  })
})
