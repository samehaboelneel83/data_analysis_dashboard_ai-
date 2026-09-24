import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import NotebookSnippet from './NotebookSnippet'

vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))
vi.mock('../services/api', () => ({ api: { defaults: { baseURL: 'http://localhost:8000/api/v1' } } }))

describe('NotebookSnippet (Phase 7.6)', () => {
  it('shows a governed-frame snippet for this dataset, never a key', () => {
    render(<NotebookSnippet datasetId={120} datasetName="Demo — Sales" />)
    fireEvent.click(screen.getByRole('button', { name: /Use in Python/ }))
    const code = screen.getByTestId('notebook-code').textContent ?? ''
    expect(code).toContain('Datalytics("http://localhost:8000"')
    expect(code).toContain('dl.frame(120)')
    expect(code).toContain('api_key="dl_…"')
  })
})
