import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import LlmEndpointsPanel from './LlmEndpointsPanel'
import { platformSettingsApi, type LlmEndpointsOut } from '../../services/api'

vi.mock('react-hot-toast', () => ({
  default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}))
vi.mock('../../services/api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../services/api')
  return {
    ...actual,
    platformSettingsApi: { getLlmEndpoints: vi.fn(), saveLlmEndpoints: vi.fn(), resetLlmEndpoints: vi.fn(), testLlm: vi.fn() },
  }
})

const OUT: LlmEndpointsOut = {
  llm_enabled: true, default: 'env', auto_pick: null, source: 'environment',
  endpoints: [{ id: 'env', name: 'Default', model: 'qwen3.5', enabled: true, is_default: true, strength: 5, context: 32768, max_model_len: 32768,
    base_url: 'http://10.0.0.5:8000/v1', has_api_key: true,
    status: { ok: false, latency_ms: null, checked_at: '', error: 'ConnectError' } }],
}

beforeEach(() => {
  vi.mocked(platformSettingsApi.getLlmEndpoints).mockResolvedValue(OUT)
  vi.mocked(platformSettingsApi.saveLlmEndpoints).mockResolvedValue({ ...OUT, source: 'saved' })
})

describe('LlmEndpointsPanel', () => {
  it('adds a second endpoint, makes Auto the default and saves, keeping the stored key', async () => {
    render(<LlmEndpointsPanel />)
    await screen.findByDisplayValue('http://10.0.0.5:8000/v1')
    fireEvent.click(screen.getByRole('button', { name: /Add endpoint/ }))
    const names = screen.getAllByLabelText('Name')
    fireEvent.change(names[1], { target: { value: 'Backup' } })
    fireEvent.change(screen.getByLabelText('Address (ending in /v1): Backup'), { target: { value: 'http://backup:8000/v1' } })
    fireEvent.change(screen.getByLabelText('Model: Backup'), { target: { value: 'llama' } })
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'auto' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save endpoints' }))
    await waitFor(() => expect(platformSettingsApi.saveLlmEndpoints).toHaveBeenCalled())
    const [list, def] = vi.mocked(platformSettingsApi.saveLlmEndpoints).mock.calls[0]
    expect(def).toBe('auto')
    expect(list).toEqual([
      expect.objectContaining({ id: 'env', base_url: 'http://10.0.0.5:8000/v1', api_key: null }),
      expect.objectContaining({ id: undefined, name: 'Backup', base_url: 'http://backup:8000/v1', model: 'llama', api_key: null, strength: 0, context: 0 }),
    ])
  })

  it('shows each endpoint with its light', async () => {
    const { container } = render(<LlmEndpointsPanel />)
    await screen.findByDisplayValue('http://10.0.0.5:8000/v1')
    expect(container.querySelector('[data-light="down"]')).not.toBeNull()
  })

  it('the name and context boxes are wide enough for what they show (QA V10)', async () => {
    // "تلقائي: 32768" and "Qwen 3.8 27B" were cut off in 110 px boxes.
    render(<LlmEndpointsPanel />)
    await screen.findByDisplayValue('http://10.0.0.5:8000/v1')
    const px = (el: HTMLElement) => parseInt(el.style.width || el.style.minWidth, 10)
    expect(px(screen.getAllByLabelText('Name')[0])).toBeGreaterThanOrEqual(140)
    expect(px(screen.getByLabelText(/: Default$/, { selector: 'input[type="number"][step="1024"]' }))).toBeGreaterThanOrEqual(140)
  })
})
