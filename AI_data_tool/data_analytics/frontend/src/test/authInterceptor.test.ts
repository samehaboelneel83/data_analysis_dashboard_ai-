import { AxiosHeaders } from 'axios'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  setUnauthorizedHandler, handleResponseError, takeLegacyToken, api, LLM_USED_EVENT,
} from '../services/api'

/**
 * T6 (BUG-040): the session is an httpOnly cookie the server sets. Nothing
 * here stores, reads or attaches the login token any more -- the client only
 * sends credentials and the CSRF header, and reacts to a 401.
 */
describe('auth-aware API client', () => {
  beforeEach(() => {
    localStorage.clear()
    setUnauthorizedHandler(null)
  })

  it('sends the session cookie and the CSRF header on every request', () => {
    expect(api.defaults.withCredentials).toBe(true)
    expect((api.defaults.headers as any)['X-Requested-With']).toBe('XMLHttpRequest')
  })

  it('attaches no Authorization header of its own', () => {
    // The one request interceptor adds the person's LLM pick (X-LLM-Endpoint)
    // and nothing else: the session still rides only in the httpOnly cookie.
    const handlers = (api as any).interceptors.request.handlers.filter(Boolean)
    expect(handlers).toHaveLength(1)
    localStorage.setItem('datalytics.llmEndpoint', 'auto')
    const config = handlers[0].fulfilled({ headers: new AxiosHeaders() })
    localStorage.removeItem('datalytics.llmEndpoint')
    expect(config.headers.get('X-LLM-Endpoint')).toBe('auto')
    expect(config.headers.get('Authorization')).toBeUndefined()
    expect((api.defaults.headers as any).Authorization).toBeUndefined()
  })

  it('never writes the token to localStorage', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    await expect(handleResponseError({ response: { status: 401 } })).rejects.toBeTruthy()
    expect(setItem).not.toHaveBeenCalledWith('datalytics_token', expect.anything())
    setItem.mockRestore()
  })

  it('hands over a token an older build stored, exactly once, and deletes it', () => {
    localStorage.setItem('datalytics_token', 'old-jwt')
    expect(takeLegacyToken()).toBe('old-jwt')
    expect(localStorage.getItem('datalytics_token')).toBeNull()
    expect(takeLegacyToken()).toBeNull()
  })

  it('a 401 invokes the unauthorized handler', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    await expect(handleResponseError({ response: { status: 401 } })).rejects.toBeTruthy()
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('a quiet 401 -- the start-up "am I logged in?" check -- does not redirect', async () => {
    // Every visitor makes that check now; a share-link viewer must not be
    // bounced to the login page because they have no session.
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    await expect(handleResponseError({ response: { status: 401 }, config: { quiet401: true } })).rejects.toBeTruthy()
    expect(handler).not.toHaveBeenCalled()
  })

  it('a non-401 error does not invoke the handler', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    await expect(handleResponseError({ response: { status: 500 } })).rejects.toBeTruthy()
    expect(handler).not.toHaveBeenCalled()
  })

  it('registers handleResponseError on the shared axios instance', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    const responseHandlers = (api as any).interceptors.response.handlers
    expect(responseHandlers.length).toBeGreaterThan(0)
    await expect(responseHandlers[0].rejected({ response: { status: 401 } })).rejects.toBeTruthy()
    expect(handler).toHaveBeenCalledTimes(1)
  })
})

describe('X-LLM-Used', () => {
  it('a response that used models announces which ones', () => {
    const seen: unknown[] = []
    const on = (e: Event) => seen.push((e as CustomEvent).detail)
    window.addEventListener(LLM_USED_EVENT, on)
    const handlers = (api as any).interceptors.response.handlers.filter(Boolean)
    for (const h of handlers) h.fulfilled?.({ headers: new AxiosHeaders({ 'X-LLM-Used': 'small=light,big=heavy' }) })
    for (const h of handlers) h.fulfilled?.({ headers: new AxiosHeaders() })
    window.removeEventListener(LLM_USED_EVENT, on)
    expect(seen).toEqual([[{ id: 'small', weight: 'light' }, { id: 'big', weight: 'heavy' }]])
  })
})
