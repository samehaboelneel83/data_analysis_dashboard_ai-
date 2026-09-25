import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Upload, { batchBaseName } from './Upload'
import { datasetsApi } from '../services/api'
import toast from 'react-hot-toast'

/**
 * The upload page after it learned to take several files.
 *
 * Two behaviours carry the real risk:
 *
 *   - A single ordinary file must still take the OLD path. That flow (upload,
 *     then land on the new dataset) is what everyone already knows, and the
 *     batch endpoint returns a different shape, so routing one file through it
 *     would silently change what happens on success.
 *
 *   - A partial failure must not navigate away. The per-file errors are the
 *     only record of which files were rejected and why; leaving the page
 *     throws that away and the user has no idea what to fix.
 */

const navigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<any>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('../services/api', () => ({
  datasetsApi: { upload: vi.fn(), uploadBatch: vi.fn(), list: vi.fn() },
}))

const file = (name: string, body = 'a,b\n1,2\n') =>
  new File([body], name, { type: 'text/csv' })

function show() {
  return render(<MemoryRouter><Upload /></MemoryRouter>)
}

function pick(files: File[]) {
  const input = document.querySelector('input[type=file]') as HTMLInputElement
  Object.defineProperty(input, 'files', { value: files, configurable: true })
  fireEvent.change(input)
}

const submit = () => fireEvent.click(screen.getByText('Upload', { selector: 'button' }))

beforeEach(() => {
  vi.clearAllMocks()
  ;(datasetsApi.upload as any).mockResolvedValue({ id: 7, name: 'one' })
  ;(datasetsApi.list as any).mockResolvedValue([])
  ;(datasetsApi.uploadBatch as any).mockResolvedValue({
    items: [{ source_filename: 'a.csv', status: 'created', dataset: { id: 1 }, error: null }],
    created: 1, failed: 0, mode: 'separate',
  })
})

describe('Upload', () => {
  it('explains what is missing when Upload is clicked with no file', () => {
    show()
    const button = screen.getByText('Upload', { selector: 'button' }) as HTMLButtonElement
    expect(button.disabled).toBe(false)
    submit()
    expect(toast.error).toHaveBeenCalledWith('Please select a file and enter a name')
  })

  it('accepts several files at once', () => {
    show()
    const input = document.querySelector('input[type=file]') as HTMLInputElement
    expect(input.multiple).toBe(true)
  })

  it('offers Access files as an accepted format', () => {
    show()
    const input = document.querySelector('input[type=file]') as HTMLInputElement
    expect(input.accept).toContain('.accdb')
    expect(input.accept).toContain('.mdb')
  })

  it('sends one ordinary file through the single-file endpoint', async () => {
    show()
    pick([file('solo.csv')])
    submit()

    await waitFor(() => expect(datasetsApi.upload).toHaveBeenCalled())
    expect(datasetsApi.uploadBatch).not.toHaveBeenCalled()
    // ...and still lands the user on the dataset it just made.
    expect(navigate).toHaveBeenCalledWith('/datasets/7')
  })

  it('sends an Access file through the batch endpoint even on its own', async () => {
    // One .accdb yields one dataset per table, which the single-file endpoint
    // cannot express -- it rejects them with a pointer to /batch.
    show()
    pick([file('sales.accdb')])
    submit()

    await waitFor(() => expect(datasetsApi.uploadBatch).toHaveBeenCalled())
    expect(datasetsApi.upload).not.toHaveBeenCalled()
  })

  it('sends several files through the batch endpoint', async () => {
    show()
    pick([file('a.csv'), file('b.csv')])
    submit()

    await waitFor(() => expect(datasetsApi.uploadBatch).toHaveBeenCalled())
    const [files, , , mode] = (datasetsApi.uploadBatch as any).mock.calls[0]
    expect(files).toHaveLength(2)
    expect(mode).toBe('separate')
  })

  describe('the separate/append choice', () => {
    it('is hidden for a single file, where it would mean nothing', () => {
      show()
      pick([file('solo.csv')])
      expect(screen.queryByText(/single dataset/i)).toBeNull()
    })

    it('appears once there is more than one file', () => {
      show()
      pick([file('a.csv'), file('b.csv')])
      expect(screen.getByText(/Separate datasets/i)).toBeTruthy()
      expect(screen.getByText(/single dataset/i)).toBeTruthy()
    })

    it('changes what the request asks for', async () => {
      show()
      pick([file('a.csv'), file('b.csv')])
      fireEvent.click(screen.getByDisplayValue('append'))
      submit()

      await waitFor(() => expect(datasetsApi.uploadBatch).toHaveBeenCalled())
      expect((datasetsApi.uploadBatch as any).mock.calls[0][3]).toBe('append')
    })
  })

  describe('partial failure', () => {
    beforeEach(() => {
      ;(datasetsApi.uploadBatch as any).mockResolvedValue({
        items: [
          { source_filename: 'good.csv', status: 'created', dataset: { id: 1 }, error: null },
          { source_filename: 'bad.txt', status: 'error', dataset: null,
            error: 'Unsupported file type: .txt' },
        ],
        created: 1, failed: 1, mode: 'separate',
      })
    })

    it('lists which files failed, and why', async () => {
      show()
      pick([file('good.csv'), file('bad.txt')])
      submit()

      expect(await screen.findByText('bad.txt')).toBeTruthy()
      expect(screen.getByText(/Unsupported file type/)).toBeTruthy()
    })

    it('stays on the page so the errors survive', async () => {
      show()
      pick([file('good.csv'), file('bad.txt')])
      submit()

      await screen.findByText('bad.txt')
      expect(navigate).not.toHaveBeenCalled()
    })

    it('lets the user try again rather than leaving the button spinning', async () => {
      show()
      pick([file('good.csv'), file('bad.txt')])
      submit()

      await screen.findByText('bad.txt')
      const button = screen.getByText('Upload', { selector: 'button' }) as HTMLButtonElement
      expect(button.disabled).toBe(false)
    })
  })

  describe('upload in progress', () => {
    it('shows a dedicated loading state while the upload is in flight, not just the button label', async () => {
      // Distinct wording from the button's own "Uploading…" label -- this proves
      // a SEPARATE, more visible affordance exists, not a re-match of the button.
      let resolveUpload: (v: any) => void
      ;(datasetsApi.upload as any).mockReturnValue(new Promise(res => { resolveUpload = res }))
      show()
      pick([file('solo.csv')])
      submit()

      await waitFor(() => expect(screen.getByText(/uploading and processing/i)).toBeInTheDocument())
      resolveUpload!({ id: 7, name: 'one' })
    })
  })

  it('renders the errors when the whole request is rejected', async () => {
    // A total failure comes back as an HTTP error carrying the same body.
    ;(datasetsApi.uploadBatch as any).mockRejectedValue({
      response: { data: { detail: {
        items: [{ source_filename: 'x.txt', status: 'error', dataset: null,
                  error: 'Unsupported file type: .txt' }],
        created: 0, failed: 1, mode: 'separate',
      } } },
    })

    show()
    pick([file('x.txt'), file('y.txt')])
    submit()

    expect(await screen.findByText('x.txt')).toBeTruthy()
    expect(navigate).not.toHaveBeenCalled()
  })
})

describe('the name a batch suggests', () => {
  // The server appends each file's own stem to this base, so seeding it with
  // the first file's whole stem put that stem in twice -- the duplicated
  // "qa_sample" fragment QA saw in the dataset list.
  it('uses what the file names share, not the first one whole', () => {
    expect(batchBaseName([file('qa_sample.csv'), file('qa_sample2.csv')]))
      .toBe('qa_sample')
  })

  it('trims a trailing separator off the shared prefix', () => {
    expect(batchBaseName([file('q3_sales.csv'), file('q3_costs.csv')]))
      .toBe('q3')
  })

  it('falls back to the first stem when the files share nothing', () => {
    expect(batchBaseName([file('sales.csv'), file('costs.csv')]))
      .toBe('sales')
  })

  it('keeps a single file\'s own stem', () => {
    expect(batchBaseName([file('sales.csv')])).toBe('sales')
  })
})

describe('a name that is already taken (BUG-027)', () => {
  it('says so while typing, without blocking the upload', async () => {
    ;(datasetsApi.list as any).mockResolvedValue([{ id: 3, name: 'Sales 2024' }])
    show()
    await waitFor(() => expect(datasetsApi.list).toHaveBeenCalled())
    const input = screen.getByPlaceholderText('My dataset')
    fireEvent.change(input, { target: { value: '  sales 2024 ' } })
    expect(await screen.findByRole('status')).toHaveTextContent('You already have a dataset named "sales 2024"')

    pick([file('x.csv')])
    submit()
    await waitFor(() => expect(datasetsApi.upload).toHaveBeenCalled())
  })

  it('stays quiet for a new name, or when the list cannot be read', async () => {
    ;(datasetsApi.list as any).mockRejectedValue(new Error('offline'))
    show()
    fireEvent.change(screen.getByPlaceholderText('My dataset'), { target: { value: 'Sales 2024' } })
    await waitFor(() => expect(datasetsApi.list).toHaveBeenCalled())
    expect(screen.queryByText(/already have a dataset/)).toBeNull()
  })
})
