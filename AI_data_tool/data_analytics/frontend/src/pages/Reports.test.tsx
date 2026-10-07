import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import Reports, { nextUntitledName } from './Reports'
import { reportsApi, reportGrantsApi, datasetsApi, workspaceApi, pageTemplatesApi } from '../services/api'
import { ConfirmProvider } from '../components/ui/ConfirmDialog'
import { PromptProvider } from '../components/ui/PromptDialog'
import { AuthContext } from '../contexts/AuthContext'
import { answerPrompt } from '../test/renderWithProviders'
import toast from 'react-hot-toast'
import { axeViolations } from '../test/axe'

/**
 * The Dashboards page (redesign 7b). What is pinned: every control the server
 * would refuse is absent, a drop or a delete is confirmed before anything is
 * sent, the server's refusal is shown as given, folders come from the tree and
 * fail on their own, and nothing the backend cannot answer is pretended.
 */

vi.mock('../services/api', () => ({
  reportsApi: { list: vi.fn(), recent: vi.fn(), delete: vi.fn(), create: vi.fn(), update: vi.fn(), setPublished: vi.fn(),
    downloadPdf: vi.fn(), deletePage: vi.fn() },
  reportGrantsApi: { list: vi.fn(), create: vi.fn(), remove: vi.fn() },
  datasetsApi: { list: vi.fn() },
  workspaceApi: { tree: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
  pageTemplatesApi: { builtins: vi.fn(), addFrom: vi.fn() },
  authzApi: { decisions: vi.fn(async () => []) },
  shareLinksApi: { list: vi.fn(async () => []), create: vi.fn(), revoke: vi.fn() },
  embedConfigsApi: { list: vi.fn(async () => []), create: vi.fn(), setEnabled: vi.fn(), delete: vi.fn() },
}))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))
vi.mock('../components/dataset/SuggestDashboardsDialog', () => ({
  default: (p: { datasetName: string; initialGoal?: string }) =>
    <div data-testid="suggest-dialog">{p.datasetName}|{p.initialGoal}</div>,
}))

/** Renders the current path, so navigation is observable rather than implied. */
function Where() {
  const { pathname, search } = useLocation()
  return <div data-testid="where">{pathname}{search}</div>
}

const renderReports = (opts: { admin?: boolean; at?: string } = {}) =>
  render(
    <AuthContext.Provider value={{ user: { id: 7, email: 'me@x.io', role: { is_org_admin: !!opts.admin } } as never,
      loading: false, login: async () => {}, logout: () => {} }}>
      <ConfirmProvider><PromptProvider>
        <MemoryRouter initialEntries={[opts.at ?? '/reports']}>
          <Reports />
          <Where />
        </MemoryRouter>
      </PromptProvider></ConfirmProvider>
    </AuthContext.Provider>,
  )

// `my_capability` is spelled out: the page fails closed on a missing one.
const report = (over = {}) => ({
  id: 1, name: 'Revenue', description: '', dataset_id: undefined, pages: [],
  my_capability: 'data', created_by: 7, is_mine: true, published: false,
  created_at: '2026-08-22T00:00:00Z', updated_at: '2026-09-01T00:00:00Z', ...over,
})
const node = (over: Record<string, unknown>) => ({
  id: 1, parent_id: null, node_type: 'folder', name: 'Finance', report_id: null,
  position: 0, can_manage: true, is_mine: true, role_ids: [], pages: [], children: [], ...over,
})
const leaf = (reportId: number, parent: number | null = 1, over: Record<string, unknown> = {}) =>
  node({ id: 90 + reportId, parent_id: parent, node_type: 'report', name: 'x', report_id: reportId, ...over })

const card = (id: number) => screen.getByTestId(`dash-card-${id}`)
const nav = () => screen.getByTestId('dash-nav')
/** A folder's button in the side column (its menu trigger also names it). */
const folderBtn = async (name: string) => {
  await waitFor(() => expect(nav().querySelector(`[data-folder="${name}"]`)).not.toBeNull())
  return nav().querySelector(`[data-folder="${name}"]`) as HTMLElement
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  vi.mocked(datasetsApi.list).mockResolvedValue([] as never)
  vi.mocked(reportsApi.list).mockResolvedValue([report()] as never)
  vi.mocked(reportsApi.recent).mockResolvedValue([] as never)
  vi.mocked(reportsApi.delete).mockResolvedValue(undefined as never)
  vi.mocked(workspaceApi.tree).mockResolvedValue({ roots: [], unfiled: [] } as never)
  vi.mocked(workspaceApi.update).mockResolvedValue({} as never)
  vi.mocked(workspaceApi.create).mockResolvedValue({} as never)
})

describe('deleting', () => {
  it('confirms, then deletes', async () => {
    renderReports()
    await screen.findByTestId('dash-card-1')
    fireEvent.click(within(card(1)).getByRole('button', { name: 'More actions for Revenue' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent('Delete dashboard "Revenue"?')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(reportsApi.delete).toHaveBeenCalledWith(1))
    await waitFor(() => expect(screen.queryByTestId('dash-card-1')).not.toBeInTheDocument())
  })

  it('ticking cards selects them and deletes them together, after naming them', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([report({ id: 1, name: 'A' }), report({ id: 2, name: 'B' })] as never)
    renderReports()
    await screen.findByTestId('dash-card-2')
    fireEvent.click(within(card(1)).getByRole('checkbox', { name: /A/ }))
    // Once something is ticked, a click on another card ticks it too.
    fireEvent.click(card(2))
    const bar = screen.getByRole('toolbar')
    expect(bar).toHaveTextContent('2')
    fireEvent.click(within(bar).getByRole('button', { name: /Delete/ }))
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent('A')
    expect(dialog).toHaveTextContent('B')
    fireEvent.click(within(dialog).getByRole('button', { name: /Delete/ }))
    await waitFor(() => expect(reportsApi.delete).toHaveBeenCalledTimes(2))
  })

  it('a view-only dashboard has no Delete, no tick box, and says it is view only', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([report({ id: 3, name: 'Theirs', my_capability: 'view', is_mine: false, created_by: 4 })] as never)
    renderReports()
    await screen.findByTestId('dash-card-3')
    expect(card(3)).toHaveTextContent('View only')
    expect(within(card(3)).queryByRole('checkbox')).not.toBeInTheDocument()
    fireEvent.click(within(card(3)).getByRole('button', { name: 'More actions for Theirs' }))
    const menu = await screen.findByRole('menu')
    expect(within(menu).queryByRole('menuitem', { name: 'Delete' })).not.toBeInTheDocument()
    expect(within(menu).queryByRole('menuitem', { name: 'Rename' })).not.toBeInTheDocument()
    expect(within(menu).getByRole('menuitem', { name: 'Export as PDF' })).toBeInTheDocument()
  })
})

describe('publish and share', () => {
  it('the author gets Share and Publish; publishing calls the API and shows the badge', async () => {
    vi.mocked(reportsApi.setPublished).mockResolvedValue({ published: true } as never)
    renderReports()
    await screen.findByTestId('dash-card-1')
    expect(card(1)).toHaveTextContent('Draft')
    expect(within(card(1)).getByRole('button', { name: 'Share Revenue' })).toBeInTheDocument()
    fireEvent.click(within(card(1)).getByRole('button', { name: 'More actions for Revenue' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Publish' }))
    await waitFor(() => expect(reportsApi.setPublished).toHaveBeenCalledWith(1, true))
    await waitFor(() => expect(card(1)).toHaveTextContent('Published'))
  })

  it('a legacy dashboard (no author) offers no Publish and wears no status', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([report({ created_by: null, is_mine: false })] as never)
    renderReports()
    await screen.findByTestId('dash-card-1')
    expect(card(1)).not.toHaveTextContent('Draft')
    fireEvent.click(within(card(1)).getByRole('button', { name: 'More actions for Revenue' }))
    expect(within(await screen.findByRole('menu')).queryByRole('menuitem', { name: 'Publish' })).not.toBeInTheDocument()
  })

  it("someone else's dashboard offers no Share, unless the viewer is an admin", async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([report({ is_mine: false, created_by: 4 })] as never)
    const { unmount } = renderReports()
    await screen.findByTestId('dash-card-1')
    expect(within(card(1)).queryByRole('button', { name: 'Share Revenue' })).not.toBeInTheDocument()
    unmount()
    renderReports({ admin: true })
    await screen.findByTestId('dash-card-1')
    expect(within(card(1)).getByRole('button', { name: 'Share Revenue' })).toBeInTheDocument()
  })

  it('the share dialog lists grants and posts a new one by email', async () => {
    vi.mocked(reportGrantsApi.list).mockResolvedValue([{ id: 5, user_id: 2, email: 'a@x.io', level: 'view' }] as never)
    vi.mocked(reportGrantsApi.create).mockResolvedValue({ id: 6, user_id: 3, email: 'b@x.io', level: 'edit' } as never)
    renderReports()
    await screen.findByTestId('dash-card-1')
    fireEvent.click(within(card(1)).getByRole('button', { name: 'Share Revenue' }))
    const dialog = await screen.findByRole('dialog', { name: 'Share Revenue' })
    expect(await within(dialog).findByText('a@x.io')).toBeInTheDocument()
    fireEvent.change(within(dialog).getByLabelText('Email to share with'), { target: { value: 'b@x.io' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Invite' }))
    await waitFor(() => expect(reportGrantsApi.create).toHaveBeenCalledWith(1, { email: 'b@x.io', level: 'edit' }))
  })
})

describe('opening a dashboard', () => {
  it('the title is a real anchor, and a click shows the loader', async () => {
    renderReports()
    const link = await screen.findByRole('link', { name: 'Revenue' })
    expect(link).toHaveAttribute('href', '/reports/1')
    fireEvent.click(link)
    expect(await screen.findByRole('status')).toBeInTheDocument()
  })

  it('a ctrl-click (new tab) keeps the list', async () => {
    renderReports()
    fireEvent.click(await screen.findByRole('link', { name: 'Revenue' }), { ctrlKey: true })
    expect(screen.getByTestId('dash-card-1')).toBeInTheDocument()
  })

  it('the card has one tab stop: the title link', async () => {
    renderReports()
    await screen.findByTestId('dash-card-1')
    expect(card(1)).not.toHaveAttribute('tabindex')
    expect(within(card(1)).getAllByRole('link')).toHaveLength(1)
  })
})

describe('what a card says', () => {
  it('a Suggest dashboards card wears the AI badge and keeps its goal, without the prefix', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 1, name: 'A', description: 'Suggested from the data' }),
      report({ id: 2, name: 'B', description: 'Suggested for: churn by month' }),
    ] as never)
    renderReports()
    await screen.findByTestId('dash-card-2')
    expect(card(1)).toHaveTextContent('AI suggestion')
    expect(card(1)).not.toHaveTextContent('Suggested from the data')
    expect(card(2)).toHaveTextContent('churn by month')
    expect(card(2)).not.toHaveTextContent('Suggested for:')
  })

  it('drops the dataset chip when the title already names the dataset', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([{ id: 4, name: 'Demo Sales' }] as never)
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 1, name: 'What stands out in demo  sales', dataset_id: 4 }),
      report({ id: 2, name: 'Quarterly', dataset_id: 4 }),
    ] as never)
    renderReports()
    await waitFor(() => expect(card(2)).toHaveTextContent('Demo Sales'))
    expect(card(1)).not.toHaveTextContent('Demo Sales')
  })

  it('says how many pages when there is no description', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([report({ pages: [{ id: 1, page_type: 'normal', widgets: [] }, { id: 2, page_type: 'normal', widgets: [] }] })] as never)
    renderReports()
    expect(await screen.findByTestId('dash-card-1')).toHaveTextContent(/2 pages/)
  })
})

describe('folders', () => {
  const tree = () => vi.mocked(workspaceApi.tree).mockResolvedValue({
    roots: [node({ id: 1, name: 'Finance', children: [leaf(1), node({ id: 2, parent_id: 1, name: 'Board', children: [leaf(2, 2)] })] }),
      node({ id: 3, name: 'Empty', children: [] })],
    unfiled: [leaf(3, null, { id: 0 })],
  } as never)
  beforeEach(() => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 1, name: 'Revenue' }), report({ id: 2, name: 'Pack' }), report({ id: 3, name: 'Loose' }),
    ] as never)
    tree()
  })

  it('groups the cards under folder headings, subfolders inside, loose ones last', async () => {
    renderReports()
    const finance = await screen.findByRole('region', { name: 'Finance' })
    expect(within(finance).getByTestId('dash-card-1')).toBeInTheDocument()
    const board = within(finance).getByRole('region', { name: 'Board' })
    expect(within(board).getByTestId('dash-card-2')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Not in a folder' })).getByTestId('dash-card-3')).toBeInTheDocument()
    // A folder with nothing in it is still shown, so it can be filled or deleted.
    expect(within(screen.getByRole('region', { name: 'Empty' })).getByText('Empty folder')).toBeInTheDocument()
  })

  it('lists the folders in the side column with what each holds, subtree included', async () => {
    renderReports()
    const finance = await folderBtn('Finance')
    expect(finance).toHaveTextContent('2')
  })

  it('choosing a folder shows only what is in it', async () => {
    renderReports()
    fireEvent.click(await folderBtn('Board'))
    expect(screen.getByTestId('dash-card-2')).toBeInTheDocument()
    expect(screen.queryByTestId('dash-card-1')).not.toBeInTheDocument()
    expect(screen.queryByTestId('dash-card-3')).not.toBeInTheDocument()
  })

  it('an empty folder says so and offers a dashboard there', async () => {
    vi.mocked(pageTemplatesApi.builtins).mockResolvedValue([] as never)
    renderReports()
    fireEvent.click(await folderBtn('Empty'))
    expect(screen.getByTestId('dash-folder-empty')).toHaveTextContent('This folder is empty')
    fireEvent.click(screen.getByRole('button', { name: 'New dashboard here' }))
    expect(await screen.findByLabelText('Folder')).toHaveValue('3')
  })

  it('headings collapse, and the choice is remembered', async () => {
    const { unmount } = renderReports()
    const finance = await screen.findByRole('region', { name: 'Finance' })
    const toggle = within(finance).getAllByRole('button', { name: /Finance/ })[0]
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId('dash-card-1')).not.toBeInTheDocument()
    unmount()
    renderReports()
    const again = await screen.findByRole('region', { name: 'Finance' })
    expect(within(again).getAllByRole('button', { name: /Finance/ })[0]).toHaveAttribute('aria-expanded', 'false')
  })

  it('still lists every dashboard when the tree fails, and says the folders did not load', async () => {
    vi.mocked(workspaceApi.tree).mockRejectedValue(new Error('down'))
    renderReports()
    expect(await screen.findByText("Folders couldn't load.")).toBeInTheDocument()
    for (const id of [1, 2, 3]) expect(screen.getByTestId(`dash-card-${id}`)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New folder' })).not.toBeInTheDocument()
  })

  it('creates a top-level folder inline, in the side column', async () => {
    renderReports()
    await screen.findByTestId('dash-card-1')
    fireEvent.click(screen.getAllByRole('button', { name: 'New folder' })[0])
    fireEvent.change(within(nav()).getByRole('textbox', { name: 'Folder name' }), { target: { value: 'Ops' } })
    fireEvent.click(within(nav()).getByRole('button', { name: 'Create folder' }))
    await waitFor(() => expect(workspaceApi.create).toHaveBeenCalledWith({ node_type: 'folder', name: 'Ops' }))
  })

  it("creates a subfolder, renames and deletes a folder from its menu; deleting says contents survive", async () => {
    vi.mocked(workspaceApi.delete).mockResolvedValue(undefined as never)
    renderReports()
    const row = (await folderBtn('Finance')).parentElement as HTMLElement
    const menuBtn = () => within(row).getByRole('button', { name: 'Actions for Finance' })
    fireEvent.click(menuBtn())
    fireEvent.click(await screen.findByRole('menuitem', { name: 'New subfolder' }))
    await answerPrompt('Q3')
    await waitFor(() => expect(workspaceApi.create).toHaveBeenCalledWith({ node_type: 'folder', name: 'Q3', parent_id: 1 }))

    fireEvent.click(menuBtn())
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Rename' }))
    await answerPrompt('Money')
    await waitFor(() => expect(workspaceApi.update).toHaveBeenCalledWith(1, { name: 'Money' }))

    fireEvent.click(menuBtn())
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete folder' }))
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent('No dashboards are deleted')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete folder' }))
    await waitFor(() => expect(workspaceApi.delete).toHaveBeenCalledWith(1))
  })

  it('offers no folder actions on a folder the viewer cannot manage', async () => {
    vi.mocked(workspaceApi.tree).mockResolvedValue({ roots: [node({ can_manage: false, children: [leaf(1)] })], unfiled: [] } as never)
    renderReports()
    const row = (await folderBtn('Finance')).parentElement as HTMLElement
    expect(within(row).getAllByRole('button')).toHaveLength(1)
  })
})

describe('moving a dashboard', () => {
  beforeEach(() => {
    vi.mocked(reportsApi.list).mockResolvedValue([report({ id: 1, name: 'Revenue' }), report({ id: 2, name: 'Costs' })] as never)
    vi.mocked(workspaceApi.tree).mockResolvedValue({
      roots: [node({ id: 1, name: 'Finance', children: [leaf(1)] }), node({ id: 9, name: 'Archive', children: [] })],
      unfiled: [leaf(2, null, { id: 0 })],
    } as never)
  })
  const folderRow = (name: string) => (nav().querySelector(`[data-folder="${name}"]`) as HTMLElement).parentElement as HTMLElement
  const drag = (id: number, onto: string) => {
    fireEvent.dragStart(card(id))
    fireEvent.dragOver(folderRow(onto))
    fireEvent.drop(folderRow(onto))
  }

  it('a drop onto a folder asks first, then re-parents the node', async () => {
    renderReports()
    await folderBtn('Archive')
    drag(1, 'Archive')
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent('Move "Revenue" to Archive?')
    expect(dialog).toHaveTextContent('Anyone the destination folder is shared with')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Move' }))
    await waitFor(() => expect(workspaceApi.update).toHaveBeenCalledWith(91, { parent_id: 9 }))
  })

  it('nothing is sent when the move is cancelled', async () => {
    renderReports()
    await folderBtn('Archive')
    drag(1, 'Archive')
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(workspaceApi.update).not.toHaveBeenCalled()
  })

  it('files a loose dashboard by creating its node', async () => {
    renderReports()
    await folderBtn('Archive')
    drag(2, 'Archive')
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Move' }))
    await waitFor(() => expect(workspaceApi.create).toHaveBeenCalledWith({ node_type: 'report', report_id: 2, parent_id: 9 }))
  })

  it('asks nothing when it is dropped where it already is', async () => {
    renderReports()
    await folderBtn('Finance')
    drag(1, 'Finance')
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it("shows the server's refusal as given", async () => {
    vi.mocked(workspaceApi.update).mockRejectedValue({ response: { data: { detail: 'Only the author can move this' } } })
    renderReports()
    await folderBtn('Archive')
    drag(1, 'Archive')
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Move' }))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Only the author can move this'))
  })

  it('Move to folder… picks a folder in a dialog', async () => {
    renderReports()
    await screen.findByTestId('dash-card-1')
    fireEvent.click(within(card(1)).getByRole('button', { name: 'More actions for Revenue' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Move to folder…' }))
    const dialog = await screen.findByRole('dialog', { name: 'Move "Revenue" to…' })
    // Its own folder is not offered.
    expect(within(dialog).queryByRole('radio', { name: 'Finance' })).not.toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('radio', { name: 'Archive' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Move' }))
    await waitFor(() => expect(workspaceApi.update).toHaveBeenCalledWith(91, { parent_id: 9 }))
  })
})

describe('views, search and facets', () => {
  beforeEach(() => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 1, name: 'Revenue', published: true }),
      report({ id: 2, name: 'Costs', published: false, dataset_id: 4 }),
      report({ id: 3, name: 'Granted', is_mine: false, created_by: 5, published: true }),
    ] as never)
    vi.mocked(datasetsApi.list).mockResolvedValue([{ id: 4, name: 'Ledger' }] as never)
  })

  it('Recent lists what this person opened, in that order', async () => {
    vi.mocked(reportsApi.recent).mockResolvedValue([{ id: 3 }, { id: 1 }] as never)
    renderReports()
    fireEvent.click(await within(nav()).findByRole('button', { name: /Recent/ }))
    const names = screen.getAllByRole('heading', { level: 3 }).map(h => h.textContent)
    expect(names).toEqual(['Granted', 'Revenue'])
  })

  it('Shared with me lists only what was deliberately granted, not merely not mine', async () => {
    vi.mocked(workspaceApi.tree).mockResolvedValue({ roots: [], unfiled: [
      leaf(3, null, { id: 0, shared_with_me: true, is_mine: false }), leaf(1, null, { id: 0 }),
    ] } as never)
    renderReports()
    const item = await within(nav()).findByRole('button', { name: /Shared with me/ })
    await waitFor(() => expect(item).toHaveTextContent('1'))
    fireEvent.click(item)
    expect(screen.getByTestId('dash-card-3')).toBeInTheDocument()
    expect(screen.queryByTestId('dash-card-1')).not.toBeInTheDocument()
  })

  it('the status filter narrows to drafts or published, with counts', async () => {
    renderReports()
    const drafts = await screen.findByRole('button', { name: /Drafts/ })
    expect(drafts).toHaveTextContent('1')
    fireEvent.click(drafts)
    expect(screen.getByTestId('dash-card-2')).toBeInTheDocument()
    expect(screen.queryByTestId('dash-card-1')).not.toBeInTheDocument()
  })

  it('the dataset filter narrows to one dataset', async () => {
    renderReports()
    fireEvent.click(await screen.findByRole('button', { name: 'Dataset: Any' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Ledger' }))
    expect(screen.getByTestId('dash-card-2')).toBeInTheDocument()
    expect(screen.queryByTestId('dash-card-1')).not.toBeInTheDocument()
  })

  it('one ticked dashboard and one search result read in the singular (QA V2, V3)', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue(Array.from({ length: 9 }, (_, i) => report({ id: i + 1, name: `Board ${i}` })) as never)
    renderReports()
    const box = await screen.findByRole('searchbox', { name: /Search dashboards/ })
    fireEvent.change(box, { target: { value: 'Board 3' } })
    expect(screen.getByText('1 result')).toBeInTheDocument()
    fireEvent.click(within(card(4)).getByRole('checkbox'))
    expect(screen.getByRole('toolbar')).toHaveTextContent('1 dashboard selected')
  })

  it('the searched text in the no-match title keeps its own direction (QA V3)', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue(Array.from({ length: 9 }, (_, i) => report({ id: i + 1, name: `Board ${i}` })) as never)
    renderReports()
    fireEvent.change(await screen.findByRole('searchbox', { name: /Search dashboards/ }), { target: { value: 'QA-' } })
    const title = screen.getByText((_, el) => el?.tagName === 'H2' && el.textContent === 'No dashboards match "QA-"')
    expect(title.querySelector('bdi')).toHaveTextContent(/^QA-$/)
  })

  it('one test-looking dashboard is offered in the singular (QA V2)', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([report({ id: 1, name: 'Revenue' }), report({ id: 2, name: 'test 2' })] as never)
    renderReports()
    await screen.findByTestId('dash-card-2')
    fireEvent.click(within(card(1)).getByRole('checkbox'))
    expect(within(screen.getByRole('toolbar')).getByRole('button', { name: 'Also select the one that looks like test data' })).toBeInTheDocument()
  })

  it('the list cells that clip take the direction of their own text (QA V1)', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([report({ id: 2, name: 'Costs', dataset_id: 4 })] as never)
    renderReports()
    await screen.findByTestId('dash-card-2')
    fireEvent.click(screen.getByRole('button', { name: 'List view' }))
    const row = screen.getByTestId('dash-row-2')
    // The span that clips, not a <bdi> inside it: an English name in an
    // Arabic row then loses its end, not its start.
    expect(within(row).getByText('Ledger').closest('[dir="auto"]')).not.toBeNull()
    expect(within(row).getAllByText('Not in a folder')[0].closest('[dir="auto"]')).not.toBeNull()
  })

  it('a search with no match says what was searched and offers a way out', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue(Array.from({ length: 9 }, (_, i) => report({ id: i + 1, name: `Board ${i}` })) as never)
    renderReports()
    const box = await screen.findByRole('searchbox', { name: /Search dashboards/ })
    fireEvent.change(box, { target: { value: 'zzz' } })
    // The whole heading's text: the query sits in a <bdi> (QA V3), which splits the text nodes.
    const title = screen.getByText((_, el) => el?.tagName === 'H2' && el.textContent === 'No dashboards match "zzz"')
    fireEvent.click(within(title.parentElement as HTMLElement).getByRole('button', { name: 'Clear search' }))
    expect(screen.getByTestId('dash-card-1')).toBeInTheDocument()
  })

  it('the search also matches the dataset name', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      ...Array.from({ length: 8 }, (_, i) => report({ id: i + 10, name: `Board ${i}` })), report({ id: 2, name: 'Costs', dataset_id: 4 }),
    ] as never)
    renderReports()
    await waitFor(() => expect(screen.getByTestId('dash-card-2')).toHaveTextContent('Ledger'))
    fireEvent.change(screen.getByRole('searchbox', { name: /Search dashboards/ }), { target: { value: 'ledger' } })
    expect(screen.getByTestId('dash-card-2')).toBeInTheDocument()
    expect(screen.queryByTestId('dash-card-10')).not.toBeInTheDocument()
  })

  it('list view is a table with folder, dataset and status, and is remembered', async () => {
    const { unmount } = renderReports()
    await screen.findByTestId('dash-card-1')
    fireEvent.click(screen.getByRole('button', { name: 'List view' }))
    const table = screen.getByTestId('dash-table')
    expect(within(table).getByTestId('dash-row-2')).toHaveTextContent('Ledger')
    expect(within(table).getByTestId('dash-row-2')).toHaveTextContent('Draft')
    unmount()
    renderReports()
    expect(await screen.findByTestId('dash-table')).toBeInTheDocument()
  })
})

describe('partial failures', () => {
  it('a failed datasets call hides the dataset chips and filter, and nothing else', async () => {
    vi.mocked(datasetsApi.list).mockRejectedValue(new Error('down'))
    vi.mocked(reportsApi.list).mockResolvedValue([report({ dataset_id: 4 })] as never)
    renderReports()
    expect(await screen.findByTestId('dash-card-1')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Dataset:/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('a failed recents call leaves Recent without a count, and the page works', async () => {
    vi.mocked(reportsApi.recent).mockRejectedValue(new Error('down'))
    renderReports()
    await screen.findByTestId('dash-card-1')
    expect(within(nav()).getByRole('button', { name: /Recent/ })).not.toHaveTextContent(/\d/)
  })
})

describe('renaming', () => {
  it('renames from the card menu', async () => {
    vi.mocked(reportsApi.update).mockResolvedValue({} as never)
    renderReports()
    await screen.findByTestId('dash-card-1')
    fireEvent.click(within(card(1)).getByRole('button', { name: 'More actions for Revenue' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Rename' }))
    await answerPrompt('Income')
    await waitFor(() => expect(reportsApi.update).toHaveBeenCalledWith(1, { name: 'Income' }))
    expect(await screen.findByRole('link', { name: 'Income' })).toBeInTheDocument()
  })

  it('does nothing when the prompt is cancelled', async () => {
    renderReports()
    await screen.findByTestId('dash-card-1')
    fireEvent.click(within(card(1)).getByRole('button', { name: 'More actions for Revenue' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Rename' }))
    await answerPrompt(null)
    expect(reportsApi.update).not.toHaveBeenCalled()
  })
})

describe('creating a dashboard', () => {
  beforeEach(() => {
    vi.mocked(datasetsApi.list).mockResolvedValue([{ id: 4, name: 'Ledger' }] as never)
    vi.mocked(reportsApi.create).mockResolvedValue({ id: 42, pages: [{ id: 420 }] } as never)
  })

  it('Blank with no data opens the builder asking for data, auto-named', async () => {
    renderReports()
    await screen.findByTestId('dash-card-1')
    fireEvent.click(screen.getByRole('button', { name: 'New dashboard' }))
    const dialog = await screen.findByRole('dialog', { name: 'Create a dashboard' })
    fireEvent.click(within(dialog).getByRole('button', { name: /^Create$/ }))
    await waitFor(() => expect(reportsApi.create).toHaveBeenCalledWith({ name: 'Untitled dashboard' }))
    expect(await screen.findByTestId('where')).toHaveTextContent('/reports/42?pick=data')
  })

  it('Blank with a dataset and a folder files it there', async () => {
    vi.mocked(workspaceApi.tree).mockResolvedValue({ roots: [node({ id: 5, name: 'Finance' })], unfiled: [] } as never)
    renderReports()
    await folderBtn('Finance')
    fireEvent.click(screen.getByRole('button', { name: 'New dashboard' }))
    const dialog = await screen.findByRole('dialog', { name: 'Create a dashboard' })
    fireEvent.change(within(dialog).getByLabelText('Dashboard name'), { target: { value: 'Q3' } })
    fireEvent.change(within(dialog).getByLabelText('Dataset'), { target: { value: '4' } })
    fireEvent.change(within(dialog).getByLabelText('Folder'), { target: { value: '5' } })
    fireEvent.click(within(dialog).getByRole('button', { name: /^Create$/ }))
    await waitFor(() => expect(reportsApi.create).toHaveBeenCalledWith({ name: 'Q3', dataset_id: 4 }))
    await waitFor(() => expect(workspaceApi.create).toHaveBeenCalledWith({ node_type: 'report', report_id: 42, parent_id: 5 }))
    expect(await screen.findByTestId('where')).toHaveTextContent('/reports/42')
  })

  it('Template adds the template page and drops the empty default page', async () => {
    vi.mocked(pageTemplatesApi.builtins).mockResolvedValue([{ key: 'quad', name: 'Four-panel comparison', widgets: 4 }] as never)
    vi.mocked(pageTemplatesApi.addFrom).mockResolvedValue({ page_id: 421, widgets: 4 } as never)
    vi.mocked(reportsApi.deletePage).mockResolvedValue(undefined as never)
    renderReports()
    await screen.findByTestId('dash-card-1')
    fireEvent.click(screen.getByRole('button', { name: 'New dashboard' }))
    const dialog = await screen.findByRole('dialog', { name: 'Create a dashboard' })
    fireEvent.click(within(dialog).getByRole('radio', { name: /Template/ }))
    expect(await within(dialog).findByRole('radio', { name: /Four-panel comparison/ })).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(within(dialog).getByRole('button', { name: /^Create$/ }))
    await waitFor(() => expect(pageTemplatesApi.addFrom).toHaveBeenCalledWith(42, { builtin: 'quad' }))
    await waitFor(() => expect(reportsApi.deletePage).toHaveBeenCalledWith(42, 420))
  })

  it('With AI needs a dataset, then hands the goal to Suggest dashboards', async () => {
    renderReports()
    await screen.findByTestId('dash-card-1')
    fireEvent.click(screen.getByRole('button', { name: 'New dashboard' }))
    const dialog = await screen.findByRole('dialog', { name: 'Create a dashboard' })
    fireEvent.click(within(dialog).getByRole('radio', { name: /With AI/ }))
    const go = within(dialog).getByRole('button', { name: 'Suggest dashboards' })
    expect(go).toBeDisabled()
    fireEvent.change(within(dialog).getByLabelText('What should it show?'), { target: { value: 'churn by month' } })
    fireEvent.change(within(dialog).getByLabelText('Dataset'), { target: { value: '4' } })
    fireEvent.click(go)
    expect(await screen.findByTestId('suggest-dialog')).toHaveTextContent('Ledger|churn by month')
    expect(reportsApi.create).not.toHaveBeenCalled()
  })

  it('?new=1 (the command palette, Home) opens the dialog', async () => {
    renderReports({ at: '/reports?new=1' })
    expect(await screen.findByRole('dialog', { name: 'Create a dashboard' })).toBeInTheDocument()
  })

  it('a first run offers three ways to start instead of an empty grid', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([] as never)
    renderReports()
    expect(await screen.findByTestId('dash-firstrun')).toHaveTextContent('Build your first dashboard')
    fireEvent.click(screen.getByRole('button', { name: /Describe it to AI/ }))
    expect(within(await screen.findByRole('dialog')).getByRole('radio', { name: /With AI/ })).toHaveAttribute('aria-checked', 'true')
  })
})

describe('nextUntitledName', () => {
  it('never repeats a name already taken', () => {
    expect(nextUntitledName(['Untitled dashboard', 'Untitled dashboard 2'])).toBe('Untitled dashboard 3')
  })
})

describe('Reports accessibility', () => {
  it('has no structural accessibility violations', async () => {
    vi.mocked(workspaceApi.tree).mockResolvedValue({ roots: [node({ children: [leaf(1)] })], unfiled: [] } as never)
    const { container } = renderReports()
    await screen.findByRole('region', { name: 'Finance' })
    expect(await axeViolations(container)).toEqual([])
  })
})

/**
 * Behaviours the v1 page pinned that the redesign keeps, re-pinned against the
 * new layout (GATE C audit of the old Reports.test.tsx).
 */
const stylesheet = async () => {
  const fs = await import('node:fs')
  const path = await import('node:path')
  const url = await import('node:url')
  const here = path.dirname(url.fileURLToPath(import.meta.url))
  return fs.readFileSync(path.resolve(here, 'reports/dashboards.css'), 'utf8')
}
/** The body of the first rule whose selector list starts with `selector`. */
const rule = (css: string, selector: string) => {
  const i = css.indexOf(selector + ' {')
  expect(i, `no rule for ${selector}`).toBeGreaterThan(-1)
  return css.slice(i, css.indexOf('}', i) + 1)
}
const menuOf = async (id: number, name: string) => {
  fireEvent.click(within(card(id)).getByRole('button', { name: `More actions for ${name}` }))
  return screen.findByRole('menu')
}

describe('kept from v1: controls', () => {
  it('in select mode a click on a card ticks it and does not open it', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([report({ id: 1, name: 'A' }), report({ id: 2, name: 'B' })] as never)
    renderReports()
    await screen.findByTestId('dash-card-2')
    fireEvent.click(within(card(1)).getByRole('checkbox', { name: /A/ }))
    fireEvent.click(within(card(2)).getByRole('link', { name: 'B' }))
    expect(screen.getByTestId('where')).toHaveTextContent(/^\/reports$/)
    expect(within(card(2)).getByRole('checkbox')).toBeChecked()
  })

  it('offers exactly one Delete per dashboard', async () => {
    renderReports()
    await screen.findByTestId('dash-card-1')
    expect(within(card(1)).queryByRole('button', { name: /Delete/ })).not.toBeInTheDocument()
    const menu = await menuOf(1, 'Revenue')
    expect(within(menu).getAllByRole('menuitem', { name: 'Delete' })).toHaveLength(1)
  })

  it('a granted-but-editable dashboard keeps its design controls, not the author\'s', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([report({ is_mine: false, created_by: 4, my_capability: 'edit' })] as never)
    renderReports()
    await screen.findByTestId('dash-card-1')
    expect(within(card(1)).getByRole('checkbox')).toBeInTheDocument()
    expect(within(card(1)).queryByRole('button', { name: 'Share Revenue' })).not.toBeInTheDocument()
    const menu = await menuOf(1, 'Revenue')
    for (const name of ['Rename', 'Move to folder…', 'Delete']) expect(within(menu).getByRole('menuitem', { name })).toBeInTheDocument()
    for (const name of ['Publish', 'Share…']) expect(within(menu).queryByRole('menuitem', { name })).not.toBeInTheDocument()
  })

  it("someone else's dashboard offers no Publish either", async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([report({ is_mine: false, created_by: 4 })] as never)
    renderReports()
    await screen.findByTestId('dash-card-1')
    const menu = await menuOf(1, 'Revenue')
    expect(within(menu).queryByRole('menuitem', { name: /Publish/ })).not.toBeInTheDocument()
  })

  it('removing a grant calls the API and drops the row', async () => {
    vi.mocked(reportGrantsApi.list).mockResolvedValue([{ id: 5, user_id: 2, email: 'a@x.io', level: 'view' }] as never)
    vi.mocked(reportGrantsApi.remove).mockResolvedValue(undefined as never)
    renderReports()
    await screen.findByTestId('dash-card-1')
    fireEvent.click(within(card(1)).getByRole('button', { name: 'Share Revenue' }))
    const dialog = await screen.findByRole('dialog', { name: 'Share Revenue' })
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Remove access for a@x.io' }))
    await waitFor(() => expect(reportGrantsApi.remove).toHaveBeenCalledWith(1, 5))
    await waitFor(() => expect(within(dialog).queryByText('a@x.io')).not.toBeInTheDocument())
  })

  it('clicking a control inside the card does not open the dashboard', async () => {
    vi.mocked(reportGrantsApi.list).mockResolvedValue([] as never)
    renderReports()
    await screen.findByTestId('dash-card-1')
    fireEvent.click(within(card(1)).getByRole('button', { name: 'Share Revenue' }))
    expect(screen.getByTestId('where')).toHaveTextContent(/^\/reports$/)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('keeps every control reachable and named, not merely un-drawn', async () => {
    renderReports()
    await screen.findByTestId('dash-card-1')
    for (const name of ['Share Revenue', 'More actions for Revenue']) {
      const btn = within(card(1)).getByRole('button', { name })
      expect(btn).not.toHaveAttribute('aria-hidden')
      expect(btn).not.toBeDisabled()
      expect(btn).toHaveAttribute('title')
    }
  })
})

describe('kept from v1: stylesheet rules jsdom cannot see', () => {
  it('the whole card opens the dashboard: the title link is stretched over it', async () => {
    const css = await stylesheet()
    expect(rule(css, '.dsh-nm a::after')).toMatch(/inset:\s*0/)
    // Controls sit above the stretched link, so they stay clickable.
    expect(rule(css, '.dsh-ov')).toMatch(/z-index:\s*3/)
  })

  it('controls reveal on hover AND keyboard focus, and are never hidden on touch', async () => {
    const css = await stylesheet()
    expect(rule(css, '.dsh-ov')).toMatch(/opacity:\s*0/)
    expect(css).toMatch(/\.dsh-card:focus-within \.dsh-ov/)
    expect(css).toMatch(/@media \(hover: none\) \{\s*\.dsh-ov \{[^}]*opacity: 1/)
  })

  it('a long dashboard name is clamped to two lines, and the full name stays on the link', async () => {
    expect(rule(await stylesheet(), '.dsh-nm')).toMatch(/-webkit-line-clamp:\s*2/)
    const long = 'What stands out in Route planning extract output for the northern depots'
    vi.mocked(reportsApi.list).mockResolvedValue([report({ name: long })] as never)
    renderReports()
    expect(await screen.findByRole('link', { name: long })).toHaveAttribute('title', long)
    // The badges live in the footer, never beside the title.
    expect(within(screen.getByRole('heading', { name: long })).queryByText('Draft')).not.toBeInTheDocument()
  })

  it('a folder heading wraps rather than truncating', async () => {
    const name = rule(await stylesheet(), '.dsh-sh .fold .name')
    expect(name).not.toMatch(/text-overflow:\s*ellipsis/)
    expect(name).toMatch(/overflow-wrap:\s*anywhere/)
    expect(rule(await stylesheet(), '.dsh-sh .fold')).not.toMatch(/white-space:\s*nowrap/)
  })
})

describe('kept from v1: what a card says', () => {
  it('leaves a hand-written description alone, and never rewrites the one it was sent', async () => {
    const rows = [report({ id: 10, name: 'Ops', description: 'Weekly ops review, EMEA only' }),
      report({ id: 11, name: 'R', description: 'Suggested from the data' })]
    vi.mocked(reportsApi.list).mockResolvedValue(rows as never)
    renderReports()
    await screen.findByTestId('dash-card-11')
    expect(card(10)).toHaveTextContent('Weekly ops review, EMEA only')
    expect(card(10)).not.toHaveTextContent('AI suggestion')
    expect(rows[1].description).toBe('Suggested from the data')
  })

  it('says nothing about a dataset when a dashboard has none', async () => {
    renderReports()
    await screen.findByTestId('dash-card-1')
    expect(card(1)).not.toHaveTextContent(/No dataset/i)
    expect(card(1).querySelector('.dsh-ch')).toBeNull()
  })
})

describe('kept from v1: folders', () => {
  beforeEach(() => {
    vi.mocked(reportsApi.list).mockResolvedValue(Array.from({ length: 9 }, (_, i) => report({ id: i + 1, name: `Board ${i + 1}` })) as never)
    vi.mocked(workspaceApi.tree).mockResolvedValue({
      roots: [node({ id: 1, name: 'Finance', children: [leaf(1), leaf(2), node({ id: 2, parent_id: 1, name: 'Board', children: [leaf(3, 2)] })] }),
        node({ id: 3, name: 'Empty', children: [] })],
      unfiled: [],
    } as never)
  })

  it('each heading says how many dashboards it holds, subtree included; an empty one says zero', async () => {
    renderReports()
    const finance = await screen.findByRole('region', { name: 'Finance' })
    expect(within(finance).getAllByLabelText('3 dashboards')[0]).toHaveTextContent('3')
    expect(within(screen.getByRole('region', { name: 'Empty' })).getByLabelText('0 dashboards')).toHaveTextContent('0')
  })

  it('a collapsed heading expands again', async () => {
    renderReports()
    const finance = await screen.findByRole('region', { name: 'Finance' })
    const toggle = within(finance).getAllByRole('button', { name: /Finance/ })[0]
    fireEvent.click(toggle)
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(within(finance).getByTestId('dash-card-1')).toBeInTheDocument()
  })

  it('while searching there are no folder headings, so an emptied folder cannot promise cards', async () => {
    renderReports()
    await screen.findByRole('region', { name: 'Finance' })
    fireEvent.change(screen.getByRole('searchbox', { name: /Search dashboards/ }), { target: { value: 'Board 1' } })
    expect(screen.queryByRole('region', { name: 'Finance' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Empty' })).not.toBeInTheDocument()
    expect(screen.getByTestId('dash-card-1')).toBeInTheDocument()
  })

  it('a new folder shows up: the tree is read again after it is made', async () => {
    renderReports()
    await screen.findByRole('region', { name: 'Finance' })
    const before = vi.mocked(workspaceApi.tree).mock.calls.length
    fireEvent.click(screen.getAllByRole('button', { name: 'New folder' })[0])
    fireEvent.change(within(nav()).getByRole('textbox', { name: 'Folder name' }), { target: { value: 'Ops' } })
    fireEvent.click(within(nav()).getByRole('button', { name: 'Create folder' }))
    await waitFor(() => expect(vi.mocked(workspaceApi.tree).mock.calls.length).toBeGreaterThan(before))
  })

  it('a rename to the same name sends nothing', async () => {
    renderReports()
    await screen.findByTestId('dash-card-1')
    fireEvent.click(within(card(1)).getByRole('button', { name: 'More actions for Board 1' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Rename' }))
    await answerPrompt('Board 1')
    expect(reportsApi.update).not.toHaveBeenCalled()
  })

  it('a drop on "Not in a folder" moves the dashboard out to the top level', async () => {
    vi.mocked(workspaceApi.tree).mockResolvedValue({
      roots: [node({ id: 1, name: 'Finance', children: [leaf(1)] })], unfiled: [leaf(2, null, { id: 0 })],
    } as never)
    renderReports()
    const loose = await screen.findByRole('region', { name: 'Not in a folder' })
    fireEvent.dragStart(card(1))
    const head = loose.querySelector('.dsh-sh') as HTMLElement
    fireEvent.dragOver(head)
    fireEvent.drop(head)
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent('Move "Board 1" to Not in a folder?')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Move' }))
    await waitFor(() => expect(workspaceApi.update).toHaveBeenCalledWith(91, { parent_id: null }))
  })
})

/**
 * QA B7 (7-QA): a folder's count was reported to stay at 1 after its only
 * dashboard was deleted, until a reload. Folder placement is the server's, so
 * after a delete -- one or several -- the tree is read again.
 */
describe('a delete re-reads the folder tree (QA B7)', () => {
  it('after a single delete', async () => {
    renderReports()
    await screen.findByTestId('dash-card-1')
    const before = vi.mocked(workspaceApi.tree).mock.calls.length
    fireEvent.click(within(card(1)).getByRole('button', { name: 'More actions for Revenue' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(vi.mocked(workspaceApi.tree).mock.calls.length).toBeGreaterThan(before))
  })

  it('after a bulk delete', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([report({ id: 1, name: 'A' }), report({ id: 2, name: 'B' })] as never)
    renderReports()
    await screen.findByTestId('dash-card-2')
    const before = vi.mocked(workspaceApi.tree).mock.calls.length
    fireEvent.click(within(card(1)).getByRole('checkbox', { name: /A/ }))
    fireEvent.click(within(screen.getByRole('toolbar')).getByRole('button', { name: /Delete/ }))
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: /Delete/ }))
    await waitFor(() => expect(vi.mocked(workspaceApi.tree).mock.calls.length).toBeGreaterThan(before))
  })
})

describe('the search box while the list loads (QA2 B8)', () => {
  it('is there at once, keeps what is typed, and applies it when the list arrives', async () => {
    let resolve: (v: unknown) => void = () => {}
    vi.mocked(reportsApi.list).mockReturnValue(new Promise(r => { resolve = r }) as never)
    renderReports()
    // A slow list used to mean no box at all: a click there hit nothing.
    const box = await screen.findByRole('searchbox', { name: /Search dashboards/ })
    fireEvent.change(box, { target: { value: 'Board 3' } })
    await act(async () => { resolve(Array.from({ length: 9 }, (_, i) => report({ id: i + 1, name: `Board ${i}` }))) })
    expect(await screen.findByTestId('dash-card-4')).toBeInTheDocument()
    expect(screen.queryByTestId('dash-card-1')).toBeNull()
    expect(screen.getByRole('searchbox', { name: /Search dashboards/ })).toHaveValue('Board 3')
  })
})
