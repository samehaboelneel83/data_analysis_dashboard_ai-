import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders as render, screen, fireEvent, waitFor, within } from '../test/renderWithProviders'
import QueryBuilderDialog from './QueryBuilderDialog'
import { dataSourcesApi, queryBuilderApi } from '../services/api'
import type { DataSource } from '../services/api'

vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))
vi.mock('../services/api', () => ({
  dataSourcesApi: { schema: vi.fn(), import: vi.fn() },
  queryBuilderApi: { columns: vi.fn(), compile: vi.fn(), preview: vi.fn(), functions: vi.fn().mockResolvedValue([]) },
}))

const ds = { id: 5, name: 'Shop DB', type: 'sqlite', config: {} } as unknown as DataSource

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(dataSourcesApi.schema).mockResolvedValue({ tables: [
    { name: 'orders', kind: 'table' }, { name: 'customers', kind: 'table' }] })
  vi.mocked(queryBuilderApi.columns).mockResolvedValue([
    { name: 'region', type: 'TEXT' }, { name: 'amount', type: 'REAL' }])
  vi.mocked(queryBuilderApi.compile).mockResolvedValue({ sql: 'SELECT ...' })
  vi.mocked(queryBuilderApi.preview).mockResolvedValue({ columns: ['region'], rows: [['US']], sql: 'SELECT ...' })
  vi.mocked(dataSourcesApi.import).mockResolvedValue({ id: 42, name: 'Built', row_count: 3, col_count: 2, mode: 'import' })
})

async function buildBasicQuery() {
  render(<QueryBuilderDialog ds={ds} onClose={() => {}} />)
  fireEvent.change(await screen.findByLabelText('Base table'), { target: { value: 'orders' } })
  await waitFor(() => expect(queryBuilderApi.columns).toHaveBeenCalledWith(5, 'orders'))
  fireEvent.click(screen.getByRole('button', { name: '+ Add column' }))
  await waitFor(() => expect(screen.getByLabelText('Column 1')).toBeInTheDocument())
  fireEvent.change(screen.getByLabelText('Column 1'), { target: { value: 'region' } })
}

describe('QueryBuilderDialog', () => {
  it('compiles live SQL once a table and column are chosen', async () => {
    await buildBasicQuery()
    await waitFor(() => expect(queryBuilderApi.compile).toHaveBeenCalled(), { timeout: 2000 })
    const model = vi.mocked(queryBuilderApi.compile).mock.calls[0][1] as { table: string; columns: { column: string }[] }
    expect(model.table).toBe('orders')
    expect(model.columns[0].column).toBe('region')
    await waitFor(() => expect(screen.getByTestId('qb-sql')).toHaveTextContent('SELECT ...'))
  })

  it('previews data and shows the rows', async () => {
    await buildBasicQuery()
    await waitFor(() => expect(screen.getByTestId('qb-sql')).toHaveTextContent('SELECT ...'), { timeout: 2000 })
    fireEvent.click(screen.getByRole('button', { name: 'Preview data' }))
    expect(await screen.findByText('US')).toBeInTheDocument()
  })

  it('creates a dataset from the compiled SQL, sending the model for later editing', async () => {
    const onClose = vi.fn()
    render(<QueryBuilderDialog ds={ds} onClose={onClose} />)
    fireEvent.change(await screen.findByLabelText('Base table'), { target: { value: 'orders' } })
    fireEvent.click(screen.getByRole('button', { name: '+ Add column' }))
    await waitFor(() => expect(screen.getByLabelText('Column 1')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Column 1'), { target: { value: 'region' } })
    await waitFor(() => expect(screen.getByTestId('qb-sql')).toHaveTextContent('SELECT ...'), { timeout: 2000 })
    fireEvent.change(screen.getByLabelText('Dataset name'), { target: { value: 'Built revenue' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create dataset' }))
    await waitFor(() => expect(dataSourcesApi.import).toHaveBeenCalled())
    const call = vi.mocked(dataSourcesApi.import).mock.calls[0]
    expect(call.slice(0, 4)).toEqual([5, 'Built revenue', undefined, 'SELECT ...'])
    expect(call[4]).toBe('import')
    expect((call[5] as { table: string }).table).toBe('orders')
    expect(call[6]).toBeUndefined()   // no dataset_id -- this is a create, not an edit
    expect(onClose).toHaveBeenCalled()
  })

  it('hydrates the canvas from a saved query_model when reopened for editing', async () => {
    render(<QueryBuilderDialog ds={ds} onClose={() => {}}
      existing={{ id: 42, name: 'Built revenue', query_model: {
        table: 'orders',
        columns: [{ column: 'region' }, { column: 'amount', aggregation: 'sum', alias: 'total' }],
        filters: [{ column: 'amount', op: 'gte', value: 10 }],
        sort: [{ alias: 'total', dir: 'desc' }],
        limit: 500,
      } }} />)
    expect(await screen.findByLabelText('Base table')).toHaveValue('orders')
    expect(await screen.findByLabelText('Dataset name')).toHaveValue('Built revenue')
    await waitFor(() => expect(screen.getByLabelText('Column 1')).toHaveValue('region'))
    expect(screen.getByLabelText('Aggregation 2')).toHaveValue('sum')
    expect(screen.getByLabelText('Alias 2')).toHaveValue('total')
    expect(screen.getByLabelText('Value of condition 1')).toHaveValue('10')
    expect(screen.getByLabelText('Sort alias')).toHaveValue('total')
    expect(screen.getByLabelText('Row limit')).toHaveValue(500)
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument()
  })

  describe('D2: Design | SQL tabs', () => {
    it('the SQL tab shows the generated SQL, read-only, matching the canvas', async () => {
      await buildBasicQuery()
      await waitFor(() => expect(screen.getByTestId('qb-sql')).toHaveTextContent('SELECT ...'), { timeout: 2000 })
      fireEvent.click(screen.getByRole('tab', { name: 'SQL' }))
      const editor = await screen.findByLabelText('SQL editor') as HTMLTextAreaElement
      expect(editor).toHaveValue('SELECT ...')
      expect(editor).toHaveAttribute('readonly')
    })

    it('unlocking then typing switches to script mode and greys the Design tab', async () => {
      await buildBasicQuery()
      await waitFor(() => expect(screen.getByTestId('qb-sql')).toHaveTextContent('SELECT ...'), { timeout: 2000 })
      fireEvent.click(screen.getByRole('tab', { name: 'SQL' }))
      fireEvent.click(screen.getByRole('button', { name: 'Edit SQL manually' }))
      const editor = await screen.findByLabelText('SQL editor') as HTMLTextAreaElement
      expect(editor).not.toHaveAttribute('readonly')

      fireEvent.change(editor, { target: { value: 'SELECT * FROM orders WHERE 1=1' } })
      expect(editor).toHaveValue('SELECT * FROM orders WHERE 1=1')

      fireEvent.click(screen.getByRole('tab', { name: 'Design' }))
      expect(screen.getByRole('alert')).toHaveTextContent('Manual SQL')
      // the underlying design fields are untouched -- script mode never
      // reverse-parses SQL back into the graph
      expect(screen.getByLabelText('Base table')).toHaveValue('orders')
      expect(screen.getByLabelText('Column 1')).toHaveValue('region')
    })

    it('script-mode create() sends the hand-edited SQL with no query_model', async () => {
      await buildBasicQuery()
      await waitFor(() => expect(screen.getByTestId('qb-sql')).toHaveTextContent('SELECT ...'), { timeout: 2000 })
      fireEvent.click(screen.getByRole('tab', { name: 'SQL' }))
      fireEvent.click(screen.getByRole('button', { name: 'Edit SQL manually' }))
      const editor = await screen.findByLabelText('SQL editor')
      fireEvent.change(editor, { target: { value: 'SELECT * FROM orders WHERE 1=1' } })
      fireEvent.change(screen.getByLabelText('Dataset name'), { target: { value: 'Hand tuned' } })
      fireEvent.click(screen.getByRole('button', { name: 'Create dataset' }))
      await waitFor(() => expect(dataSourcesApi.import).toHaveBeenCalled())
      const call = vi.mocked(dataSourcesApi.import).mock.calls[0]
      expect(call.slice(0, 4)).toEqual([5, 'Hand tuned', undefined, 'SELECT * FROM orders WHERE 1=1'])
      expect(call[5]).toBeUndefined()   // no model -- one-way, not re-editable visually
    })

    // Driven through the real ConfirmDialog. The old stub of window.confirm
    // could not distinguish "the user declined" from "no dialog ever opened",
    // so the decline case passed even when the guard was absent.
    const openRevertDialog = async () => {
      await buildBasicQuery()
      await waitFor(() => expect(screen.getByTestId('qb-sql')).toHaveTextContent('SELECT ...'), { timeout: 2000 })
      fireEvent.click(screen.getByRole('tab', { name: 'SQL' }))
      fireEvent.click(screen.getByRole('button', { name: 'Edit SQL manually' }))
      const editor = await screen.findByLabelText('SQL editor')
      fireEvent.change(editor, { target: { value: 'garbage sql' } })
      fireEvent.click(screen.getByRole('button', { name: 'Return to Design' }))
      return editor
    }

    it('"Return to Design" (confirmed) discards the manual edit and regenerates from the model', async () => {
      await openRevertDialog()
      // Scoped to the dialog: the trigger carries the same label, so an
      // unscoped query matches both.
      const dialog = await screen.findByRole('alertdialog')
      fireEvent.click(within(dialog).getByRole('button', { name: 'Return to Design' }))
      await waitFor(() => expect(screen.getByLabelText('SQL editor')).toHaveValue('SELECT ...'))
      expect(screen.getByLabelText('SQL editor')).toHaveAttribute('readonly')
    })

    it('declining the confirm on "Return to Design" keeps the manual edit', async () => {
      const editor = await openRevertDialog()
      // The dialog really opened -- this is what the window.confirm stub could
      // not assert, and it is the half that proves the action is guarded.
      expect(await screen.findByRole('alertdialog')).toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
      await waitFor(() =>
        expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
      expect(editor).toHaveValue('garbage sql')
    })
  })

  it('re-import in edit mode sends the existing dataset id, updating in place', async () => {
    render(<QueryBuilderDialog ds={ds} onClose={() => {}}
      existing={{ id: 42, name: 'Built revenue', query_model: {
        table: 'orders', columns: [{ column: 'region' }],
      } }} />)
    await waitFor(() => expect(screen.getByLabelText('Column 1')).toHaveValue('region'))
    await waitFor(() => expect(screen.getByTestId('qb-sql')).toHaveTextContent('SELECT ...'), { timeout: 2000 })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(dataSourcesApi.import).toHaveBeenCalled())
    const call = vi.mocked(dataSourcesApi.import).mock.calls[0]
    expect(call[6]).toBe(42)
  })

  describe('D3: canvas column picking', () => {
    it('checking a canvas column checkbox adds it to the Columns rows below', async () => {
      render(<QueryBuilderDialog ds={ds} onClose={() => {}} />)
      fireEvent.change(await screen.findByLabelText('Base table'), { target: { value: 'orders' } })
      await waitFor(() => expect(screen.getByTestId(`canvas-table-orders`)).toBeInTheDocument())
      fireEvent.click(screen.getByLabelText('Include orders.region'))
      await waitFor(() => expect(screen.getByLabelText('Column 1')).toHaveValue('region'))
      // unchecking removes the row again -- two-way sync, one source of truth
      fireEvent.click(screen.getByLabelText('Include orders.region'))
      await waitFor(() => expect(screen.queryByLabelText('Column 1')).not.toBeInTheDocument())
    })

    it('adding a column via the form row below checks its canvas checkbox', async () => {
      await buildBasicQuery()
      await waitFor(() => expect(screen.getByLabelText('Include orders.region') as HTMLInputElement)
        .toHaveProperty('checked', true))
    })

    it('the canvas aggregation badge cycles through none/sum/avg/count/min/max and drives GROUP BY', async () => {
      await buildBasicQuery()
      const badge = await screen.findByLabelText('Aggregation orders.region')
      expect(badge).toHaveTextContent('raw')
      fireEvent.click(badge)
      await waitFor(() => expect(screen.getByLabelText('Aggregation 1')).toHaveValue('sum'))
      expect(badge).toHaveTextContent('sum')
      await waitFor(() => expect(queryBuilderApi.compile).toHaveBeenCalled(), { timeout: 2000 })
      const model = vi.mocked(queryBuilderApi.compile).mock.calls.at(-1)![1] as { columns: { aggregation?: string }[] }
      expect(model.columns[0].aggregation).toBe('sum')
    })
  })

  describe('D3: WHERE builder AND/OR', () => {
    it('a second filter row exposes a Match AND/OR selector, sent as filters_joiner', async () => {
      await buildBasicQuery()
      fireEvent.click(screen.getByRole('button', { name: '+ Condition' }))
      fireEvent.click(screen.getByRole('button', { name: '+ Condition' }))
      await waitFor(() => expect(screen.getByLabelText('Column of condition 1')).toBeInTheDocument())
      fireEvent.change(screen.getByLabelText('Column of condition 1'), { target: { value: 'region' } })
      fireEvent.change(screen.getByLabelText('Value of condition 1'), { target: { value: 'US' } })
      fireEvent.change(screen.getByLabelText('Column of condition 2'), { target: { value: 'amount' } })
      fireEvent.change(screen.getByLabelText('Comparison of condition 2'), { target: { value: 'gte' } })
      fireEvent.change(screen.getByLabelText('Value of condition 2'), { target: { value: '10' } })
      fireEvent.change(screen.getByLabelText('How the conditions in Rows to keep combine'), { target: { value: 'or' } })
      await waitFor(() => expect(queryBuilderApi.compile).toHaveBeenCalled(), { timeout: 2000 })
      const model = vi.mocked(queryBuilderApi.compile).mock.calls.at(-1)![1] as { filters_joiner?: string }
      expect(model.filters_joiner).toBe('or')
      expect(screen.getByTestId('qb-where-preview')).toHaveTextContent("region = 'US' OR amount >= 10")
    })
  })

  describe('condition boxes (query builder plan step 2)', () => {
    it('a group inside the conditions is sent as a nested group', async () => {
      await buildBasicQuery()
      fireEvent.click(screen.getByRole('button', { name: '+ Condition' }))
      fireEvent.change(await screen.findByLabelText('Column of condition 1'), { target: { value: 'region' } })
      fireEvent.change(screen.getByLabelText('Value of condition 1'), { target: { value: 'US' } })
      // "+ Group" adds a box (with one empty condition) whose joiner is the other one: OR inside AND.
      fireEvent.click(within(screen.getByTestId('qb-conditions')).getAllByRole('button', { name: '+ Group' })[0])
      const group = await screen.findByTestId('qb-condition-group')
      fireEvent.click(within(group).getByRole('button', { name: '+ Condition' }))
      fireEvent.change(screen.getByLabelText('Column of condition 2'), { target: { value: 'amount' } })
      fireEvent.change(screen.getByLabelText('Comparison of condition 2'), { target: { value: 'gte' } })
      fireEvent.change(screen.getByLabelText('Value of condition 2'), { target: { value: '10' } })
      fireEvent.change(screen.getByLabelText('Column of condition 3'), { target: { value: 'amount' } })
      fireEvent.change(screen.getByLabelText('Comparison of condition 3'), { target: { value: 'is_null' } })
      await waitFor(() => {
        const model = vi.mocked(queryBuilderApi.compile).mock.calls.at(-1)![1] as { filters: unknown[] }
        expect(model.filters).toEqual([
          { table: 'orders', column: 'region', op: 'eq', value: 'US' },
          { group: 'or', filters: [
            { table: 'orders', column: 'amount', op: 'gte', value: 10 },
            { table: 'orders', column: 'amount', op: 'is_null' }] },
        ])
      }, { timeout: 2000 })
      expect(screen.getByTestId('qb-where-preview')).toHaveTextContent("region = 'US' AND (amount >= 10 OR amount IS NULL)")
    })

    it('an unfinished condition says what it needs and is left out', async () => {
      await buildBasicQuery()
      fireEvent.click(screen.getByRole('button', { name: '+ Condition' }))
      fireEvent.change(await screen.findByLabelText('Column of condition 1'), { target: { value: 'region' } })
      expect(screen.getByRole('status')).toHaveTextContent('Type a value')
      await waitFor(() => expect(queryBuilderApi.compile).toHaveBeenCalled(), { timeout: 2000 })
      const model = vi.mocked(queryBuilderApi.compile).mock.calls.at(-1)![1] as { filters: unknown[] }
      expect(model.filters).toEqual([])
    })

    it('reopening keeps groups and a sub-query condition (it used to be dropped)', async () => {
      const sub = { table: 'customers', columns: [{ column: 'region' }] }
      render(<QueryBuilderDialog ds={ds} onClose={() => {}}
        existing={{ id: 42, name: 'Built revenue', query_model: {
          table: 'orders', columns: [{ column: 'region' }],
          filters: [{ group: 'or', filters: [{ column: 'region', op: 'eq', value: 'US' },
            { column: 'region', op: 'eq', value: 'EU' }] },
          { column: 'region', op: 'in', subquery: sub }],
        } }} />)
      expect(await screen.findByTestId('qb-condition-group')).toBeInTheDocument()
      expect(screen.getByTestId('qb-condition-kept')).toHaveTextContent('region')
      await waitFor(() => {
        const model = vi.mocked(queryBuilderApi.compile).mock.calls.at(-1)?.[1] as { filters: unknown[] } | undefined
        expect(model?.filters).toEqual([
          { group: 'or', filters: [{ table: 'orders', column: 'region', op: 'eq', value: 'US' },
            { table: 'orders', column: 'region', op: 'eq', value: 'EU' }] },
          { column: 'region', op: 'in', subquery: sub },
        ])
      }, { timeout: 2000 })
    })
  })

  it('D1 round-trip: reopening hydrates filters_joiner from the saved query_model', async () => {
    render(<QueryBuilderDialog ds={ds} onClose={() => {}}
      existing={{ id: 42, name: 'Built revenue', query_model: {
        table: 'orders',
        columns: [{ column: 'region' }],
        filters: [{ column: 'region', op: 'eq', value: 'US' }, { column: 'amount', op: 'gte', value: 10 }],
        filters_joiner: 'or',
      } }} />)
    await waitFor(() => expect(screen.getByLabelText('How the conditions in Rows to keep combine')).toHaveValue('or'))
  })

  it('D3: canvas checkboxes are disabled (greyed) in script mode', async () => {
    await buildBasicQuery()
    await waitFor(() => expect(screen.getByTestId('qb-sql')).toHaveTextContent('SELECT ...'), { timeout: 2000 })
    fireEvent.click(screen.getByRole('tab', { name: 'SQL' }))
    fireEvent.click(screen.getByRole('button', { name: 'Edit SQL manually' }))
    fireEvent.change(await screen.findByLabelText('SQL editor'), { target: { value: 'SELECT * FROM orders' } })
    fireEvent.click(screen.getByRole('tab', { name: 'Design' }))
    const designPane = screen.getByLabelText('Include orders.region').closest('[aria-hidden]')
    expect(designPane).toHaveStyle({ pointerEvents: 'none' })
  })

  it('surfaces the compile validation error verbatim', async () => {
    vi.mocked(queryBuilderApi.compile).mockRejectedValue(
      { response: { data: { detail: "column 'ghost' does not exist on table 'orders'" } } })
    await buildBasicQuery()
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('does not exist'), { timeout: 2000 })
  })
})

describe('QueryBuilderDialog — grouping and HAVING', () => {
  it('offers no Having editor until something aggregates', async () => {
    // WHERE runs before grouping, so HAVING only means anything once a column
    // aggregates. Offering it earlier would be a form the compiler rejects.
    await buildBasicQuery()
    expect(screen.queryByTestId('qb-having')).not.toBeInTheDocument()
  })

  it('reveals Having once a column aggregates, and sends it in the model', async () => {
    await buildBasicQuery()
    fireEvent.change(screen.getByLabelText('Aggregation 1'), { target: { value: 'sum' } })

    const having = await screen.findByTestId('qb-having')
    fireEvent.click(within(having).getByRole('button', { name: '+ Add having' }))
    fireEvent.change(screen.getByLabelText('Having column 1'), { target: { value: 'amount' } })
    fireEvent.change(screen.getByLabelText('Having value 1'), { target: { value: '1000' } })

    await waitFor(() => {
      const calls = vi.mocked(queryBuilderApi.compile).mock.calls
      const model = calls[calls.length - 1][1] as { having?: { column: string; op: string; value: unknown }[] }
      expect(model.having?.[0]).toMatchObject({ column: 'amount', op: 'gt', value: 1000 })
    }, { timeout: 2000 })
  })
})

describe('QueryBuilderDialog — self-referencing hierarchy', () => {
  it('is off by default, so an ordinary query is unaffected', async () => {
    await buildBasicQuery()
    const box = screen.getByLabelText('Walk a self-referencing hierarchy')
    expect(box).not.toBeChecked()
    expect(screen.queryByLabelText('Hierarchy id column')).not.toBeInTheDocument()
  })

  it('sends a hierarchy spec and points the base at the CTE', async () => {
    await buildBasicQuery()
    fireEvent.click(screen.getByLabelText('Walk a self-referencing hierarchy'))
    fireEvent.change(screen.getByLabelText('Hierarchy table'), { target: { value: 'orders' } })
    fireEvent.change(screen.getByLabelText('Hierarchy id column'), { target: { value: 'region' } })
    fireEvent.change(screen.getByLabelText('Hierarchy parent column'), { target: { value: 'amount' } })

    await waitFor(() => {
      const calls = vi.mocked(queryBuilderApi.compile).mock.calls
      const m = calls[calls.length - 1][1] as {
        table: string; hierarchy?: { table: string; id_column: string; parent_column: string } }
      // The CTE becomes the base table -- that is what lets joins, filters and
      // grouping treat the walk as an ordinary source.
      expect(m.table).toBe('hierarchy')
      expect(m.hierarchy).toEqual({
        table: 'orders', id_column: 'region', parent_column: 'amount' })
    }, { timeout: 2000 })
  })

  it('offers the generated columns wherever a column is picked', async () => {
    await buildBasicQuery()
    fireEvent.click(screen.getByLabelText('Walk a self-referencing hierarchy'))
    fireEvent.change(screen.getByLabelText('Hierarchy table'), { target: { value: 'orders' } })

    // __level/__path/__root_id do not exist on the source table; they exist on
    // the CTE, and the pickers must know that or the feature is unusable.
    const picker = screen.getByLabelText('Hierarchy id column') as HTMLSelectElement
    const options = Array.from(picker.options).map(o => o.value)
    expect(options).toContain('region')
    expect(options).not.toContain('__level')   // the SOURCE table's columns only
  })

  describe('3.9: joins drawn on the diagram', () => {
    async function withCustomersOnCanvas() {
      render(<QueryBuilderDialog ds={ds} onClose={() => {}} />)
      fireEvent.change(await screen.findByLabelText('Base table'), { target: { value: 'orders' } })
      await waitFor(() => expect(screen.getByTestId('canvas-table-orders')).toBeInTheDocument())
      fireEvent.change(screen.getByLabelText('Add table to canvas'), { target: { value: 'customers' } })
      await waitFor(() => expect(screen.getByTestId('canvas-table-customers')).toBeInTheDocument())
      await waitFor(() => expect(within(screen.getByTestId('canvas-table-customers')).getByText('region')).toBeInTheDocument())
    }

    it('a line drawn from the joined table back to the base still joins the new table', async () => {
      await withCustomersOnCanvas()
      fireEvent.click(within(screen.getByTestId('canvas-table-customers')).getByText('region'))
      fireEvent.click(within(screen.getByTestId('canvas-table-orders')).getByText('region'))
      await waitFor(() => expect(screen.getByLabelText('Join table 1')).toHaveValue('customers'))
      expect(screen.getByLabelText('Join 1 base key')).toHaveValue('region')
      expect(screen.getByLabelText('Join 1 joined key')).toHaveValue('region')
    })

    it('keeps the join type chosen on the row before the line was drawn', async () => {
      await withCustomersOnCanvas()
      fireEvent.change(screen.getByLabelText('Join type 1'), { target: { value: 'inner' } })
      fireEvent.click(within(screen.getByTestId('canvas-table-orders')).getByText('region'))
      fireEvent.click(within(screen.getByTestId('canvas-table-customers')).getByText('region'))
      await waitFor(() => expect(screen.getByTestId('join-label-0')).toHaveTextContent('inner'))
      expect(screen.getByLabelText('Join type 1')).toHaveValue('inner')
    })

    it('a type picked on the diagram (full outer) shows in the form, not as "left"', async () => {
      await withCustomersOnCanvas()
      fireEvent.click(within(screen.getByTestId('canvas-table-orders')).getByText('region'))
      fireEvent.click(within(screen.getByTestId('canvas-table-customers')).getByText('region'))
      fireEvent.click(await screen.findByTestId('join-label-0'))
      fireEvent.click(screen.getByRole('menuitemradio', { name: /Full outer/ }))
      await waitFor(() => expect(screen.getByLabelText('Join type 1')).toHaveValue('full'))
    })

    it('a second join can take its key from the first joined table', async () => {
      vi.mocked(dataSourcesApi.schema).mockResolvedValue({ tables: [
        { name: 'orders', kind: 'table' }, { name: 'customers', kind: 'table' }, { name: 'regions', kind: 'table' }] })
      await withCustomersOnCanvas()
      fireEvent.click(screen.getByRole('button', { name: '+ Add join' }))
      const from = await screen.findByLabelText('Join 2 from table')
      expect(within(from).getAllByRole('option').map(o => o.textContent)).toEqual(['orders', 'customers'])
      fireEvent.change(from, { target: { value: 'customers' } })
      expect(screen.getByLabelText('Join 2 from table')).toHaveValue('customers')
    })
  })


  describe('4.1: Current rows only', () => {
    it('offers one tick per history table and sends current_only', async () => {
      vi.mocked(queryBuilderApi.columns).mockResolvedValue([
        { name: 'emp_no', type: 'INT' }, { name: 'dept_no', type: 'TEXT' }, { name: 'to_date', type: 'DATE' }])
      render(<QueryBuilderDialog ds={ds} onClose={() => {}} />)
      fireEvent.change(await screen.findByLabelText('Base table'), { target: { value: 'orders' } })
      const tick = await screen.findByLabelText('Current rows only in orders')
      fireEvent.click(screen.getByRole('button', { name: '+ Add column' }))
      fireEvent.change(await screen.findByLabelText('Column 1'), { target: { value: 'dept_no' } })
      fireEvent.click(tick)
      await waitFor(() => {
        const last = vi.mocked(queryBuilderApi.compile).mock.calls.at(-1)!
        expect(JSON.stringify(last)).toContain('"current_only":[{"table":"orders","column":"to_date"}]')
      })
    })

    it('shows nothing for tables without an end date', async () => {
      await buildBasicQuery()
      expect(screen.queryByTestId('qb-current-only')).not.toBeInTheDocument()
    })
  })

})
