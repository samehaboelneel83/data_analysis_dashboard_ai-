import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import Reports, { nextUntitledName } from './Reports'
import { reportsApi, reportGrantsApi, datasetsApi, workspaceApi } from '../services/api'
import { ConfirmProvider } from '../components/ui/ConfirmDialog'
import { PromptProvider } from '../components/ui/PromptDialog'
import { answerPrompt } from '../test/renderWithProviders'
import toast from 'react-hot-toast'
import { axeViolations } from '../test/axe'

vi.mock('../services/api', () => ({
  reportsApi: { list: vi.fn(), delete: vi.fn(), create: vi.fn(), update: vi.fn(), setPublished: vi.fn() },
  reportGrantsApi: { list: vi.fn(), create: vi.fn(), remove: vi.fn() },
  datasetsApi: { list: vi.fn() },
  // The page reads the workspace tree again -- not to render it, but to work
  // out which folder each dashboard is filed in.
  workspaceApi: { tree: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
}))
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

/** Renders the current path, so navigation is observable rather than implied. */
function Where() {
  const { pathname } = useLocation()
  return <div data-testid="where">{pathname}</div>
}

const renderReports = () =>
  render(
    <ConfirmProvider>
      <PromptProvider>
        <MemoryRouter initialEntries={['/reports']}>
          <Reports />
          <Where />
        </MemoryRouter>
      </PromptProvider>
    </ConfirmProvider>
  )

// `my_capability` is spelled out because the page now defaults a MISSING one
// to 'view' (fail closed) rather than to full access. The list endpoint always
// sends it, so a fixture without one is not a state the app can be in -- and
// omitting it silently hid every edit control this file asserts on.
const report = (over = {}) => ({
  id: 1, name: 'Revenue', description: '', dataset_id: undefined,
  my_capability: 'data', created_by: 7, is_mine: true,
  created_at: '2026-08-22T00:00:00Z', ...over,
})

beforeEach(() => {
  vi.clearAllMocks()
  // Collapsed headings persist; a test must not inherit another's.
  localStorage.clear()
  vi.mocked(datasetsApi.list).mockResolvedValue([] as never)
  vi.mocked(reportsApi.list).mockResolvedValue([report()] as never)
  vi.mocked(reportsApi.delete).mockResolvedValue(undefined as never)
  vi.mocked(workspaceApi.tree).mockResolvedValue({ roots: [], unfiled: [] } as never)
})

describe('deleting a dashboard', () => {
  it('the trash button confirms, then deletes', async () => {
    renderReports()
    await waitFor(() => expect(screen.getByText('Revenue')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Delete dashboard Revenue' }))

    const dlg = await screen.findByRole('alertdialog')
    fireEvent.click(within(dlg).getByRole('button', { name: /Delete/i }))

    await waitFor(() => expect(reportsApi.delete).toHaveBeenCalledWith(1))
  })

  it('select mode: clicking cards ticks them instead of opening them, then deletes them together', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report(), report({ id: 2, name: 'Untitled dashboard 3' }), report({ id: 3, name: 'Shared KPIs', my_capability: 'view', is_mine: false }),
    ] as never)
    renderReports()
    await waitFor(() => expect(screen.getByText('Revenue')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Select' }))
    fireEvent.click(screen.getByText('Untitled dashboard 3'))
    expect(screen.getByTestId('where')).toHaveTextContent('/reports')
    expect(screen.getByRole('checkbox', { name: 'Select Untitled dashboard 3' })).toBeChecked()
    // A dashboard the viewer cannot delete cannot be ticked.
    expect(screen.getByRole('checkbox', { name: 'Select Shared KPIs' })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: /Delete selected/ }))
    const dlg = await screen.findByRole('alertdialog')
    fireEvent.click(within(dlg).getByRole('button', { name: /Delete selected/ }))
    await waitFor(() => expect(reportsApi.delete).toHaveBeenCalledWith(2))
    expect(reportsApi.delete).toHaveBeenCalledTimes(1)
  })

  it('offers exactly ONE delete control per card', async () => {
    // It used to offer two: this button and a ⋯ menu whose only item was the
    // same action. Two controls for one destructive act is two chances to fire
    // it and one more thing to read on every card.
    renderReports()
    await screen.findByText('Revenue')
    expect(screen.getAllByRole('button', { name: /delete dashboard/i })).toHaveLength(1)
    expect(screen.queryByRole('button', { name: /more actions/i })).toBeNull()
  })
})

describe('my workspaces vs granted to me', () => {
  it('splits the grid by authorship when the viewer has both kinds', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 1, name: 'Revenue', is_mine: true, my_capability: 'data' }),
      report({ id: 2, name: 'Board pack', is_mine: false, my_capability: 'view' }),
    ] as never)
    renderReports()
    expect(await screen.findByRole('heading', { name: 'My workspaces' })).toBeInTheDocument()
    const granted = screen.getByRole('heading', { name: 'Granted to me' })
    expect(granted.compareDocumentPosition(screen.getByText('Board pack')))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
  })

  it('shows a plain grid when everything is the viewer\'s own', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 1, name: 'Revenue', is_mine: true, my_capability: 'data' }),
    ] as never)
    renderReports()
    await screen.findByText('Revenue')
    expect(screen.queryByRole('heading', { name: 'My workspaces' })).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Granted to me' })).toBeNull()
  })

  it('shows a plain grid when everything was granted to the viewer', async () => {
    // The other half of the same rule, and the branch nothing covered: a
    // viewer who authored NOTHING would otherwise read "Granted to me" over
    // their entire list, which labels a distinction that is not there.
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 2, name: 'Board pack', is_mine: false, my_capability: 'view' }),
      report({ id: 3, name: 'Team board', is_mine: false, my_capability: 'edit' }),
    ] as never)
    renderReports()
    await screen.findByText('Board pack')
    expect(screen.queryByRole('heading', { name: 'My workspaces' })).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Granted to me' })).toBeNull()
  })

  it('puts each dashboard under its own heading, not just the headings on screen', async () => {
    // A heading that renders with nothing beneath it -- or with the wrong
    // cards beneath it -- looks identical to a correct one in a test that only
    // asserts the headings exist.
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 1, name: 'Revenue', is_mine: true, my_capability: 'data' }),
      report({ id: 2, name: 'Board pack', is_mine: false, my_capability: 'view' }),
    ] as never)
    renderReports()

    const mineHead = await screen.findByRole('heading', { name: 'My workspaces' })
    const grantedHead = screen.getByRole('heading', { name: 'Granted to me' })
    const revenue = screen.getByText('Revenue')
    const boardPack = screen.getByText('Board pack')

    // Revenue sits between the two headings; Board pack after the second.
    expect(mineHead.compareDocumentPosition(revenue))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    expect(grantedHead.compareDocumentPosition(revenue))
      .toBe(Node.DOCUMENT_POSITION_PRECEDING)
    expect(grantedHead.compareDocumentPosition(boardPack))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
  })

  it('a view-only report loses Delete and is marked view only', async () => {
    // Mirrors the server: delete_report requires >= edit. Offering the button
    // and letting the request 403 would be the dead-control defect.
    //
    // The "Open designer →" / "Open →" labels used to carry this distinction
    // too; that button is gone (the whole card opens the dashboard now), so
    // the chip is the only thing left saying it -- which makes asserting on
    // the chip the point rather than a consolation.
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 2, name: 'Board pack', is_mine: false, my_capability: 'view' }),
    ] as never)
    renderReports()
    await screen.findByText('Board pack')
    expect(screen.queryByRole('button', { name: 'Delete dashboard Board pack' })).toBeNull()
    expect(screen.getByText(/view only/)).toBeInTheDocument()
  })

  it('a granted-but-editable report keeps its design controls', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 3, name: 'Team dashboard', is_mine: false, my_capability: 'edit' }),
    ] as never)
    renderReports()
    await screen.findByText('Team dashboard')
    expect(screen.getByRole('button', { name: 'Delete dashboard Team dashboard' })).toBeInTheDocument()
    expect(screen.queryByText(/view only/)).toBeNull()
  })
})

describe('publish and share controls', () => {
  const own = (over = {}) => report({
    id: 5, name: 'My board', is_mine: true, my_capability: 'data',
    created_by: 9, published: false, ...over,
  })

  it('the author gets Publish and Share; publishing calls the API and shows the badge', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([own()] as never)
    vi.mocked(reportsApi.setPublished).mockResolvedValue({ published: true } as never)
    renderReports()
    fireEvent.click(await screen.findByRole('button', { name: 'Publish My board' }))
    await waitFor(() => expect(reportsApi.setPublished).toHaveBeenCalledWith(5, true))
    expect(await screen.findByText('published')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Unpublish My board' })).toBeInTheDocument()
  })

  it('a legacy report (no author) offers no Publish -- the server would 400 it', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 6, name: 'Old faithful', created_by: null, my_capability: 'data' }),
    ] as never)
    renderReports()
    await screen.findByText('Old faithful')
    expect(screen.queryByRole('button', { name: /Publish/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Share/ })).toBeNull()
  })

  it('a granted dashboard someone else authored offers no Publish or Share', async () => {
    // Edit capability is design power, not sharing power -- mirrored from the
    // server, which 403s a grantee's publish.
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 7, name: 'Their board', is_mine: false, created_by: 4, my_capability: 'edit' }),
    ] as never)
    renderReports()
    await screen.findByText('Their board')
    expect(screen.queryByRole('button', { name: /Publish|Share/ })).toBeNull()
  })

  it('the share dialog lists grants and posts a new one by email', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([own()] as never)
    vi.mocked(reportGrantsApi.list).mockResolvedValue([
      { id: 1, user_id: 2, email: 'ana@ex.com', level: 'view' },
    ] as never)
    vi.mocked(reportGrantsApi.create).mockResolvedValue(
      { id: 2, user_id: 3, email: 'omar@ex.com', level: 'edit' } as never)
    renderReports()
    fireEvent.click(await screen.findByRole('button', { name: 'Share My board' }))

    expect(await screen.findByText('ana@ex.com')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Email to share with'),
      { target: { value: 'omar@ex.com' } })
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Share' }))
    await waitFor(() => expect(reportGrantsApi.create)
      .toHaveBeenCalledWith(5, { email: 'omar@ex.com', level: 'edit' }))
    expect(await screen.findByText('omar@ex.com')).toBeInTheDocument()
  })

  it('removing a grant calls the API and drops the row', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([own()] as never)
    vi.mocked(reportGrantsApi.list).mockResolvedValue([
      { id: 1, user_id: 2, email: 'ana@ex.com', level: 'edit' },
    ] as never)
    vi.mocked(reportGrantsApi.remove).mockResolvedValue(undefined as never)
    renderReports()
    fireEvent.click(await screen.findByRole('button', { name: 'Share My board' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Remove access for ana@ex.com' }))
    await waitFor(() => expect(reportGrantsApi.remove).toHaveBeenCalledWith(5, 1))
    expect(screen.queryByText('ana@ex.com')).toBeNull()
  })
})

describe('opening a dashboard', () => {
  const where = () => screen.getByTestId('where').textContent

  it('the whole card opens it, not just the title', async () => {
    renderReports()
    const card = (await screen.findByText('Revenue')).closest('.card')!
    fireEvent.click(card)
    expect(where()).toBe('/reports/1')
  })

  it('keeps the title a real anchor, so middle-click and new-tab still work', async () => {
    // A div with an onClick cannot be opened in a new tab, copied as a link,
    // or reached by a screen reader's link list. The card click is a
    // convenience ON TOP of the anchor, never a replacement for it.
    renderReports()
    const title = await screen.findByText('Revenue')
    expect(title.tagName).toBe('A')
    expect(title).toHaveAttribute('href', '/reports/1')
  })

  it('does not navigate when a control inside the card is clicked', async () => {
    renderReports()
    await screen.findByText('Revenue')
    fireEvent.click(screen.getByRole('button', { name: 'Delete dashboard Revenue' }))
    expect(where()).toBe('/reports')
  })

  it('adds no second tab stop for the card itself', async () => {
    // Two focusable things pointing at one destination means two tab stops and
    // two announcements for one dashboard.
    renderReports()
    const card = (await screen.findByText('Revenue')).closest('.card')!
    expect(card).not.toHaveAttribute('tabindex')
    expect(card).not.toHaveAttribute('role')
  })
})

describe('card controls are quiet until reached for', () => {
  /**
   * jsdom applies no stylesheet, so the reveal itself is pinned by CONTENT --
   * the technique svgDirection.test.ts uses for the same reason. What IS
   * testable here is the part that matters for access: the buttons stay in the
   * DOM and in the tab order, so "hidden until hover" never becomes "hidden".
   */
  const css = async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const url = await import('node:url')
    const here = path.dirname(url.fileURLToPath(import.meta.url))
    return fs.readFileSync(path.resolve(here, '../index.css'), 'utf8')
  }

  it('keeps every control reachable, not merely un-drawn', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 5, name: 'My board', is_mine: true, my_capability: 'data',
               created_by: 9, published: false }),
    ] as never)
    renderReports()
    await screen.findByText('My board')

    for (const name of ['Share My board', 'Publish My board', 'Delete dashboard My board']) {
      const btn = screen.getByRole('button', { name })
      expect(btn).toBeInTheDocument()
      expect(btn).not.toHaveAttribute('aria-hidden')
      expect(btn).not.toBeDisabled()
    }
  })

  it('names all three for a screen reader and on hover', async () => {
    // Icon-only buttons: without both, one card's delete is indistinguishable
    // from another's, and the globe is a guess.
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 5, name: 'My board', is_mine: true, my_capability: 'data',
               created_by: 9, published: false }),
    ] as never)
    renderReports()
    await screen.findByText('My board')

    for (const name of ['Share My board', 'Publish My board', 'Delete dashboard My board']) {
      expect(screen.getByRole('button', { name })).toHaveAttribute('title')
    }
  })

  it('reveals on hover AND on keyboard focus, and never hides on touch', async () => {
    const text = await css()
    const rule = text.match(/\.dl-card-actions\s*\{[^}]*\}/)
    expect(rule, 'no .dl-card-actions rule in index.css').toBeTruthy()
    expect(rule![0]).toMatch(/opacity:\s*0/)

    // Keyboard users never hover; without this they could not see what they
    // had focused.
    expect(text).toMatch(/\.card:focus-within\s+\.dl-card-actions/)
    // A touch screen has no hover at all, so the reveal must not apply there.
    expect(text).toMatch(/@media\s*\(hover:\s*none\)[^{]*\{[^}]*\.dl-card-actions/)
  })
})

describe('dashboards proposed by Suggest dashboards', () => {
  it('shows a Suggested chip instead of a description line', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 8, name: 'Revenue picture', description: 'Suggested from the data' }),
    ] as never)
    renderReports()
    await screen.findByText('Revenue picture')

    expect(screen.getByText('Suggested')).toBeInTheDocument()
    // The sentence itself is gone: it said the same thing on every such card
    // and cost a full line to do it.
    expect(screen.queryByText('Suggested from the data')).toBeNull()
  })

  it('keeps the goal when one was given, without repeating the word', async () => {
    // "Suggested for: quarterly board review" carries something the chip
    // cannot -- the goal. Only the prefix is redundant once the chip is there.
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 9, name: 'Board view',
               description: 'Suggested for: quarterly board review' }),
    ] as never)
    renderReports()
    await screen.findByText('Board view')

    expect(screen.getByText('Suggested')).toBeInTheDocument()
    expect(screen.getByText('quarterly board review')).toBeInTheDocument()
    expect(screen.queryByText(/Suggested for:/)).toBeNull()
  })

  it('leaves a hand-written description completely alone', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 10, name: 'Ops', description: 'Weekly ops review, EMEA only' }),
    ] as never)
    renderReports()
    await screen.findByText('Ops')

    expect(screen.getByText('Weekly ops review, EMEA only')).toBeInTheDocument()
    expect(screen.queryByText('Suggested')).toBeNull()
  })

  it('does not rewrite the description it was sent', async () => {
    // A rendering change only: nothing here may mutate the API value, or the
    // next PATCH would save the trimmed text back over the original.
    const rows = [report({ id: 11, name: 'R', description: 'Suggested from the data' })]
    vi.mocked(reportsApi.list).mockResolvedValue(rows as never)
    renderReports()
    await screen.findByText('R')
    expect(rows[0].description).toBe('Suggested from the data')
  })
})

describe('the card title is not squeezed by its own chips', () => {
  /**
   * The regression this pins: the title and the status chips shared one flex
   * row, chips at flex-shrink: 0. Adding the SUGGESTED chip left "What stands
   * out in Route planning extract output" about eight characters wide and six
   * lines tall, and the grid row grew to fit the tower.
   *
   * The structural fix is that no chip sits beside the title any more. That is
   * checkable in jsdom; the two-line clamp that goes with it is CSS, so it is
   * pinned by reading index.css.
   */
  const suggested = () => report({
    id: 12, name: 'What stands out in Route planning extract output',
    description: 'Suggested from the data', published: true, created_by: 9,
    is_mine: true, my_capability: 'data',
  })

  it('puts every chip in the footer, none beside the title', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([suggested()] as never)
    renderReports()
    const title = await screen.findByText(/What stands out in Route planning/)
    const head = title.closest('.dl-dash-card__head')!
    const card = title.closest('.card')!

    expect(head).toBeTruthy()
    for (const chip of ['Suggested', 'published']) {
      const el = screen.getByText(chip)
      expect(head.contains(el), `${chip} is still beside the title`).toBe(false)
      expect(card.querySelector('.dl-dash-card__foot')!.contains(el)).toBe(true)
    }
  })

  it('clamps a long name to two lines rather than letting it tower', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const url = await import('node:url')
    const here = path.dirname(url.fileURLToPath(import.meta.url))
    const css = fs.readFileSync(path.resolve(here, '../index.css'), 'utf8')

    const rule = css.match(/\.dl-dash-card__title\s*\{[^}]*\}/)
    expect(rule, 'no .dl-dash-card__title rule in index.css').toBeTruthy()
    expect(rule![0]).toMatch(/line-clamp:\s*2/)
    // Without min-inline-size: 0 a flex child refuses to shrink below its
    // content, which is what let the chips win the row in the first place.
    expect(rule![0]).toMatch(/min-inline-size:\s*0/)
  })

  it('keeps the full name reachable once it is clipped', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([suggested()] as never)
    renderReports()
    const title = await screen.findByText(/What stands out in Route planning/)
    expect(title).toHaveAttribute('title',
      'What stands out in Route planning extract output')
  })
})

/**
 * The card carries four labels at most, and no two of them say the same thing.
 *
 * Every auto-generated dashboard is named after the dataset it was generated
 * from -- "What stands out in Demo Sales", "Enrolments 2025 - escalated to
 * registrar" -- and the footer then printed that dataset's name again, right
 * under the title. Two labels, one fact, on most of the grid.
 *
 * The chip is not dropped outright, because it is the ONLY identifying label
 * on a card whose title says nothing: "What stands out in this data" needs
 * "Metrics Snapshot Test" to be worth anything at all.
 */
describe('the dashboard card does not repeat itself', () => {
  const withDataset = (dsName: string, reportName: string) => {
    vi.mocked(datasetsApi.list).mockResolvedValue([
      { id: 9, name: dsName },
    ] as never)
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 1, name: reportName, dataset_id: 9 }),
    ] as never)
  }

  it('drops the dataset chip when the title already names the dataset', async () => {
    withDataset('Enrolments 2025', 'Enrolments 2025 - escalated to registrar')
    renderReports()

    await screen.findByText('Enrolments 2025 - escalated to registrar')
    // Exact match: the title contains the string, the chip WAS the string.
    expect(screen.queryByText('Enrolments 2025')).toBeNull()
  })

  it('ignores case and spacing when deciding that', async () => {
    withDataset('demo  sales', 'What stands out in Demo Sales')
    renderReports()

    await screen.findByText('What stands out in Demo Sales')
    // Queried in the normalised form testing-library compares against --
    // asking for the raw double space matches nothing either way, which
    // would make this test pass without testing anything.
    expect(screen.queryByText('demo sales')).toBeNull()
  })

  it('keeps the dataset chip when the title does not name it', async () => {
    // The card that needs it most: the title is generic, so the chip is the
    // only thing telling one of these apart from the next.
    withDataset('Metrics Snapshot Test', 'What stands out in this data')
    renderReports()

    expect(await screen.findByText('Metrics Snapshot Test')).toBeInTheDocument()
  })

  it('says nothing at all when a dashboard has no dataset', async () => {
    // "No dataset" is an absence, not a fact about the dashboard. It cost a
    // label on every card that had one.
    vi.mocked(datasetsApi.list).mockResolvedValue([] as never)
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 1, name: '465', dataset_id: undefined }),
    ] as never)
    renderReports()

    await screen.findByText('465')
    expect(screen.queryByText(/no dataset/i)).toBeNull()
  })
})

describe('the dashboards page is one full-width column', () => {
  it('does not render the workspace tree', async () => {
    // The tree moved out again: the page is a list of dashboards, and the
    // 280px column of folders was taking a quarter of the width to show six.
    renderReports()
    await screen.findByText('Revenue')
    expect(screen.queryByTestId('workspace-tree')).toBeNull()
    expect(screen.queryByRole('button', { name: /folders/i })).toBeNull()
  })
})


/**
 * Folders are headings, not chips.
 *
 * A chip on every card under one folder said the same word six times in a
 * row -- the duplication the page had just been cleared of. A heading says
 * it once and makes the grid read like the tree did: this folder, its
 * dashboards, then its subfolders as smaller headings inside it.
 *
 * Loose dashboards come FIRST, before any folder heading, rather than last
 * under an invented "Unfiled" label: a run of cards after a heading reads as
 * belonging to it, a run of cards before the first heading reads as
 * belonging to nothing. Same shape at every level -- a folder is its direct
 * cards and then its children.
 */
describe('cards are grouped under folder headings', () => {
  const node = (over: Record<string, unknown>) => ({
    id: 1, parent_id: null, node_type: 'folder', name: 'Widget gallery', report_id: null,
    position: 0, can_manage: true, is_mine: true, role_ids: [], pages: [],
    children: [], ...over,
  })
  const leaf = (reportId: number) =>
    node({ id: 90 + reportId, node_type: 'report', name: 'x', report_id: reportId })

  const three = () => vi.mocked(reportsApi.list).mockResolvedValue([
    report({ id: 1, name: 'Revenue' }),
    report({ id: 2, name: 'Costs' }),
    report({ id: 3, name: 'Margin' }),
  ] as never)

  const before = (a: Element, b: Element) =>
    !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)

  it('puts a heading named after the folder above its dashboards', async () => {
    three()
    vi.mocked(workspaceApi.tree).mockResolvedValue({
      roots: [node({ children: [leaf(1), leaf(2)] })], unfiled: [leaf(3)],
    } as never)
    renderReports()

    const region = await screen.findByRole('region', { name: 'Widget gallery' })
    expect(within(region).getByText('Revenue')).toBeInTheDocument()
    expect(within(region).getByText('Costs')).toBeInTheDocument()
    expect(within(region).queryByText('Margin')).toBeNull()
    // No chip: the heading already said it.
    expect(screen.queryByTestId('card-folder')).toBeNull()
    // And each dashboard exactly ONCE on the page. Scoping the assertions
    // above to the region hid a mutant that rendered every filed card a
    // second time in the loose grid -- the duplication this feature exists
    // to avoid, and nothing here would have noticed.
    for (const name of ['Revenue', 'Costs', 'Margin']) {
      expect(screen.getAllByText(name)).toHaveLength(1)
    }
  })

  it('nests a subfolder heading inside its parent', async () => {
    three()
    vi.mocked(workspaceApi.tree).mockResolvedValue({
      roots: [node({
        name: 'omda',
        children: [leaf(1), node({ id: 2, name: 'omda1', children: [leaf(2)] })],
      })],
      unfiled: [],
    } as never)
    renderReports()

    const parent = await screen.findByRole('region', { name: 'omda' })
    const child = within(parent).getByRole('region', { name: 'omda1' })
    expect(within(child).getByText('Costs')).toBeInTheDocument()
    // The parent's own dashboard sits above the child folder, not inside it.
    expect(within(child).queryByText('Revenue')).toBeNull()
    expect(before(within(parent).getByText('Revenue'), child)).toBe(true)
  })

  it('renders loose dashboards before the first folder heading', async () => {
    three()
    vi.mocked(workspaceApi.tree).mockResolvedValue({
      roots: [node({ children: [leaf(1)] })], unfiled: [leaf(2), leaf(3)],
    } as never)
    renderReports()

    const heading = await screen.findByRole('heading', { name: 'Widget gallery' })
    expect(before(screen.getByText('Costs'), heading)).toBe(true)
    expect(before(screen.getByText('Margin'), heading)).toBe(true)
    expect(screen.queryByText(/unfiled/i)).toBeNull()
  })

  it('shows a folder that is genuinely empty, with a zero', async () => {
    // The page manages folders now, so a folder you just created has to be
    // on screen to be named, filled or deleted. It used to be hidden, which
    // made "New folder" look like it did nothing.
    three()
    vi.mocked(workspaceApi.tree).mockResolvedValue({
      roots: [
        node({ children: [leaf(1)] }),
        node({ id: 2, name: 'Empty one', children: [] }),
        node({ id: 3, name: 'Only subfolders', children: [node({ id: 4, name: 'Also empty' })] }),
      ],
      unfiled: [],
    } as never)
    renderReports()

    await screen.findByRole('heading', { name: 'Widget gallery' })
    const empty = screen.getByRole('region', { name: 'Empty one' })
    expect(within(empty).getByLabelText('0 dashboards')).toBeInTheDocument()
    expect(within(empty).getByText(/empty folder/i)).toBeInTheDocument()
    // Nesting still holds for empties.
    const outer = screen.getByRole('region', { name: 'Only subfolders' })
    expect(within(outer).getByRole('region', { name: 'Also empty' })).toBeInTheDocument()
  })

  it("lists an empty folder once, under the viewer's own group only", async () => {
    // An empty folder belongs to nobody's dashboards, so without this rule
    // it appeared under BOTH groups -- the same heading twice on one page.
    // It is the viewer's own folder, so it goes where their own dashboards go.
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 1, name: 'Revenue' }),
      report({ id: 3, name: 'Theirs', is_mine: false, my_capability: 'view', created_by: 8 }),
    ] as never)
    vi.mocked(workspaceApi.tree).mockResolvedValue({
      roots: [node({ id: 2, name: 'Empty one', children: [] })],
      unfiled: [leaf(1), leaf(3)],
    } as never)
    renderReports()

    const mine = await screen.findByRole('region', { name: 'My workspaces' })
    expect(within(mine).getByRole('heading', { name: 'Empty one' })).toBeInTheDocument()
    const granted = screen.getByRole('region', { name: 'Granted to me' })
    expect(within(granted).queryByRole('heading', { name: 'Empty one' })).toBeNull()
    expect(screen.getAllByRole('heading', { name: 'Empty one' })).toHaveLength(1)
  })

  it('hides a folder the search box emptied, and empty ones while searching', async () => {
    // Eight rows, so the search box renders at all. A folder that HAS
    // dashboards but none that match is hidden with them: the heading
    // would otherwise promise something the search says is not there. And
    // an empty folder cannot match anything, so it goes too.
    vi.mocked(reportsApi.list).mockResolvedValue(
      Array.from({ length: 8 }, (_, i) => report({ id: i + 1, name: `Dash ${i + 1}` })) as never)
    vi.mocked(workspaceApi.tree).mockResolvedValue({
      roots: [
        node({ children: [leaf(1)] }),
        node({ id: 2, name: 'Empty one', children: [] }),
      ],
      unfiled: [leaf(2), leaf(3), leaf(4), leaf(5), leaf(6), leaf(7), leaf(8)],
    } as never)
    renderReports()
    await screen.findByRole('heading', { name: 'Widget gallery' })

    fireEvent.change(screen.getByPlaceholderText('Search dashboards'), { target: { value: 'Dash 2' } })

    expect(screen.queryByRole('heading', { name: 'Widget gallery' })).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Empty one' })).toBeNull()
    expect(screen.getByText('Dash 2')).toBeInTheDocument()
  })

  it('still renders the dashboards when the tree request fails', async () => {
    // The headings are a courtesy. Losing them must not cost the page.
    three()
    vi.mocked(workspaceApi.tree).mockRejectedValue(new Error('boom'))
    renderReports()

    expect(await screen.findByText('Revenue')).toBeInTheDocument()
    expect(screen.getByText('Margin')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})


/**
 * Three tiers, and each one visibly UNDER the one above it.
 *
 * "My workspaces" and "sameh" used to render as siblings at the same level,
 * with the folder heading actually heavier than the group heading -- the
 * hierarchy read upside-down. Now a folder's section is inside its group's
 * section, a subfolder's inside its folder's, and every heading carries the
 * same collapse control, so a long page folds down to its headings.
 */
describe('headings nest and collapse', () => {
  const node = (over: Record<string, unknown>) => ({
    id: 1, parent_id: null, node_type: 'folder', name: 'sameh', report_id: null,
    position: 0, can_manage: true, is_mine: true, role_ids: [], pages: [],
    children: [], ...over,
  })
  const leaf = (reportId: number) =>
    node({ id: 90 + reportId, node_type: 'report', name: 'x', report_id: reportId })

  /** One of mine filed under "sameh", one of mine loose, one granted. */
  const arrange = () => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 1, name: 'Revenue' }),
      report({ id: 2, name: 'Costs' }),
      report({ id: 3, name: 'Theirs', is_mine: false, my_capability: 'view', created_by: 8 }),
    ] as never)
    vi.mocked(workspaceApi.tree).mockResolvedValue({
      roots: [node({ children: [leaf(1)] })], unfiled: [leaf(2), leaf(3)],
    } as never)
  }

  it('puts a folder INSIDE its authorship group, not beside it', async () => {
    arrange()
    renderReports()

    const group = await screen.findByRole('region', { name: 'My workspaces' })
    const folder = within(group).getByRole('region', { name: 'sameh' })
    expect(within(folder).getByText('Revenue')).toBeInTheDocument()
    // The loose card is in the group but not in the folder.
    expect(within(group).getByText('Costs')).toBeInTheDocument()
    expect(within(folder).queryByText('Costs')).toBeNull()
    // And the other group is a sibling, not a child.
    expect(within(group).queryByText('Theirs')).toBeNull()
  })

  it('collapses a folder from its heading, and expands it again', async () => {
    arrange()
    renderReports()
    await screen.findByText('Revenue')

    const toggle = screen.getByRole('button', { name: 'sameh' })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')

    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Revenue')).toBeNull()
    // The heading stays, so there is something to expand from.
    expect(screen.getByRole('heading', { name: 'sameh' })).toBeInTheDocument()
    // Nothing outside the folder moved.
    expect(screen.getByText('Costs')).toBeInTheDocument()

    fireEvent.click(toggle)
    expect(screen.getByText('Revenue')).toBeInTheDocument()
  })

  it('collapses a whole group, folders included', async () => {
    arrange()
    renderReports()
    await screen.findByText('Revenue')

    fireEvent.click(screen.getByRole('button', { name: 'My workspaces' }))

    expect(screen.queryByText('Revenue')).toBeNull()
    expect(screen.queryByText('Costs')).toBeNull()
    expect(screen.queryByRole('heading', { name: 'sameh' })).toBeNull()
    // The other group is untouched.
    expect(screen.getByText('Theirs')).toBeInTheDocument()
  })

  it('remembers what was collapsed across a reload', async () => {
    arrange()
    const { unmount } = renderReports()
    await screen.findByText('Revenue')
    fireEvent.click(screen.getByRole('button', { name: 'sameh' }))
    expect(screen.queryByText('Revenue')).toBeNull()
    unmount()

    renderReports()
    await screen.findByText('Costs')
    expect(screen.queryByText('Revenue')).toBeNull()
    expect(screen.getByRole('button', { name: 'sameh' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('says how many dashboards each heading holds', async () => {
    // The number is what makes a collapsed heading worth anything: "sameh"
    // alone says nothing about whether opening it is worth the click.
    arrange()
    renderReports()
    await screen.findByText('Revenue')

    const group = screen.getByRole('region', { name: 'My workspaces' })
    expect(within(group).getAllByLabelText('2 dashboards')[0]).toBeInTheDocument()
    const folder = within(group).getByRole('region', { name: 'sameh' })
    expect(within(folder).getByLabelText('1 dashboard')).toBeInTheDocument()
  })

  it("counts the whole subtree, not just the folder's own cards", async () => {
    // A folded "omda" whose dashboards all live in "omda1" must not say 0 --
    // that number is the only reason to open it. A shallow count survived
    // every other test here because none of them nested.
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 1, name: 'Revenue' }),
      report({ id: 2, name: 'Costs' }),
    ] as never)
    vi.mocked(workspaceApi.tree).mockResolvedValue({
      roots: [node({
        name: 'omda',
        children: [leaf(1), node({ id: 2, name: 'omda1', children: [leaf(2)] })],
      })],
      unfiled: [],
    } as never)
    renderReports()

    const parent = await screen.findByRole('region', { name: 'omda' })
    // The parent's own count badge is the first one inside it; the child's
    // is nested deeper.
    expect(within(parent).getAllByLabelText(/dashboards?$/)[0])
      .toHaveAttribute('aria-label', '2 dashboards')
    expect(within(within(parent).getByRole('region', { name: 'omda1' }))
      .getByLabelText('1 dashboard')).toBeInTheDocument()
  })
})

/**
 * A heading is never cut short.
 *
 * "My workspa…" shipped: the heading's name had the card-title treatment
 * (nowrap + ellipsis), and a flex quirk handed the <h2> a fraction of its row.
 * The fix is a rule, not a width: a heading name WRAPS. jsdom lays nothing
 * out, so the rule is pinned by reading the stylesheet, the way the
 * hover-reveal test above does.
 */
describe('heading names are shown in full', () => {
  const stylesheet = async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const url = await import('node:url')
    const here = path.dirname(url.fileURLToPath(import.meta.url))
    return fs.readFileSync(path.resolve(here, '../index.css'), 'utf8')
  }
  // indexOf rather than a RegExp: a selector full of dots and underscores
  // needs escaping, and escaping is exactly what went wrong in the first
  // draft of this helper.
  const rule = (css: string, selector: string) => {
    const i = css.indexOf(String.fromCharCode(10) + selector + ' {')
    expect(i, `no rule for ${selector}`).toBeGreaterThan(-1)
    return css.slice(i, css.indexOf('}', i) + 1)
  }

  it('lets a folder or group name wrap rather than truncate', async () => {
    const name = rule(await stylesheet(), '.dl-fold__name')
    expect(name).not.toMatch(/white-space\s*:\s*nowrap/)
    expect(name).not.toMatch(/text-overflow\s*:\s*ellipsis/)
    expect(name).toMatch(/overflow-wrap\s*:\s*anywhere/)
  })

  it('gives the heading its whole row so nothing can squeeze it', async () => {
    expect(rule(await stylesheet(), '.dl-fold__title')).toMatch(/flex\s*:\s*1 1 auto/)
  })
})


/**
 * Folders and dashboards are managed from the page, now that the tree is not
 * mounted anywhere else. The strings are the tree's, character for character:
 * the delete prompt in particular says that nothing is destroyed, and a user
 * who has been burned by another tool will not believe that unless it is
 * written on the button.
 *
 * Every folder action reads `can_manage` from the server; the page never
 * decides who may rename or delete.
 */
describe('managing folders and dashboards from the page', () => {
  const node = (over: Record<string, unknown>) => ({
    id: 1, parent_id: null, node_type: 'folder', name: 'sameh', report_id: null,
    position: 0, can_manage: true, is_mine: true, role_ids: [], pages: [],
    children: [], ...over,
  })
  const leaf = (reportId: number) =>
    node({ id: 90 + reportId, node_type: 'report', name: 'x', report_id: reportId })
  const treeWith = (...roots: unknown[]) =>
    vi.mocked(workspaceApi.tree).mockResolvedValue({ roots, unfiled: [] } as never)
  const openMenu = (name: string) =>
    fireEvent.click(screen.getByRole('button', { name: `Actions for ${name}` }))
  const item = (name: RegExp) => screen.getByRole('menuitem', { name })

  beforeEach(() => {
    vi.mocked(workspaceApi.create).mockResolvedValue({} as never)
    vi.mocked(workspaceApi.update).mockResolvedValue({} as never)
    vi.mocked(workspaceApi.delete).mockResolvedValue(undefined as never)
  })

  it('creates a top-level folder from the page head, and shows it', async () => {
    treeWith(node({ children: [leaf(1)] }))
    renderReports()
    await screen.findByRole('heading', { name: 'sameh' })
    // The refresh after creating returns the tree with the new folder in it.
    treeWith(node({ children: [leaf(1)] }), node({ id: 2, name: 'Q4 planning' }))

    fireEvent.click(screen.getByRole('button', { name: 'New folder' }))

    // The name is asked for in a real, in-page dialog -- not a native prompt,
    // which the browser can suppress and no test or screen reader can reach.
    expect(await screen.findByRole('dialog', { name: 'New folder' })).toBeInTheDocument()
    await answerPrompt('Q4 planning')

    await waitFor(() => expect(workspaceApi.create).toHaveBeenCalledWith({ node_type: 'folder', name: 'Q4 planning' }))
    expect(await screen.findByRole('heading', { name: 'Q4 planning' })).toBeInTheDocument()
  })

  it("creates a subfolder from a folder's own menu", async () => {
    treeWith(node({ children: [leaf(1)] }))
    renderReports()
    await screen.findByRole('heading', { name: 'sameh' })
    openMenu('sameh')
    fireEvent.click(item(/new subfolder/i))

    expect(await screen.findByRole('dialog', { name: 'New subfolder' })).toBeInTheDocument()
    await answerPrompt('EMEA')

    await waitFor(() => expect(workspaceApi.create).toHaveBeenCalledWith({ node_type: 'folder', name: 'EMEA', parent_id: 1 }))
  })

  it('renames a folder', async () => {
    treeWith(node({ children: [leaf(1)] }))
    renderReports()
    await screen.findByRole('heading', { name: 'sameh' })
    treeWith(node({ name: 'Sales', children: [leaf(1)] }))

    openMenu('sameh')
    fireEvent.click(item(/rename/i))

    // Pre-filled with the current name, and selected, so typing replaces it.
    const renameFolderDialog = await screen.findByRole('dialog', { name: 'Rename folder' })
    expect(within(renameFolderDialog).getByRole('textbox')).toHaveValue('sameh')
    await answerPrompt('Sales')

    await waitFor(() => expect(workspaceApi.update).toHaveBeenCalledWith(1, { name: 'Sales' }))
    expect(await screen.findByRole('heading', { name: 'Sales' })).toBeInTheDocument()
  })

  it('deleting a folder says that its contents survive', async () => {
    treeWith(node({ children: [leaf(1)] }))
    renderReports()
    await screen.findByRole('heading', { name: 'sameh' })

    openMenu('sameh')
    fireEvent.click(item(/delete folder/i))

    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent('Delete the folder "sameh"?')
    expect(dialog).toHaveTextContent('Anything inside it moves up a level — no dashboards are deleted.')
    expect(workspaceApi.delete).not.toHaveBeenCalled()

    treeWith()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete folder' }))
    await waitFor(() => expect(workspaceApi.delete).toHaveBeenCalledWith(1))
    // The dashboard is still on the page -- re-parented, not deleted.
    expect(await screen.findByText('Revenue')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'sameh' })).toBeNull()
  })

  it('offers no folder actions on a folder the viewer cannot manage', async () => {
    // can_manage is the server's answer. No menu, rather than a menu of
    // items the server would refuse.
    treeWith(node({ can_manage: false, children: [leaf(1)] }))
    renderReports()
    await screen.findByRole('heading', { name: 'sameh' })
    expect(screen.queryByRole('button', { name: 'Actions for sameh' })).toBeNull()
  })

  it('renames a dashboard from its card', async () => {
    vi.mocked(reportsApi.update).mockResolvedValue({} as never)
    renderReports()
    await screen.findByText('Revenue')
    fireEvent.click(screen.getByRole('button', { name: 'Rename dashboard Revenue' }))

    const renameDialog = await screen.findByRole('dialog', { name: 'Rename dashboard' })
    expect(within(renameDialog).getByRole('textbox')).toHaveValue('Revenue')
    await answerPrompt('Income')

    await waitFor(() => expect(reportsApi.update).toHaveBeenCalledWith(1, { name: 'Income' }))
    expect(await screen.findByText('Income')).toBeInTheDocument()
    expect(screen.queryByText('Revenue')).toBeNull()
  })

  it('does not rename when the prompt is cancelled or unchanged', async () => {
    vi.mocked(reportsApi.update).mockResolvedValue({} as never)
    renderReports()
    await screen.findByText('Revenue')
    fireEvent.click(screen.getByRole('button', { name: 'Rename dashboard Revenue' }))
    await answerPrompt(null)

    fireEvent.click(screen.getByRole('button', { name: 'Rename dashboard Revenue' }))
    // Same name back, padded: trimmed to the original, so nothing is written.
    await answerPrompt('  Revenue ')

    expect(reportsApi.update).not.toHaveBeenCalled()
  })

  it('a view-only dashboard offers no rename', async () => {
    // Mirrors delete: the server requires >= edit to change a report, so a
    // viewer gets no control that would be refused.
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ my_capability: 'view', is_mine: false, created_by: 8 }),
    ] as never)
    renderReports()
    await screen.findByText('Revenue')
    expect(screen.queryByRole('button', { name: /rename dashboard/i })).toBeNull()
  })
})


/**
 * Moving a dashboard is a drag onto a folder heading, then a question.
 *
 * The question, because a drop is the easiest gesture to make by accident
 * and a move can change who sees the dashboard (folder grants reach into
 * the folder). The server still has the last word: the page sends the move
 * it was asked for and shows the refusal it gets back, never a guess of its
 * own about what is allowed.
 */
describe('moving a dashboard between folders by drag and drop', () => {
  const node = (over: Record<string, unknown>) => ({
    id: 1, parent_id: null, node_type: 'folder', name: 'sameh', report_id: null,
    position: 0, can_manage: true, is_mine: true, role_ids: [], pages: [],
    children: [], ...over,
  })
  const leaf = (reportId: number, parent: number | null = 1) =>
    node({ id: 90 + reportId, parent_id: parent, node_type: 'report', name: 'x', report_id: reportId })
  const twoFolders = (unfiled: unknown[] = []) =>
    vi.mocked(workspaceApi.tree).mockResolvedValue({
      roots: [node({ children: [leaf(1)] }), node({ id: 9, name: 'Archive', children: [] })],
      unfiled,
    } as never)
  const card = (name: string) => screen.getByText(name).closest('.dl-dash-card') as HTMLElement
  const headOf = (name: string) => screen.getByRole('heading', { name }).parentElement as HTMLElement
  const drag = (what: string, onto: string) => {
    fireEvent.dragStart(card(what))
    fireEvent.dragOver(headOf(onto))
    fireEvent.drop(headOf(onto))
  }

  beforeEach(() => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 1, name: 'Revenue' }),
      report({ id: 2, name: 'Costs' }),
    ] as never)
    vi.mocked(workspaceApi.update).mockResolvedValue({} as never)
    vi.mocked(workspaceApi.create).mockResolvedValue({} as never)
  })

  it('asks first, then moves the node into the folder it was dropped on', async () => {
    twoFolders([leaf(2, null)])
    renderReports()
    await screen.findByRole('heading', { name: 'Archive' })

    drag('Revenue', 'Archive')

    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent('Move "Revenue" to "Archive"?')
    expect(workspaceApi.update).not.toHaveBeenCalled()

    // The refresh after the move returns Revenue under Archive.
    vi.mocked(workspaceApi.tree).mockResolvedValue({
      roots: [node({ children: [] }), node({ id: 9, name: 'Archive', children: [leaf(1, 9)] })],
      unfiled: [leaf(2, null)],
    } as never)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Move' }))

    await waitFor(() => expect(workspaceApi.update).toHaveBeenCalledWith(91, { parent_id: 9 }))
    const archive = await screen.findByRole('region', { name: 'Archive' })
    expect(await within(archive).findByText('Revenue')).toBeInTheDocument()
    expect(toast.success).toHaveBeenCalled()
  })

  it('does nothing when the move is cancelled', async () => {
    twoFolders([leaf(2, null)])
    renderReports()
    await screen.findByRole('heading', { name: 'Archive' })

    drag('Revenue', 'Archive')
    const dialog = await screen.findByRole('alertdialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(workspaceApi.update).not.toHaveBeenCalled()
    expect(workspaceApi.create).not.toHaveBeenCalled()
    expect(within(screen.getByRole('region', { name: 'sameh' })).getByText('Revenue')).toBeInTheDocument()
  })

  it('files a loose dashboard by creating its node', async () => {
    // An unfiled dashboard has no node row yet (id 0), so there is nothing
    // to re-parent: the move IS the creation of its node.
    twoFolders([node({ id: 0, node_type: 'report', name: 'x', report_id: 2 })])
    renderReports()
    await screen.findByText('Costs')

    drag('Costs', 'Archive')
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Move' }))

    await waitFor(() => expect(workspaceApi.create).toHaveBeenCalledWith({
      node_type: 'report', report_id: 2, parent_id: 9,
    }))
    expect(workspaceApi.update).not.toHaveBeenCalled()
  })

  it('moves a dashboard out to the top level via the group heading', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 1, name: 'Revenue' }),
      report({ id: 3, name: 'Theirs', is_mine: false, my_capability: 'view', created_by: 8 }),
    ] as never)
    twoFolders([leaf(3, null)])
    renderReports()
    await screen.findByRole('heading', { name: 'My workspaces' })

    drag('Revenue', 'My workspaces')
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent('Move "Revenue" to the top level?')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Move' }))

    await waitFor(() => expect(workspaceApi.update).toHaveBeenCalledWith(91, { parent_id: null }))
  })

  it('asks nothing when a dashboard is dropped where it already is', async () => {
    twoFolders([leaf(2, null)])
    renderReports()
    await screen.findByRole('heading', { name: 'Archive' })

    drag('Revenue', 'sameh')

    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(workspaceApi.update).not.toHaveBeenCalled()
  })

  it("shows the server's refusal rather than pre-empting it", async () => {
    // Who may move what into where is the server's rule (can_manage, the
    // cycle guard). The page sends the move and repeats the answer.
    twoFolders([leaf(2, null)])
    vi.mocked(workspaceApi.update).mockRejectedValue(
      { response: { data: { detail: 'You cannot manage the folder "Archive"' } } })
    renderReports()
    await screen.findByRole('heading', { name: 'Archive' })

    drag('Revenue', 'Archive')
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Move' }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('You cannot manage the folder "Archive"'))
    // Unchanged on screen: the server said no.
    expect(within(screen.getByRole('region', { name: 'sameh' })).getByText('Revenue')).toBeInTheDocument()
  })
})

describe('creating a dashboard', () => {
  it('New dashboard opens the builder at once, auto-named, asking for data', async () => {
    vi.mocked(reportsApi.create).mockResolvedValue(report({ id: 77, name: 'Untitled dashboard' }) as never)
    renderReports()
    fireEvent.click(await screen.findByRole('button', { name: /New dashboard/i }))
    await waitFor(() => expect(reportsApi.create).toHaveBeenCalledWith({ name: 'Untitled dashboard' }))
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/reports/77'))
  })
})

describe('nextUntitledName', () => {
  it('never repeats a name already taken', () => {
    expect(nextUntitledName([])).toBe('Untitled dashboard')
    expect(nextUntitledName(['Untitled dashboard'])).toBe('Untitled dashboard 2')
    expect(nextUntitledName(['untitled dashboard', 'Untitled dashboard 2'])).toBe('Untitled dashboard 3')
  })
})

describe('Reports accessibility', () => {
  it('has no structural accessibility violations', async () => {
    const { container } = renderReports()
    await screen.findByText('Revenue')
    expect(await axeViolations(container)).toEqual([])
  })
})
