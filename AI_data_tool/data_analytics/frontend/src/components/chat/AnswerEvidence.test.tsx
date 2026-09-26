import { renderWithProviders as render, screen, fireEvent, waitFor } from '../../test/renderWithProviders'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import AnswerText from './AnswerText'
import ResultView from './ResultView'
import ChatPane from './ChatPane'
import CopilotChat from '../report/CopilotChat'
import { agentApi, reportsApi, type AgentResult, type AnswerEvidence } from '../../services/api'
import { axeViolations } from '../../test/axe'

/**
 * E11: every number in an Ask AI answer links to the result it came from, or
 * says it was not found there. The server traces (services/agent/evidence.py,
 * tests/test_answer_evidence.py); these pin what the reader is shown.
 */

vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const TEXT = 'North had 12,431 in revenue, 3 regions in all, and a total of 30,000.'
/** A claim's span: `s` where it begins `where` (so "3" is the count, not the 3 in 12,431). */
const at = (s: string, where = s) => ({ start: TEXT.indexOf(where), end: TEXT.indexOf(where) + s.length, text: s })
const EVIDENCE: AnswerEvidence = {
  untraced: 1,
  claims: [
    { ...at('12,431'), status: 'traced',
      source: { result: 0, row: 0, column: 'revenue', value: 12431, kind: 'cell' } },
    { ...at('3', '3 regions'), status: 'traced',
      source: { result: 0, row: null, column: null, value: 3, kind: 'count' } },
    { ...at('30,000'), status: 'untraced' },
  ],
}
const RESULT: AgentResult = {
  step: 's1', columns: ['region', 'revenue'], total: 3, truncated: false,
  rows: [['North', 12431], ['South', 8200], ['East', 4000]],
}

describe('the answer text', () => {
  it('makes a traced number a button that names its source and shows it', () => {
    const onShow = vi.fn()
    render(<AnswerText text={TEXT} evidence={EVIDENCE} onShow={onShow} />)
    const btn = screen.getByRole('button', { name: /^12,431: From the result: revenue, row 1/ })
    expect(screen.getByRole('button', { name: /^3: The number of rows/ })).toBeInTheDocument()
    fireEvent.click(btn)
    expect(onShow).toHaveBeenCalledWith(EVIDENCE.claims[0])
    // The sentence is intact around the links (plus the untraced figure's
    // note for screen readers).
    expect(screen.getByTestId('answer-text').textContent)
      .toBe(TEXT.replace('30,000', '30,000 (Not found in the result rows)'))
  })

  it('marks a number found nowhere, and says so under the answer', () => {
    render(<AnswerText text={TEXT} evidence={EVIDENCE} onShow={() => {}} />)
    const mark = screen.getByText('30,000')
    expect(mark.closest('mark')).toHaveAttribute('data-evidence', 'untraced')
    expect(mark.closest('mark')).toHaveTextContent('30,000 (Not found in the result rows)')
    expect(screen.getByRole('note')).toHaveTextContent(/A figure in this answer is not in the result rows/)
  })

  it('counts several untraced figures', () => {
    const two: AnswerEvidence = { untraced: 2, claims: [
      { ...at('12,431'), status: 'untraced' }, { ...at('30,000'), status: 'untraced' }] }
    render(<AnswerText text={TEXT} evidence={two} onShow={() => {}} />)
    expect(screen.getByRole('note')).toHaveTextContent(/^2 figures in this answer are not in the result rows/)
  })

  it('a number from the question is highlighted, not linked or flagged', () => {
    const text = 'The top 5 are listed.'
    render(<AnswerText text={text} onShow={() => {}} evidence={{ untraced: 0, claims: [
      { start: 8, end: 9, text: '5', status: 'context' }] }} />)
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.queryByRole('note')).toBeNull()
    expect(screen.getByText('5').tagName).toBe('MARK')
  })

  it('falls back to plain highlighting when the trace does not fit the text', () => {
    render(<AnswerText text="Sales were 99." onShow={() => {}} evidence={{ untraced: 1, claims: [
      { start: 11, end: 13, text: '12', status: 'untraced' }] }} />)
    expect(screen.queryByRole('note')).toBeNull()
    expect(screen.getByText('99').tagName).toBe('MARK')
  })

  it('reads offsets as characters, so an emoji before a number does not shift it', () => {
    // Python counts the emoji as one character; JavaScript as two units.
    const text = '📈 Sales were 99.'
    render(<AnswerText text={text} onShow={() => {}} evidence={{ untraced: 0, claims: [
      { start: 13, end: 15, text: '99', status: 'traced',
        source: { result: 0, row: 0, column: 'sales', value: 99, kind: 'cell' } }] }} />)
    expect(screen.getByRole('button', { name: /^99:/ })).toBeInTheDocument()
  })

  it('without a trace, numbers are highlighted as before', () => {
    render(<AnswerText text="Total 12,400." />)
    expect(screen.getByText('12,400').tagName).toBe('MARK')
  })

  it('has no serious accessibility violations', async () => {
    const { container } = render(<AnswerText text={TEXT} evidence={EVIDENCE} onShow={() => {}} />)
    expect(await axeViolations(container)).toEqual([])
  })
})

describe('the result, pointed at', () => {
  it('marks the cell a number came from', () => {
    render(<ResultView results={[RESULT]} focus={{ result: 0, rows: [1], column: 'revenue', seq: 1 }} />)
    const marked = document.querySelectorAll('td.dl-cell--evidence')
    expect([...marked].map(td => td.textContent)).toEqual(['8200'])
  })

  it('marks a whole column for a total, and the row count for a count', () => {
    const { unmount } = render(<ResultView results={[RESULT]}
      focus={{ result: 0, rows: [], column: 'revenue', seq: 1 }} />)
    expect([...document.querySelectorAll('td.dl-cell--evidence')].map(td => td.textContent))
      .toEqual(['12431', '8200', '4000'])
    unmount()
    render(<ResultView results={[RESULT]} focus={{ result: 0, rows: [], column: null, seq: 1 }} />)
    expect(screen.getByText('3 rows').parentElement).toHaveClass('dl-cell--evidence')
  })

  it('opens the rows under a chart to show the cell', () => {
    render(<ResultView results={[RESULT]} presentation={{ format: 'bar', limit: null }}
      focus={{ result: 0, rows: [0], column: 'revenue', seq: 1 }} />)
    expect(screen.getByRole('button', { name: /hide rows/i })).toHaveAttribute('aria-expanded', 'true')
    expect(document.querySelector('td.dl-cell--evidence')).toHaveTextContent('12431')
  })
})

describe('in the chat', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(agentApi, 'createConversation').mockResolvedValue({ id: 7, title: 'New conversation' })
    vi.spyOn(agentApi, 'listConversations').mockResolvedValue([])
    vi.spyOn(agentApi, 'messages').mockResolvedValue([])
  })

  it('selecting a traced number marks its cell in that answer’s result', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 1, status: 'ok', intent: 'aggregate', error: null,
      answer: TEXT, results: [RESULT],
      sql: ['SELECT region, revenue FROM t'], evidence: EVIDENCE,
    })
    render(<ChatPane dataSourceId={2} />)
    fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: 'revenue by region' } })
    fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
    const btn = await screen.findByRole('button', { name: /^12,431: From the result/ })
    expect(document.querySelector('.dl-cell--evidence')).toBeNull()
    fireEvent.click(btn)
    await waitFor(() =>
      expect(document.querySelector('td.dl-cell--evidence')).toHaveTextContent('12431'))
    expect(screen.getByRole('note')).toHaveTextContent(/not in the result rows/)
  })
})

describe('in the dashboard copilot', () => {
  beforeEach(() => { vi.restoreAllMocks(); localStorage.clear(); sessionStorage.clear() })

  it('a data reply links its numbers to the rows it drew', async () => {
    vi.spyOn(reportsApi, 'copilot').mockResolvedValue({
      reply: TEXT, applied: [], notes: [], results: [RESULT], evidence: EVIDENCE,
    })
    render(<CopilotChat reportId={9} pageId={4} onApplied={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Ask AI about this dashboard' }))
    fireEvent.change(screen.getByLabelText('Message to Ask AI'), { target: { value: 'revenue by region' } })
    fireEvent.keyDown(screen.getByLabelText('Message to Ask AI'), { key: 'Enter' })
    fireEvent.click(await screen.findByRole('button', { name: /^12,431: From the result/ }))
    await waitFor(() =>
      expect(document.querySelector('td.dl-cell--evidence')).toHaveTextContent('12431'))
    expect(screen.getByRole('note')).toHaveTextContent(/not in the result rows/)
  })
})
