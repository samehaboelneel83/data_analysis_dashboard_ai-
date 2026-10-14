import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import LlmPicker, { choiceLight, effectiveChoice, mainStep } from './LlmPicker'
import type { LlmEndpointsOut } from '../services/api'
import * as api from '../services/api'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { email: 'a@b.c', is_super_admin: true } }),
}))

const DATA: LlmEndpointsOut = {
  llm_enabled: true, default: 'a', auto_pick: 'b', source: 'saved',
  endpoints: [
    { id: 'a', name: 'Server A', model: 'qwen', enabled: true, is_default: true, strength: 6, context: 32768,
      status: { ok: false, latency_ms: null, checked_at: '', error: 'ConnectError: refused' } },
    { id: 'b', name: 'Server B', model: 'llama', enabled: true, is_default: false, strength: 4, context: 16384,
      status: { ok: true, latency_ms: 42, checked_at: '', error: null } },
  ],
}

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(api.llmApi, 'endpoints').mockResolvedValue(DATA)
})

describe('LlmPicker', () => {
  it('shows a red light when the default model is down', async () => {
    render(<MemoryRouter><LlmPicker /></MemoryRouter>)
    const button = await screen.findByRole('button', { name: /Server A, not reachable/ })
    expect(button.querySelector('[data-light="down"]')).not.toBeNull()
  })

  it('lists Auto and every endpoint with its own light, and remembers the pick', async () => {
    render(<MemoryRouter><LlmPicker /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: /AI model/ }))
    const items = screen.getAllByRole('menuitemradio')
    expect(items.map(i => i.textContent)).toEqual([
      expect.stringContaining('Auto'), expect.stringContaining('Server A'), expect.stringContaining('Server B')])
    expect(items[1].querySelector('[data-light="down"]')).not.toBeNull()
    expect(items[2].querySelector('[data-light="up"]')).not.toBeNull()
    expect(items[0]).toHaveTextContent('Using Server B')
    fireEvent.click(items[2])
    expect(api.getLlmChoice()).toBe('b')
    await waitFor(() => expect(screen.getByRole('button', { name: /Server B, available/ })).toBeInTheDocument())
  })

  it('says in plain words what picking a model changes (4.9)', async () => {
    render(<MemoryRouter><LlmPicker /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: /AI model/ }))
    const box = screen.getByTestId('llm-explainer')
    expect(box).toHaveTextContent('What does this change?')
    expect(box).toHaveTextContent(/Ask AI, the steps of Automations/)
    expect(box).toHaveTextContent(/Lighter models answer faster/)
    expect(box).toHaveTextContent(/set the default for everyone under Manage/)
  })

  it('forgets a pick of an endpoint that no longer exists', async () => {
    api.setLlmChoice('gone')
    render(<MemoryRouter><LlmPicker /></MemoryRouter>)
    await screen.findByRole('button', { name: /Server A/ })
    expect(api.getLlmChoice()).toBeNull()
  })
})

describe('choice helpers', () => {
  it('Auto is green when anything is up, red when nothing is', () => {
    expect(choiceLight(DATA, 'auto')).toBe('up')
    expect(choiceLight({ ...DATA, auto_pick: null }, 'auto')).toBe('down')
    expect(choiceLight({ ...DATA, llm_enabled: false }, 'b')).toBe('off')
    expect(effectiveChoice(DATA, null)).toBe('a')
    expect(effectiveChoice(DATA, 'auto')).toBe('auto')
  })
})

describe('on Auto, the button names the model that really answered', () => {
  const used = (header: string) => act(() => {
    window.dispatchEvent(new CustomEvent(api.LLM_USED_EVENT, { detail: api.parseLlmUsed(header) }))
  })

  it('switches the name when the next request is answered by another model, and highlights it', async () => {
    api.setLlmChoice('auto')
    render(<MemoryRouter><LlmPicker /></MemoryRouter>)
    await screen.findByRole('button', { name: /AI model: Auto/ })
    used('b=light,a=heavy')
    const button = await screen.findByRole('button', { name: /Auto → Server A/ })
    // The heavy step carried the answer, and Server A is down: the light says so.
    expect(button.querySelector('[data-light="down"]')).not.toBeNull()
    used('b=light,b=heavy')
    const moved = await screen.findByRole('button', { name: /Auto → Server B, available/ })
    expect(moved).toHaveAttribute('data-switched', 'true')
    fireEvent.click(moved)
    expect(screen.getByTestId('llm-last-request')).toHaveTextContent('Last request: Server B (light task) → Server B (heavy task)')
  })

  it('after a reload it shows the last use the server remembers', async () => {
    api.setLlmChoice('auto')
    vi.mocked(api.llmApi.endpoints).mockResolvedValue({ ...DATA, last_used: [
      { id: 'b', name: 'Server B', model: 'llama', weight: 'light', auto: true, feature: 'ask', at: '' }] })
    render(<MemoryRouter><LlmPicker /></MemoryRouter>)
    expect(await screen.findByRole('button', { name: /Auto → Server B/ })).toBeInTheDocument()
  })

  it('a named model keeps its own name', async () => {
    api.setLlmChoice('a')
    render(<MemoryRouter><LlmPicker /></MemoryRouter>)
    await screen.findByRole('button', { name: /AI model: Server A/ })
    used('a=heavy')
    expect(screen.getByRole('button', { name: /AI model: Server A,/ })).toBeInTheDocument()
  })

  it('reads the heavy step as the one that carried the answer', () => {
    expect(mainStep(api.parseLlmUsed('s=light,b=heavy,s=light'))?.id).toBe('b')
    expect(mainStep(api.parseLlmUsed('s=light,m=normal'))?.id).toBe('m')
    expect(api.parseLlmUsed('')).toEqual([])
  })
})
