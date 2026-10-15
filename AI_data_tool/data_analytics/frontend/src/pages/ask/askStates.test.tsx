import { describe, it, expect } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { LLM_ENDPOINTS_EVENT, type LlmEndpointsOut } from '../../services/api'
import { useAiGate } from './useAiOffline'

function payload(ok: boolean): LlmEndpointsOut {
  return {
    llm_enabled: true, default: 'env', auto_pick: null, source: 'environment', ai_available: ok,
    endpoints: [{
      id: 'env', name: 'Default', model: 'qwen', enabled: true, is_default: true, strength: 5, context: null,
      status: { ok, latency_ms: null, checked_at: new Date().toISOString(), error: ok ? null : 'ConnectTimeout' },
    }],
  }
}

describe('useAiGate (AD-01)', () => {
  it('is open until the endpoints answer arrives', () => {
    const { result } = renderHook(() => useAiGate())
    expect(result.current.offline).toBe(false)
    expect(result.current.reason).toBeUndefined()
  })

  it('reports offline with a reason from a broadcast endpoints payload', () => {
    const { result } = renderHook(() => useAiGate())
    act(() => {
      window.dispatchEvent(new CustomEvent(LLM_ENDPOINTS_EVENT, { detail: { data: payload(false), at: Date.now() } }))
    })
    expect(result.current.offline).toBe(true)
    expect(result.current.reason).toMatch(/paused|unreachable/i)
    act(() => {
      window.dispatchEvent(new CustomEvent(LLM_ENDPOINTS_EVENT, { detail: { data: payload(true), at: Date.now() } }))
    })
    expect(result.current.offline).toBe(false)
  })
})

describe('a role without AI (QA E-08)', () => {
  it('is offline, and says the role is why -- not the model server', async () => {
    const { createElement } = await import('react')
    const { AuthContext } = await import('../../contexts/AuthContext')
    const user = { id: 1, email: 'v@x.io', is_active: true, organization: { id: 1, name: 'O' },
      role: { id: 2, name: 'Viewer', is_org_admin: false, permissions: { use_ai: false } } }
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      createElement(AuthContext.Provider, { value: { user, loading: false, login: async () => {}, logout: () => {} } as never }, children)
    const { result } = renderHook(() => useAiGate(), { wrapper })
    expect(result.current.offline).toBe(true)
    expect(result.current.reason).toBe('Your role does not include AI features')
  })
})
