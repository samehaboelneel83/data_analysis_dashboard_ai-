import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import AskAI from './AskAI'
import { renderWithProviders } from '../test/renderWithProviders'
import { agentApi, allowAiApi, analysisApi, dataSourcesApi, datasetsApi,
  LLM_ENDPOINTS_EVENT, type LlmEndpointsOut } from '../services/api'

/**
 * B-18 (plan test): on /ask?dataset=1 with the model offline, typing in the
 * locked box and pressing Enter reset the page to "Choose your data". The
 * whole page, the real ChatPane and Composer: the box keeps focus, Enter
 * stays in it, and the dataset stays chosen.
 */
let where = ''
function Probe() { where = useLocation().search; return null }

const offline: LlmEndpointsOut = {
  llm_enabled: true, default: 'env', auto_pick: null, source: 'environment', ai_available: false,
  endpoints: [{ id: 'env', name: 'Default', model: 'qwen', enabled: true, is_default: true, strength: 5, context: null,
    status: { ok: false, latency_ms: null, checked_at: new Date().toISOString(), error: 'ConnectTimeout' } }],
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(datasetsApi, 'list').mockResolvedValue([{ id: 1, name: 'Demo — Sales', mode: 'import', filename: 's.csv',
    columns: [{ id: 1, name: 'region', dtype: 'object' }, { id: 2, name: 'revenue', dtype: 'float64' }] } as never])
  vi.spyOn(dataSourcesApi, 'list').mockResolvedValue([])
  vi.spyOn(agentApi, 'listConversations').mockResolvedValue([])
  vi.spyOn(agentApi, 'messages').mockResolvedValue([])
  vi.spyOn(allowAiApi, 'get').mockResolvedValue({ own: null, effective: true, decided_by: 'default', connection: null } as never)
  vi.spyOn(analysisApi, 'get').mockResolvedValue(null)
})
afterEach(() => { vi.restoreAllMocks() })

describe('Ask with the model offline (B-18)', () => {
  it('Enter in the locked box keeps the chosen dataset and the focus', async () => {
    renderWithProviders(<MemoryRouter initialEntries={['/ask?dataset=1']}><AskAI /><Probe /></MemoryRouter>)
    await screen.findByRole('textbox', { name: /your question/i })
    await waitFor(() => expect(agentApi.listConversations).toHaveBeenCalled())
    await new Promise(r => setTimeout(r, 50))     // the thread list settles (the pane remounts once)
    act(() => {
      window.dispatchEvent(new CustomEvent(LLM_ENDPOINTS_EVENT, { detail: { data: offline, at: Date.now() } }))
    })
    const box = screen.getByRole('textbox', { name: /your question/i })
    await waitFor(() => expect(box).toHaveAttribute('aria-disabled', 'true'))
    box.focus()
    expect(document.activeElement).toBe(box)
    fireEvent.change(box, { target: { value: 'total revenue' } })
    fireEvent.keyDown(box, { key: 'Enter' })
    fireEvent.keyDown(box, { key: 'a', ctrlKey: true })
    expect(document.activeElement).toBe(box)
    expect(where).toBe('?dataset=1')
    expect(screen.queryByText('Choose your data')).toBeNull()
    expect(agentApi.listConversations).toHaveBeenCalled()
  })
})
