import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Upload, { batchBaseName } from './Upload'
import { datasetsApi } from '../services/api'
import toast from 'react-hot-toast'

/**
 * The Upload page (autopilot step 5): choose, review, import. What carries
 * the risk, kept from v1: one ordinary file takes the single-file endpoint
 * and several take the batch; a partial failure keeps the per-file errors on
 * screen; a reused name or a duplicate content is said; a workbook's sheets
 * are offered when the server names them; nothing uploads twice.
 */

vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }))
vi.mock('../services/api', () => ({
  datasetsApi: { uploadWithProgress: vi.fn(), uploadBatchWithProgress: vi.fn(), list: vi.fn() },
}))

const file = (name: string, body = 'a,b\n1,2\n') => new File([body], name, { type: 'text/csv' })
const show = () => render(<MemoryRouter><Upload /></MemoryRouter>)
const settle = () => act(async () => { for (let i = 0; i < 10; i++) await Promise.resolve() })
async function pick(files: File[]) {
  const input = screen.getByTestId('upload-input') as HTMLInputElement
  Object.defineProperty(input, 'files', { value: files, configurable: true })
  fireEvent.change(input)
  await waitFor(() => expect(screen.getByRole('button', { name: /^Import/ })).toBeEnabled())
}
const importNow = () => fireEvent.click(screen.getByRole('button', { name: /^Import/ }))
const single = () => vi.mocked(datasetsApi.uploadWithProgress)
const batch = () => vi.mocked(datasetsApi.uploadBatchWithProgress)

beforeEach(() => {
  vi.clearAllMocks()
  single().mockResolvedValue({ id: 7, name: 'Sales', row_count: 2, col_count: 2, file_size: 10 } as never)
  vi.mocked(datasetsApi.list).mockResolvedValue([])
  batch().mockResolvedValue({ items: [{ source_filename: 'a.csv', status: 'created', dataset: { id: 1, name: 'a' }, error: null },
    { source_filename: 'b.csv', status: 'created', dataset: { id: 2, name: 'b' }, error: null }], created: 2, failed: 0, mode: 'separate' } as never)
})

describe('choosing', () => {
  it('starts on the drop zone, with recent uploads and tips beside it', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([
      { id: 3, name: 'Old sales', filename: '/app/uploads/x/old.csv', created_at: '2026-01-01T00:00:00Z' },
      { id: 4, name: 'From a database', filename: undefined, created_at: '2026-02-01T00:00:00Z' },
    ] as never)
    show()
    expect(screen.getByRole('heading', { name: 'Drop your files here' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Browse files' })).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: /Old sales/ })).toHaveAttribute('href', '/datasets/3')
    expect(screen.queryByText('From a database')).toBeNull()
    expect(screen.getByRole('link', { name: /Connect a database/ })).toHaveAttribute('href', '/connections')
    expect(screen.getByTestId('upload-input')).toHaveAttribute('accept', expect.stringContaining('.accdb'))
    expect(screen.getByTestId('upload-input')).toHaveAttribute('multiple')
  })

  it('shows the drop state while files are dragged over', () => {
    show()
    const zone = screen.getByRole('heading', { name: 'Drop your files here' }).closest('.dl-up-drop')!
    fireEvent.dragOver(zone)
    expect(screen.getByRole('heading', { name: 'Release to add them' })).toBeInTheDocument()
  })
})

describe('reviewing', () => {
  it('names the dataset from the file and previews its first rows, read in the browser', async () => {
    show()
    await pick([file('enrolments_2025.csv', 'id,faculty,enrolled_on\n1,Law,05/09/2025\n2,Arts,06/09/2025\n3,,07/09/2025\n')])
    expect(screen.getByRole('textbox', { name: 'Dataset name' })).toHaveValue('Enrolments 2025')
    expect(screen.getByTestId('preview-stats')).toHaveTextContent('3 rows3 columns1 empty cell')
    expect(screen.getByRole('note')).toHaveTextContent('Dates in enrolled_on could be day/month or month/day.')
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('columnheader').map(h => h.textContent)).toEqual(['idNumber', 'facultyText', 'enrolled_onDate'])
    expect(single()).not.toHaveBeenCalled()
  })

  it('says a workbook is previewed after import, and still imports it', async () => {
    show()
    await pick([new File(['x'], 'book.xlsx')])
    expect(screen.getByText(/A preview of XLSX files needs the server/)).toBeInTheDocument()
  })

  it('keeps a typed name, and says when it is already used', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([{ id: 1, name: 'Sales', filename: 'x.csv', created_at: '' }] as never)
    show()
    await pick([file('first.csv')])
    const name = screen.getByRole('textbox', { name: 'Dataset name' })
    fireEvent.change(name, { target: { value: 'Sales' } })
    expect(await screen.findByRole('status')).toHaveTextContent('You already have a dataset named "Sales"')
    fireEvent.click(screen.getByRole('button', { name: 'Add more files' }))
    await pick([file('second.csv')])
    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('Sales')
  })

  it('removes a file, and back to the start when none is left', async () => {
    show()
    await pick([file('a.csv'), file('b.csv')])
    expect(screen.getByText('2 datasets ready to import')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Remove a.csv' }))
    expect(screen.getByText('1 dataset ready to import')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Remove b.csv' }))
    expect(screen.getByRole('heading', { name: 'Drop your files here' })).toBeInTheDocument()
  })

  it('combines several files into one dataset only when asked', async () => {
    show()
    await pick([file('sales_q1.csv'), file('sales_q2.csv')])
    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('sales_q')
    const sw = screen.getByRole('switch', { name: 'Combine into one dataset' })
    expect(sw).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(sw)
    expect(screen.getByText('1 dataset ready to import')).toBeInTheDocument()
    importNow(); await settle()
    expect(batch()).toHaveBeenCalledWith(expect.any(Array), 'sales_q', '', 'append', expect.any(Function))
  })

  it('an Access file is explained, and goes through the batch even alone', async () => {
    show()
    await pick([new File(['x'], 'legacy.accdb')])
    expect(screen.getByText(/An Access database becomes one dataset per table/)).toBeInTheDocument()
    importNow(); await settle()
    expect(batch()).toHaveBeenCalled()
    expect(single()).not.toHaveBeenCalled()
  })
})

describe('importing', () => {
  it('one ordinary file: the single endpoint, its progress, then where to go next', async () => {
    let finish!: (v: unknown) => void
    single().mockImplementation((_f, _n, _d, _s, onSent) => { onSent(0.4); return new Promise(r => { finish = r }) as never })
    show()
    await pick([file('sales.csv')])
    importNow(); await settle()
    expect(screen.getByRole('heading', { name: 'Importing Sales…' })).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '40')
    finish({ id: 7, name: 'Sales', row_count: 1200, col_count: 9, file_size: 2048 }); await settle()
    expect(screen.getByRole('heading', { name: 'Dataset imported' })).toBeInTheDocument()
    expect(screen.getByText('1,200 rows')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open dataset/ })).toHaveAttribute('href', '/datasets/7?new=1')
    expect(screen.getByRole('link', { name: /Ask AI about it/ })).toHaveAttribute('href', '/ask?dataset=7')
    fireEvent.click(screen.getByRole('button', { name: /Upload another/ }))
    expect(screen.getByRole('heading', { name: 'Drop your files here' })).toBeInTheDocument()
  })

  it('does not upload twice from a double click', async () => {
    single().mockReturnValue(new Promise(() => {}) as never)
    show()
    await pick([file('sales.csv')])
    const go = screen.getByRole('button', { name: /^Import/ })
    fireEvent.click(go); fireEvent.click(go); await settle()
    expect(single()).toHaveBeenCalledTimes(1)
  })

  it('says when the content repeats a dataset you have', async () => {
    single().mockResolvedValue({ id: 8, name: 'Copy', row_count: 1, col_count: 1, duplicate_of: { id: 3, name: 'Original' } } as never)
    show()
    await pick([file('copy.csv')])
    importNow(); await settle()
    expect(screen.getByRole('note')).toHaveTextContent('It has the same content as “Original”, which you already have.')
  })

  it('several files: lists every dataset made', async () => {
    show()
    await pick([file('a.csv'), file('b.csv')])
    importNow(); await settle()
    expect(batch()).toHaveBeenCalledWith(expect.any(Array), 'a', '', 'separate', expect.any(Function))
    expect(screen.getByRole('heading', { name: '2 datasets imported' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'b' })).toHaveAttribute('href', '/datasets/2?new=1')
  })
})

describe('when it fails', () => {
  it('keeps the per-file errors of a partial batch on screen', async () => {
    batch().mockResolvedValue({ items: [{ source_filename: 'a.csv', status: 'created', dataset: { id: 1, name: 'a' }, error: null },
      { source_filename: 'b.csv', status: 'error', dataset: null, error: 'not a table' }], created: 1, failed: 1, mode: 'separate' } as never)
    show()
    await pick([file('a.csv'), file('b.csv')])
    importNow(); await settle()
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('1 imported, 1 failed')
    expect(alert).toHaveTextContent('b.csv not a table')
    expect(within(alert).getByRole('link', { name: 'Open dataset' })).toHaveAttribute('href', '/datasets/1?new=1')
  })

  it('the whole batch rejected: the errors, and Try again back to the review', async () => {
    batch().mockRejectedValue({ response: { data: { detail: { items: [{ source_filename: 'a.csv', status: 'error', dataset: null, error: 'bad' }], failed: 1 } } } })
    show()
    await pick([file('a.csv'), file('b.csv')])
    importNow(); await settle()
    expect(screen.getByRole('alert')).toHaveTextContent('a.csv bad')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(screen.getByRole('switch')).toBeInTheDocument()
  })

  it('a single file refused: the server text under Technical details', async () => {
    single().mockRejectedValue({ response: { data: { detail: 'line 3 has 7 fields' } } })
    show()
    await pick([file('sales.csv')])
    importNow(); await settle()
    expect(screen.getByRole('heading', { name: 'Couldn’t import Sales' })).toBeInTheDocument()
    expect(screen.getByText('Technical details')).toBeInTheDocument()
    expect(screen.getByText('line 3 has 7 fields')).toBeInTheDocument()
  })

  it('a workbook with several sheets: back to the review to choose one, or all', async () => {
    single().mockRejectedValueOnce({ response: { data: { detail: { message: 'several sheets', sheets: ['Jan', 'Feb'] } } } })
    show()
    await pick([new File(['x'], 'book.xlsx')])
    importNow(); await settle()
    const select = screen.getByRole('combobox', { name: 'Sheet' })
    expect(within(select).getAllByRole('option').map(o => o.textContent)).toEqual(['Jan', 'Feb', 'All sheets: one dataset each'])
    fireEvent.change(select, { target: { value: 'Feb' } })
    importNow(); await settle()
    expect(single()).toHaveBeenLastCalledWith(expect.any(File), 'Book', '', 'Feb', expect.any(Function))
  })

  it('a workbook refusal that went through the real interceptor still shows the sheet picker first (B-06)', async () => {
    const { sanitizeErrorDetail } = await import('../lib/friendlyError')
    const err = { response: { status: 400, data: { detail: { message: 'The workbook has 2 sheets', sheets: ['Sales', 'Costs'] } } } }
    sanitizeErrorDetail(err)
    expect(typeof err.response.data.detail).toBe('string')
    single().mockRejectedValueOnce(err)
    show()
    await pick([new File(['x'], 'two_sheets.xlsx')])
    importNow(); await settle()
    const select = screen.getByRole('combobox', { name: 'Sheet' })
    expect(within(select).getAllByRole('option').map(o => o.textContent)).toEqual(['Sales', 'Costs', 'All sheets: one dataset each'])
    // At the top of the review card, before the file list -- not under the fold.
    const card = select.closest('section')!
    expect(card.querySelector('.dl-up-sheet')!.compareDocumentPosition(card.querySelector('.dl-up-files')!)
      & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('a batch refusal with per-file items that went through the interceptor lists the failures (B-06)', async () => {
    const { sanitizeErrorDetail } = await import('../lib/friendlyError')
    const err = { response: { status: 400, data: { detail: { items: [
      { filename: 'b.csv', status: 'error', error: 'line 3 has 7 fields' }] } } } }
    sanitizeErrorDetail(err)
    batch().mockRejectedValueOnce(err)
    show()
    await pick([file('a.csv'), file('b.csv')])
    importNow(); await settle()
    expect(screen.getByText('line 3 has 7 fields')).toBeInTheDocument()
  })

  it('"All sheets" sends the one file to the batch', async () => {
    single().mockRejectedValueOnce({ response: { data: { detail: { message: 'x', sheets: ['Jan', 'Feb'] } } } })
    show()
    await pick([new File(['x'], 'book.xlsx')])
    importNow(); await settle()
    fireEvent.change(screen.getByRole('combobox', { name: 'Sheet' }), { target: { value: '\u0000all' } })
    importNow(); await settle()
    expect(batch()).toHaveBeenCalled()
  })

  it('asks for a name before importing', async () => {
    show()
    await pick([file('a.csv')])
    fireEvent.change(screen.getByRole('textbox', { name: 'Dataset name' }), { target: { value: '  ' } })
    importNow()
    expect(toast.error).toHaveBeenCalledWith('Give the dataset a name')
    expect(single()).not.toHaveBeenCalled()
  })
})

describe('batchBaseName', () => {
  const f = (n: string) => new File([''], n)
  it('uses what the file names share, not the first one whole', () => expect(batchBaseName([f('qa_sample.csv'), f('qa_sample2.csv')])).toBe('qa_sample'))
  it('trims a trailing separator off the shared prefix', () => expect(batchBaseName([f('sales_q1.csv'), f('sales_q2.csv')])).toBe('sales_q'))
  it('falls back to the first stem when the files share nothing', () => expect(batchBaseName([f('alpha.csv'), f('beta.csv')])).toBe('alpha'))
  it("keeps a single file's own stem", () => expect(batchBaseName([f('report.final.csv')])).toBe('report.final'))
})
