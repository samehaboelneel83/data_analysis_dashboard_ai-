import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Settings from './Settings'
import { AuthContext } from '../../contexts/AuthContext'
import { platformSettingsApi, mapSettingsApi, type PlatformSetting } from '../../services/api'
import toast from 'react-hot-toast'

vi.mock('react-hot-toast', () => ({
  default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}))

vi.mock('../../services/api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../services/api')
  return {
    ...actual,
    platformSettingsApi: { get: vi.fn(), save: vi.fn(), testLlm: vi.fn() },
    mapSettingsApi: { get: vi.fn(), set: vi.fn() },
  }
})

const setting = (over: Partial<PlatformSetting>): PlatformSetting => ({
  key: 'k', label: 'K', help: '', type: 'str', bounds: {}, editable: true, secret: false, restart: false,
  options: [], value: '', is_set: false, default: '', source: 'environment', updated_by: null, updated_at: null,
  ...over,
})

const PAYLOAD = {
  categories: [
    { id: 'ai', label: 'AI model (LLM)', settings: [
      setting({ key: 'llm_model', label: 'Model name', value: 'qwen3.5', default: 'qwen3.5' }),
      setting({ key: 'llm_timeout_s', label: 'Request timeout (seconds)', type: 'float', value: 180, bounds: { gt: 0 } }),
      setting({ key: 'llm_api_key', label: 'API key', secret: true, value: null, is_set: true }),
      setting({ key: 'llm_enabled', label: 'AI features on', type: 'bool', value: true }),
    ] },
    { id: 'data', label: 'Data import and limits', settings: [
      setting({ key: 'source_connect_timeout_s', label: 'Database connect timeout (seconds)', type: 'int', value: 12,
        default: 8, source: 'saved', updated_by: 'admin@x' }),
      setting({ key: 'widget_work_max_concurrency', label: 'Charts computed at once', type: 'int', value: 4, restart: true }),
    ] },
    { id: 'deployment', label: 'Deployment (read-only)', settings: [
      setting({ key: 'database_url', label: 'Database', editable: false, secret: true, value: null, is_set: true }),
      setting({ key: 'env', label: 'Environment', editable: false, value: 'development' }),
    ] },
  ],
}

function show(user: { is_super_admin?: boolean; org_admin?: boolean }, scope?: 'all' | 'platform') {
  const value = { user: { is_super_admin: !!user.is_super_admin, role: { is_org_admin: !!user.org_admin } } } as never
  return render(
    <MemoryRouter><AuthContext.Provider value={value}><Settings scope={scope} /></AuthContext.Provider></MemoryRouter>)
}

beforeEach(() => {
  vi.clearAllMocks()
  ;(platformSettingsApi.get as any).mockResolvedValue(PAYLOAD)
  ;(platformSettingsApi.save as any).mockResolvedValue(PAYLOAD)
  ;(mapSettingsApi.get as any).mockResolvedValue({ tile_url: 'http://tiles/{z}/{x}/{y}.pbf', attribution: 'OSM', contrast_tile_url: null })
})

describe('Admin -> Settings', () => {
  it('shows an org admin the tile server and the other org pages, and no platform settings', async () => {
    show({ org_admin: true })
    expect(await screen.findByDisplayValue('http://tiles/{z}/{x}/{y}.pbf')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Single sign-on' })).toHaveAttribute('href', '/admin/sso')
    expect(platformSettingsApi.get).not.toHaveBeenCalled()
    expect(screen.getByText(/shown to platform admins/)).toBeInTheDocument()
  })

  it('shows a platform admin every category, with deploy-time values read-only', async () => {
    show({ is_super_admin: true, org_admin: true })
    expect(await screen.findByLabelText('Model name')).toHaveValue('qwen3.5')
    const db = screen.getByTestId('setting-database_url')
    expect(within(db).queryByRole('textbox')).toBeNull()
    expect(db).toHaveTextContent('••••••')
    expect(within(screen.getByTestId('setting-env')).getByText('development')).toBeInTheDocument()
  })

  it('never shows a secret, and a blank secret is not sent', async () => {
    show({ is_super_admin: true })
    const key = await screen.findByLabelText('API key')
    expect(key).toHaveValue('')
    expect(key).toHaveAttribute('placeholder', expect.stringMatching(/^Set/))
    fireEvent.change(screen.getByLabelText('Model name'), { target: { value: 'qwen-next' } })
    fireEvent.change(key, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(platformSettingsApi.save).toHaveBeenCalledWith({ llm_model: 'qwen-next' }))
  })

  it('sends numbers as numbers, and refuses text in a number field', async () => {
    show({ is_super_admin: true })
    const timeout = await screen.findByLabelText('Request timeout (seconds)')
    fireEvent.change(timeout, { target: { value: '45.5' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(platformSettingsApi.save).toHaveBeenCalledWith({ llm_timeout_s: 45.5 }))

    fireEvent.change(screen.getByLabelText('Charts computed at once'), { target: { value: 'four' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(toast.error).toHaveBeenCalledWith('Charts computed at once: enter a whole number')
    expect(platformSettingsApi.save).toHaveBeenCalledTimes(1)
  })

  it('resets a saved value to the environment', async () => {
    show({ is_super_admin: true })
    const row = await screen.findByTestId('setting-source_connect_timeout_s')
    expect(row).toHaveTextContent('Environment value: 8.')
    fireEvent.click(within(row).getByRole('button', { name: /Reset/ }))
    await waitFor(() => expect(platformSettingsApi.save).toHaveBeenCalledWith({ source_connect_timeout_s: null }))
  })

  it('says when a saved setting needs a restart', async () => {
    ;(platformSettingsApi.save as any).mockResolvedValue({ ...PAYLOAD, restart_required: ['widget_work_max_concurrency'] })
    show({ is_super_admin: true })
    fireEvent.change(await screen.findByLabelText('Charts computed at once'), { target: { value: '6' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(toast).toHaveBeenCalledWith(
      'Saved. These apply after the backend restarts: Charts computed at once', expect.anything()))
  })

  it('tests the LLM with the values on the form, before saving', async () => {
    ;(platformSettingsApi.testLlm as any).mockResolvedValue({ ok: true, latency_ms: 120, model: 'm2', detail: 'ok' })
    show({ is_super_admin: true })
    fireEvent.change(await screen.findByLabelText('Model name'), { target: { value: 'm2' } })
    fireEvent.change(screen.getByLabelText('API key'), { target: { value: 'k2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))
    await waitFor(() => expect(platformSettingsApi.testLlm).toHaveBeenCalledWith({ llm_model: 'm2', llm_api_key: 'k2' }))
    expect(toast.success).toHaveBeenCalledWith('Connected to m2 in 120 ms')
    expect(platformSettingsApi.save).not.toHaveBeenCalled()
  })

  it('finds a setting by name', async () => {
    show({ is_super_admin: true })
    fireEvent.change(await screen.findByLabelText('Find a setting'), { target: { value: 'connect' } })
    expect(screen.getByTestId('setting-source_connect_timeout_s')).toBeInTheDocument()
    expect(screen.queryByTestId('setting-llm_model')).toBeNull()
  })
})
