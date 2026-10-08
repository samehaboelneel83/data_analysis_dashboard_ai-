import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DatasetSensitivity from './DatasetSensitivity'
import { DirectionProvider } from '../contexts/DirectionContext'
import { sensitivityApi } from '../services/api'

vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))
vi.mock('../services/api', () => ({ sensitivityApi: { get: vi.fn(), set: vi.fn() } }))

describe('DatasetSensitivity (Phase 7.3)', () => {
  it('shows the inherited label with its reason and what it enforces, and saves a new label', async () => {
    vi.mocked(sensitivityApi.get).mockResolvedValue({ label: null, effective: 'Confidential',
      reasons: ['People joins data labelled Confidential'], options: ['Public', 'Internal', 'Confidential', 'Restricted'],
      redacted_on_share: ['email'] })
    vi.mocked(sensitivityApi.set).mockResolvedValue({ label: 'Restricted', effective: 'Restricted', reasons: ['People is labelled Restricted'],
      options: ['Public', 'Internal', 'Confidential', 'Restricted'], redacted_on_share: ['email'] })
    render(<DatasetSensitivity datasetId={7} />)
    const box = await screen.findByTestId('dataset-sensitivity')
    expect(box.textContent).toContain('in force: Confidential')
    expect(box.getAttribute('title')).toContain('email redacted from links, embeds and files')
    fireEvent.change(screen.getByLabelText('Dataset sensitivity'), { target: { value: 'Restricted' } })
    await waitFor(() => expect(sensitivityApi.set).toHaveBeenCalledWith(7, 'Restricted'))
    await waitFor(() => expect(screen.getByTestId('dataset-sensitivity').getAttribute('title')).toContain('No guest links'))
  })
})

describe('DatasetSensitivity in Arabic (QA5b S5)', () => {
  it('names the control, its tooltip and what a label enforces in Arabic; the server reason stays as sent', async () => {
    localStorage.setItem('datalytics.language', 'ar')
    vi.mocked(sensitivityApi.get).mockResolvedValue({ label: null, effective: 'Confidential',
      reasons: ['People joins data labelled Confidential'], options: ['Public', 'Internal', 'Confidential', 'Restricted'],
      redacted_on_share: ['email', 'phone'] })
    render(<DirectionProvider><DatasetSensitivity datasetId={7} /></DirectionProvider>)
    const box = await screen.findByTestId('dataset-sensitivity')
    expect(screen.getByLabelText('حساسية مجموعة البيانات')).toBeInTheDocument()
    expect(box.getAttribute('title')).toBe('المطبّق: سري — ⁨People joins data labelled Confidential⁩ · '
      + 'روابط الضيوف تتطلب عضوًا مسجّل الدخول؛ وتُحجب ⁨email، phone⁩ من الروابط والتضمينات والملفات.')
    localStorage.removeItem('datalytics.language')
  })
})
