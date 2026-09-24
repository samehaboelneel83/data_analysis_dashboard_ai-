import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DataView from './DataView'
import { dataPreviewApi } from '../../services/api'
import { AuthContext } from '../../contexts/AuthContext'

vi.mock('../../services/api', () => ({
  dataPreviewApi: { query: vi.fn() },
  prepApi: { get: vi.fn().mockResolvedValue([]), set: vi.fn(), preview: vi.fn() },
  dataViewsApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn(), apply: vi.fn(), delete: vi.fn(), setDefault: vi.fn() },
}))

describe('DataView', () => {
  it('renders a table of the dataset rows', async () => {
    vi.mocked(dataPreviewApi.query).mockResolvedValue({
      columns: ['region', 'revenue'], rows: [['east', 100], ['west', 50]], total: 2,
    })
    render(<DataView datasetId={10} />)
    expect(await screen.findByText('east')).toBeInTheDocument()
    expect(screen.getByText('west')).toBeInTheDocument()
    expect(dataPreviewApi.query).toHaveBeenCalledWith(10, [], [], 100, 0, undefined, 'asc', undefined)
  })

  it('shows a loading state before data arrives', () => {
    vi.mocked(dataPreviewApi.query).mockReturnValue(new Promise(() => {}))
    render(<DataView datasetId={10} />)
    expect(screen.getByText(/Loading/i)).toBeInTheDocument()
  })

  it('fetches and renders rows for DirectQuery datasets too', async () => {
    vi.mocked(dataPreviewApi.query).mockReset()
    vi.mocked(dataPreviewApi.query).mockResolvedValue({
      columns: ['region', 'revenue'], rows: [['north', 40]], total: 1,
    })
    render(<DataView datasetId={10} mode="directquery" />)
    expect(await screen.findByText('north')).toBeInTheDocument()
    expect(dataPreviewApi.query).toHaveBeenCalledWith(10, [], [], 100, 0, undefined, 'asc', undefined)
  })
})

describe('DataView paging, sorting and search', () => {
  beforeEach(() => {
    vi.mocked(dataPreviewApi.query).mockResolvedValue({
      columns: ['region', 'sales'],
      rows: Array.from({ length: 100 }, (_, i) => [`R${i}`, i]),
      total: 350,
    })
  })

  it('pages forward and back with server-side offsets', async () => {
    render(<DataView datasetId={10} />)
    await screen.findByText(/Page 1 of 4/)
    fireEvent.click(screen.getByRole('button', { name: /Next/ }))
    await waitFor(() => expect(dataPreviewApi.query).toHaveBeenLastCalledWith(
      10, [], [], 100, 100, undefined, 'asc', undefined))
    await screen.findByText(/Page 2 of 4/)
    fireEvent.click(screen.getByRole('button', { name: /Prev/ }))
    await waitFor(() => expect(dataPreviewApi.query).toHaveBeenLastCalledWith(
      10, [], [], 100, 0, undefined, 'asc', undefined))
  })

  it('clicking a header cycles sort asc -> desc -> off, resetting to page 1', async () => {
    render(<DataView datasetId={10} />)
    await screen.findByText(/Page 1 of 4/)
    fireEvent.click(screen.getByRole('columnheader', { name: /sales/ }))
    await waitFor(() => expect(dataPreviewApi.query).toHaveBeenLastCalledWith(
      10, [], [], 100, 0, 'sales', 'asc', undefined))
    fireEvent.click(screen.getByRole('columnheader', { name: /sales/ }))
    await waitFor(() => expect(dataPreviewApi.query).toHaveBeenLastCalledWith(
      10, [], [], 100, 0, 'sales', 'desc', undefined))
    fireEvent.click(screen.getByRole('columnheader', { name: /sales/ }))
    await waitFor(() => expect(dataPreviewApi.query).toHaveBeenLastCalledWith(
      10, [], [], 100, 0, undefined, 'asc', undefined))
  })

  it('search submits on Enter and clears', async () => {
    render(<DataView datasetId={10} />)
    await screen.findByText(/Page 1 of 4/)
    const box = screen.getByLabelText('Search rows')
    fireEvent.change(box, { target: { value: 'North' } })
    fireEvent.keyDown(box, { key: 'Enter' })
    await waitFor(() => expect(dataPreviewApi.query).toHaveBeenLastCalledWith(
      10, [], [], 100, 0, undefined, 'asc', 'North'))
    await screen.findByText(/filtered/)
    fireEvent.click(screen.getByRole('button', { name: /Clear/ }))
    await waitFor(() => expect(dataPreviewApi.query).toHaveBeenLastCalledWith(
      10, [], [], 100, 0, undefined, 'asc', undefined))
  })
})

describe('the admin default reaches the data views bar', () => {
  /**
   * The reachability half. `DataViewsBar` takes `isAdmin` and hides the
   * "default for new datasets" control without it — so a bar mounted without
   * that prop would render a control nobody could ever see, which is precisely
   * how several features in this codebase came to have no caller.
   */
  it('an org admin sees the default control', async () => {
    const { dataViewsApi } = await import('../../services/api')
    vi.mocked(dataViewsApi.list).mockResolvedValue(
      [{ id: 3, name: 'Sales semantics', pieces: [], is_default: false }] as never)
    vi.mocked(dataPreviewApi.query).mockResolvedValue(
      { columns: ['a'], rows: [[1]], total: 1 } as never)

    render(
      <AuthContext.Provider value={{
        user: { id: 1, email: 'a@b.c', is_active: true,
          organization: { id: 1, name: 'Org' },
          role: { id: 1, name: 'Admin', is_org_admin: true } },
        loading: false, login: vi.fn(), logout: vi.fn() } as never}>
        <DataView datasetId={7} mode="import" />
      </AuthContext.Provider>
    )
    fireEvent.change(await screen.findByLabelText('Saved data views'), { target: { value: '3' } })
    expect(await screen.findByLabelText(/default for new datasets/i)).toBeInTheDocument()
  })

  it('an ordinary member does not', async () => {
    const { dataViewsApi } = await import('../../services/api')
    vi.mocked(dataViewsApi.list).mockResolvedValue(
      [{ id: 3, name: 'Sales semantics', pieces: [], is_default: false }] as never)
    vi.mocked(dataPreviewApi.query).mockResolvedValue(
      { columns: ['a'], rows: [[1]], total: 1 } as never)

    render(
      <AuthContext.Provider value={{
        user: { id: 2, email: 'm@b.c', is_active: true,
          organization: { id: 1, name: 'Org' },
          role: { id: 2, name: 'Analyst', is_org_admin: false } },
        loading: false, login: vi.fn(), logout: vi.fn() } as never}>
        <DataView datasetId={7} mode="import" />
      </AuthContext.Provider>
    )
    fireEvent.change(await screen.findByLabelText('Saved data views'), { target: { value: '3' } })
    await waitFor(() =>
      expect(screen.queryByLabelText(/default for new datasets/i)).not.toBeInTheDocument())
  })
})
