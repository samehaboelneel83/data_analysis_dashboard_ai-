import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  getAuthToken, setAuthToken, setUnauthorizedHandler,
  attachAuthHeader, handleResponseError, api,
} from '../services/api'

describe('auth-aware API client', () => {
  beforeEach(() => {
    localStorage.clear()
    setAuthToken(null)
    setUnauthorizedHandler(null)
  })

  it('has no token by default', () => {
    expect(getAuthToken()).toBeNull()
  })

  it('persists a set token to localStorage and reflects it via getAuthToken', () => {
    setAuthToken('abc123')
    expect(getAuthToken()).toBe('abc123')
    expect(localStorage.getItem('datalytics_token')).toBe('abc123')
  })

  it('clearing the token removes it from localStorage', () => {
    setAuthToken('abc123')
    setAuthToken(null)
    expect(getAuthToken()).toBeNull()
    expect(localStorage.getItem('datalytics_token')).toBeNull()
  })

  it('attaches an Authorization header when a token is set', () => {
    setAuthToken('abc123')
    const config: any = { headers: {} }
    const result = attachAuthHeader(config)
    expect(result.headers.Authorization).toBe('Bearer abc123')
  })

  it('does not attach an Authorization header when no token is set', () => {
    const config: any = { headers: {} }
    const result = attachAuthHeader(config)
    expect(result.headers.Authorization).toBeUndefined()
  })

  it('a 401 response clears the token and invokes the unauthorized handler', async () => {
    setAuthToken('abc123')
    const handler = vi.fn()
    setUnauthorizedHandler(handler)

    await expect(handleResponseError({ response: { status: 401 } })).rejects.toBeTruthy()

    expect(getAuthToken()).toBeNull()
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('a non-401 error does not clear the token or invoke the handler', async () => {
    setAuthToken('abc123')
    const handler = vi.fn()
    setUnauthorizedHandler(handler)

    await expect(handleResponseError({ response: { status: 500 } })).rejects.toBeTruthy()

    expect(getAuthToken()).toBe('abc123')
    expect(handler).not.toHaveBeenCalled()
  })

  it('a 401 with no handler registered still clears the token without throwing', async () => {
    setAuthToken('abc123')
    await expect(handleResponseError({ response: { status: 401 } })).rejects.toBeTruthy()
    expect(getAuthToken()).toBeNull()
  })

  it('registers attachAuthHeader and handleResponseError as interceptors on the shared axios instance', async () => {
    setAuthToken('abc123')
    // Access the registered request interceptor handler directly and confirm it behaves
    // like attachAuthHeader — this proves the registration line in api.ts actually ran,
    // not just that attachAuthHeader works in isolation.
    const requestHandlers = (api as any).interceptors.request.handlers
    expect(requestHandlers.length).toBeGreaterThan(0)
    const result = await requestHandlers[0].fulfilled({ headers: {} })
    expect(result.headers.Authorization).toBe('Bearer abc123')

    const responseHandlers = (api as any).interceptors.response.handlers
    expect(responseHandlers.length).toBeGreaterThan(0)
    await expect(responseHandlers[0].rejected({ response: { status: 401 } })).rejects.toBeTruthy()
    expect(getAuthToken()).toBeNull()
  })
})
