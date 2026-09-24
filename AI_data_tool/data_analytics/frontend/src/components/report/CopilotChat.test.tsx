import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import CopilotChat from './CopilotChat'
import { reportsApi } from '../../services/api'

/** The page copilot panel: opens without touching the canvas, sends the
 *  message with its own recent turns, reports what was applied, and asks the
 *  builder to reload only when something actually changed. */

beforeEach(() => vi.restoreAllMocks())

const mount = (onApplied = vi.fn()) => {
  render(<CopilotChat reportId={9} pageId={4} onApplied={onApplied} />)
  return onApplied
}

const openPanel = () => fireEvent.click(screen.getByRole('button', { name: 'Page copilot' }))

const type = (text: string) => {
  fireEvent.change(screen.getByLabelText('Copilot message'), { target: { value: text } })
  fireEvent.keyDown(screen.getByLabelText('Copilot message'), { key: 'Enter' })
}

describe('CopilotChat', () => {
  it('is a closed button until clicked, then a panel', () => {
    mount()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    openPanel()
    expect(screen.getByRole('dialog', { name: 'Page copilot' })).toBeInTheDocument()
  })

  it('sends the message and shows the reply with what was applied', async () => {
    const copilot = vi.spyOn(reportsApi, 'copilot').mockResolvedValue({
      reply: 'Added the chart.',
      applied: [{ op: 'create', widget_id: 77, title: 'Revenue by region' }],
      notes: [], results: [], before_version_id: 31, summary: 'added "Revenue by region"',
    })
    const onApplied = mount()
    openPanel()
    type('add a bar chart of revenue by region')
    await waitFor(() => expect(screen.getByText('Added the chart.')).toBeInTheDocument())
    expect(copilot).toHaveBeenCalledWith(9, 4, {
      message: 'add a bar chart of revenue by region', history: [],
      selected_widget_id: null,
    })
    expect(screen.getByText(/Added Revenue by region/)).toBeInTheDocument()
    expect(onApplied).toHaveBeenCalledTimes(1)
    // the change travels to the builder so it can become one undo entry
    expect(onApplied).toHaveBeenCalledWith({ beforeVersionId: 31, summary: 'added "Revenue by region"' })
  })

  it('summarises an added calculated column as a formula, then reloads', async () => {
    const onApplied = mount()
    vi.spyOn(reportsApi, 'copilot').mockResolvedValue({
      reply: 'Added all_employee_count.',
      applied: [{ op: 'add_calculated_column', widget_id: null, title: 'all_employee_count' }],
      notes: [], results: [],
    })
    openPanel()
    type('create a new fx expression useful')
    await waitFor(() => expect(screen.getByText('Added all_employee_count.')).toBeInTheDocument())
    expect(screen.getByText(/Added formula all_employee_count/)).toBeInTheDocument()
    expect(onApplied).toHaveBeenCalledTimes(1)
  })

  it('a pure answer changes nothing and never reloads the page', async () => {
    vi.spyOn(reportsApi, 'copilot').mockResolvedValue({
      reply: 'This page has 3 charts about sales.', applied: [], notes: [], results: [],
    })
    const onApplied = mount()
    openPanel()
    type('what is on this page?')
    await waitFor(() => screen.getByText(/3 charts about sales/))
    expect(onApplied).not.toHaveBeenCalled()
  })

  it('a data question comes back with rows and draws them as a grid', async () => {
    // "Any demand on this page is applicable": a data question is delegated
    // to the agent server-side instead of being refused as not-a-page-edit.
    vi.spyOn(reportsApi, 'copilot').mockResolvedValue({
      reply: 'Europe leads.', applied: [], notes: [],
      results: [{ step: 's1', columns: ['region', 'revenue'],
                  rows: [['Europe', 2199376.97]], total: 1, truncated: false }],
    })
    const onApplied = mount()
    openPanel()
    type('total revenue by region')
    await waitFor(() => screen.getByText('Europe leads.'))
    expect(screen.getByRole('table')).toHaveTextContent('Europe')
    expect(onApplied).not.toHaveBeenCalled()
  })

  it('carries its own recent turns as history on the next message', async () => {
    const copilot = vi.spyOn(reportsApi, 'copilot')
      .mockResolvedValueOnce({ reply: 'Added it.', applied: [], notes: [], results: [] })
      .mockResolvedValueOnce({ reply: 'Renamed.', applied: [], notes: [], results: [] })
    mount()
    openPanel()
    type('add a pie of sales by city')
    await waitFor(() => screen.getByText('Added it.'))
    type('rename it to Sales share')
    await waitFor(() => screen.getByText('Renamed.'))
    expect(copilot).toHaveBeenLastCalledWith(9, 4, {
      message: 'rename it to Sales share',
      history: [
        { role: 'user', content: 'add a pie of sales by city' },
        { role: 'assistant', content: 'Added it.' },
      ],
      selected_widget_id: null,
    })
  })

  it('sends the selected widget so "this chart" means what the user sees', async () => {
    // Live feedback: "do that for the selected chart" only worked by guess.
    const copilot = vi.spyOn(reportsApi, 'copilot').mockResolvedValue({
      reply: 'Done.', applied: [], notes: [], results: [],
    })
    render(<CopilotChat reportId={9} pageId={4} selectedWidgetId={41} onApplied={vi.fn()} />)
    openPanel()
    type('set auto-reload on this chart to 5 seconds')
    await waitFor(() => expect(copilot).toHaveBeenCalledWith(9, 4, {
      message: 'set auto-reload on this chart to 5 seconds', history: [],
      selected_widget_id: 41,
    }))
  })

  it('notes from skipped actions reach the reply text', async () => {
    vi.spyOn(reportsApi, 'copilot').mockResolvedValue({
      reply: 'Done, with one problem.', applied: [],
      notes: ['Skipped: no column named "profitt".'], results: [],
    })
    mount()
    openPanel()
    type('chart profitt by region')
    await waitFor(() => expect(screen.getByText(/no column named "profitt"/)).toBeInTheDocument())
  })

  it('a permission refusal says so, not "could not reach"', async () => {
    vi.spyOn(reportsApi, 'copilot').mockRejectedValue({ response: { status: 403 } })
    mount()
    openPanel()
    type('add something')
    await waitFor(() =>
      expect(screen.getByText(/do not have edit rights/i)).toBeInTheDocument())
  })

  it('a failed request reads as an error and the panel stays usable', async () => {
    vi.spyOn(reportsApi, 'copilot').mockRejectedValue(new Error('down'))
    const onApplied = mount()
    openPanel()
    type('add something')
    await waitFor(() =>
      expect(screen.getByText(/could not reach the copilot/i)).toBeInTheDocument())
    expect(onApplied).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Copilot message')).not.toBeDisabled()
  })

  it('disables the input while a request is in flight', async () => {
    let resolve!: (v: { reply: string; applied: never[]; notes: never[]; results: never[] }) => void
    vi.spyOn(reportsApi, 'copilot').mockReturnValue(new Promise(r => { resolve = r }))
    mount()
    openPanel()
    type('slow one')
    await waitFor(() => expect(screen.getByLabelText('Copilot message')).toBeDisabled())
    resolve({ reply: 'ok', applied: [], notes: [], results: [] })
    await waitFor(() => expect(screen.getByLabelText('Copilot message')).not.toBeDisabled())
  })

  it('Escape closes the panel', () => {
    mount()
    openPanel()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
