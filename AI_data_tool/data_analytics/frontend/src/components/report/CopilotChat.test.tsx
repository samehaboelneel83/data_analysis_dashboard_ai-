import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import CopilotChat from './CopilotChat'
import { api, insightsApi, llmApi, reportsApi } from '../../services/api'
import { axeViolations } from '../../test/axe'

/** The page copilot panel: opens without touching the canvas, sends the
 *  message with its own recent turns, reports what was applied, and asks the
 *  builder to reload only when something actually changed. */

beforeEach(() => { vi.restoreAllMocks(); localStorage.clear(); sessionStorage.clear() })

const mount = (onApplied = vi.fn()) => {
  render(<CopilotChat reportId={9} pageId={4} onApplied={onApplied} />)
  return onApplied
}

const openPanel = () => fireEvent.click(screen.getByRole('button', { name: 'Ask AI about this dashboard' }))

const type = (text: string) => {
  fireEvent.change(screen.getByLabelText('Message to Ask AI'), { target: { value: text } })
  fireEvent.keyDown(screen.getByLabelText('Message to Ask AI'), { key: 'Enter' })
}

describe('CopilotChat', () => {
  it('is a closed button until clicked, then a panel', () => {
    mount()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    openPanel()
    expect(screen.getByRole('dialog', { name: 'Ask AI' })).toBeInTheDocument()
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

  it('a message refused by the org\'s AI limit says so (E11)', async () => {
    vi.spyOn(reportsApi, 'copilot').mockRejectedValue({ response: { status: 429, headers: {} } })
    mount()
    openPanel()
    type('add something')
    await waitFor(() => expect(screen.getByText(
      'Your organization has reached its AI limit for now. Try again later.')).toBeInTheDocument())
  })

  it('a failed request reads as an error and the panel stays usable', async () => {
    vi.spyOn(reportsApi, 'copilot').mockRejectedValue(new Error('down'))
    const onApplied = mount()
    openPanel()
    type('add something')
    await waitFor(() =>
      expect(screen.getByText(/could not reach Ask AI/i)).toBeInTheDocument())
    expect(onApplied).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Message to Ask AI')).not.toBeDisabled()
  })

  it('disables the input while a request is in flight', async () => {
    let resolve!: (v: { reply: string; applied: never[]; notes: never[]; results: never[] }) => void
    vi.spyOn(reportsApi, 'copilot').mockReturnValue(new Promise(r => { resolve = r }))
    mount()
    openPanel()
    type('slow one')
    await waitFor(() => expect(screen.getByLabelText('Message to Ask AI')).toBeDisabled())
    resolve({ reply: 'ok', applied: [], notes: [], results: [] })
    await waitFor(() => expect(screen.getByLabelText('Message to Ask AI')).not.toBeDisabled())
  })

  it('Escape closes the panel', () => {
    mount()
    openPanel()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('Ctrl+/ opens and closes it from anywhere', () => {
    mount()
    fireEvent.keyDown(document, { key: '/', ctrlKey: true })
    expect(screen.getByRole('dialog', { name: 'Ask AI' })).toBeInTheDocument()
    fireEvent.keyDown(document, { key: '/', ctrlKey: true })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('greets with the page it is looking at, and a suggestion asks when clicked', async () => {
    const copilot = vi.spyOn(reportsApi, 'copilot').mockResolvedValue({
      reply: 'It shows sales.', applied: [], notes: [], results: [] })
    render(<CopilotChat reportId={9} pageId={4} onApplied={vi.fn()}
      reportName="Sales Overview" pageName="Page 1" widgetCount={3} />)
    openPanel()
    expect(screen.getByText("Hi, I'm looking at Page 1 with you.")).toBeInTheDocument()
    expect(screen.getByText(/read the 3 widgets/)).toBeInTheDocument()
    expect(screen.getByText('Sales Overview · Page 1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Explain this page/ }))
    await waitFor(() => expect(copilot).toHaveBeenCalledWith(9, 4, expect.objectContaining({ message: 'Explain this page' })))
    await waitFor(() => screen.getByText('It shows sales.'))
  })

  it('"Add a chart of" fills the box instead of sending', () => {
    const copilot = vi.spyOn(reportsApi, 'copilot')
    mount()
    openPanel()
    fireEvent.click(screen.getByRole('button', { name: /Add a chart of/ }))
    expect(screen.getByLabelText('Message to Ask AI')).toHaveValue('Add a chart of ')
    expect(copilot).not.toHaveBeenCalled()
  })

  it('shows a thinking card while it works', async () => {
    let resolve!: (v: { reply: string; applied: never[]; notes: never[]; results: never[] }) => void
    vi.spyOn(reportsApi, 'copilot').mockReturnValue(new Promise(r => { resolve = r }))
    render(<CopilotChat reportId={9} pageId={4} onApplied={vi.fn()} pageName="Page 1" widgetCount={3} />)
    openPanel()
    type('what drives revenue?')
    expect(await screen.findByRole('status')).toHaveTextContent('Reading 3 widgets on Page 1')
    resolve({ reply: 'ok', applied: [], notes: [], results: [] })
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument())
  })

  it('minimise keeps the conversation; close clears it', async () => {
    vi.spyOn(reportsApi, 'copilot').mockResolvedValue({ reply: 'Kept.', applied: [], notes: [], results: [] })
    mount()
    openPanel()
    type('hello')
    await waitFor(() => screen.getByText('Kept.'))
    fireEvent.click(screen.getByRole('button', { name: 'Minimise' }))
    openPanel()
    expect(screen.getByText('Kept.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close and clear' }))
    openPanel()
    expect(screen.queryByText('Kept.')).not.toBeInTheDocument()
  })

  it('a real insight puts a dot on the button, and the card in the panel', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.spyOn(insightsApi, 'runShared').mockResolvedValue({
      narrative: '', findings: [{ kind: 'share', score: 0.9, title: 'Latin America has the smallest share',
        detail: '23%, 3 points behind Europe', columns: ['region'], novelty: 'new' }] } as never)
    render(<CopilotChat reportId={9} pageId={4} onApplied={vi.fn()} datasetId={32} />)
    await vi.advanceTimersByTimeAsync(3000)
    vi.useRealTimers()
    await waitFor(() => expect(screen.getByText('Ask AI has a new insight')).toBeInTheDocument())
    openPanel()
    expect(screen.getByText('New insight')).toBeInTheDocument()
    expect(screen.getByText(/Latin America has the smallest share/)).toBeInTheDocument()
    // Seen once: the dot does not come back.
    fireEvent.click(screen.getByRole('button', { name: 'Minimise' }))
    expect(screen.queryByText('Ask AI has a new insight')).not.toBeInTheDocument()
  })

  it('no insight, no dot', async () => {
    vi.spyOn(insightsApi, 'runShared').mockResolvedValue({ narrative: '', findings: [] } as never)
    mount()
    expect(screen.queryByText('Ask AI has a new insight')).not.toBeInTheDocument()
  })

  it('Alt+arrows move it to another corner, and it remembers', () => {
    const { container } = render(<CopilotChat reportId={9} pageId={4} onApplied={vi.fn()} />)
    const root = () => container.querySelector('.dl-askai')!
    expect(root()).toHaveClass('dl-askai--bottom', 'dl-askai--end')
    fireEvent.keyDown(screen.getByRole('button', { name: 'Ask AI about this dashboard' }), { key: 'ArrowUp', altKey: true })
    fireEvent.keyDown(screen.getByRole('button', { name: 'Ask AI about this dashboard' }), { key: 'ArrowLeft', altKey: true })
    expect(root()).toHaveClass('dl-askai--top', 'dl-askai--start')
    expect(localStorage.getItem('datalytics.askai.corner')).toBe('top-start')
  })

  it('hides while the dashboard is presenting', () => {
    const { container } = render(<CopilotChat reportId={9} pageId={4} onApplied={vi.fn()} />)
    act(() => { window.dispatchEvent(new CustomEvent('datalytics:present', { detail: true })) })
    expect(container.querySelector('.dl-askai')).toBeNull()
    act(() => { window.dispatchEvent(new CustomEvent('datalytics:present', { detail: false })) })
    expect(container.querySelector('.dl-askai')).not.toBeNull()
  })

  it('button and open panel have no accessibility violations', async () => {
    const { container } = render(<CopilotChat reportId={9} pageId={4} onApplied={vi.fn()}
      reportName="Sales" pageName="Page 1" widgetCount={2} />)
    expect(await axeViolations(container)).toEqual([])
    openPanel()
    expect(await axeViolations(container)).toEqual([])
  })
})

describe('CopilotChat while the model server is unreachable (redesign 7e5)', () => {
  const endpoints = (ok: boolean) => ({ data: {
    llm_enabled: true, default: 'main', auto_pick: null, source: 'saved',
    endpoints: [{ id: 'main', name: 'Main', model: 'm', enabled: true, is_default: true, strength: 5, context: null, status: { ok } }],
  } })

  it('says so in one line and locks the box, then unlocks when it is back', async () => {
    vi.spyOn(api, 'get').mockResolvedValue(endpoints(false) as any)
    mount()
    await act(async () => { await llmApi.endpoints() })
    openPanel()
    expect(await screen.findByTestId('copilot-offline')).toHaveTextContent('The model server isn’t reachable, so new questions are paused.')
    const box = screen.getByLabelText('Message to Ask AI')
    expect(box).toBeDisabled()
    expect(box).toHaveAttribute('placeholder', 'New questions are paused while the model server is unreachable')
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    vi.mocked(api.get).mockResolvedValue(endpoints(true) as any)
    await act(async () => { await llmApi.endpoints() })
    await waitFor(() => expect(screen.queryByTestId('copilot-offline')).not.toBeInTheDocument())
    expect(screen.getByLabelText('Message to Ask AI')).not.toBeDisabled()
  })
})

