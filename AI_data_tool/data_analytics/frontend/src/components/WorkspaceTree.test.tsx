import { renderWithProviders as render, answerPrompt, screen, waitFor, fireEvent } from '../test/renderWithProviders'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import WorkspaceTree from './WorkspaceTree'
import { reportsApi, workspaceApi } from '../services/api'
import toast from 'react-hot-toast'

/**
 * The navigation menu. Three behaviours carry real risk:
 *
 *   - An unfiled report must still be listed. A report that exists but cannot
 *     be opened from the menu is worse than the flat list this replaces.
 *   - The delete prompt must say that nothing is destroyed. The server
 *     re-parents a folder's contents, and a user who has been burned by another
 *     tool will not believe that unless it is written on the button.
 *   - Pages route to their own page index, which is the only reason pages
 *     appear in the tree at all.
 */

vi.mock('../services/api', () => ({
  reportsApi: {
    create: vi.fn(),
  },
  workspaceApi: {
    tree: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    roles: vi.fn(),
    setRoles: vi.fn(),
    grants: vi.fn(),
    setGrants: vi.fn(),
    shareOptions: vi.fn(),
  },
}))

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

const navigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

const folder = (over = {}) => ({
  id: 1, parent_id: null, node_type: 'folder' as const, name: 'Sales',
  report_id: null, position: 0, can_manage: true, is_mine: true, role_ids: [],
  pages: [], children: [], ...over,
})

const report = (over = {}) => ({
  id: 2, parent_id: 1, node_type: 'report' as const, name: 'Q3 review',
  report_id: 42, position: 0, can_manage: true, is_mine: true, role_ids: [],
  pages: [], children: [], ...over,
})

/** Folder actions live in ONE menu now, picked by their words rather than by
 *  a guessable glyph. */
async function openFolderMenu(name: string) {
  fireEvent.click(await screen.findByLabelText(`Actions for ${name}`))
}
const item = (name: RegExp) => screen.getByRole('menuitem', { name })

function show(tree: any, props: Record<string, unknown> = {}) {
  ;(workspaceApi.tree as any).mockResolvedValue(tree)
  return render(
    <MemoryRouter>
      <WorkspaceTree {...props} />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})
afterEach(() => vi.restoreAllMocks())

describe('WorkspaceTree', () => {
  it('lists folders from the tree', async () => {
    show({ roots: [folder()], unfiled: [] })
    expect(await screen.findByText('Sales')).toBeTruthy()
  })

  it('keeps an unfiled report reachable', async () => {
    show({ roots: [], unfiled: [report({ id: 0, parent_id: null, name: 'Orphan' })] })
    expect(await screen.findByText('Orphan')).toBeTruthy()
    expect(screen.getByText('Unfiled')).toBeTruthy()
  })

  it('opens a report when its row is clicked', async () => {
    show({ roots: [report({ parent_id: null })], unfiled: [] })
    fireEvent.click(await screen.findByText('Q3 review'))
    expect(navigate).toHaveBeenCalledWith('/reports/42')
  })

  it('routes a page click to that page index', async () => {
    show({
      roots: [report({
        parent_id: null,
        pages: [
          { id: 7, name: 'Overview', position: 0 },
          { id: 8, name: 'Detail', position: 1 },
        ],
      })],
      unfiled: [],
    })
    // The CARET expands; the label opens the report. If the whole row toggled,
    // a report could never be opened; if it navigated, its pages could never be
    // reached. Both controls have to exist, so both are exercised.
    fireEvent.click(await screen.findByLabelText('Expand Q3 review'))
    fireEvent.click(await screen.findByText('Detail'))
    expect(navigate).toHaveBeenCalledWith('/reports/42?page=1')
  })

  it('opens the report when the label is clicked, even with pages', async () => {
    show({
      roots: [report({ parent_id: null, pages: [{ id: 7, name: 'Overview', position: 0 }] })],
      unfiled: [],
    })
    fireEvent.click(await screen.findByText('Q3 review'))
    expect(navigate).toHaveBeenCalledWith('/reports/42')
  })

  // These now read the real ConfirmDialog rather than a stubbed window.confirm.
  // The copy is the point: users who have been burned by other tools do not
  // believe a folder delete keeps its contents unless it is written down.
  it('says that deleting a folder keeps its contents', async () => {
    show({ roots: [folder()], unfiled: [] })
    await openFolderMenu('Sales')
    fireEvent.click(item(/Delete folder/i))

    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent(/moves up a level/i)
    expect(dialog).toHaveTextContent(/no dashboards are deleted/i)

    // Declining must not call the API at all -- merely rendering the dialog
    // would prove nothing about whether the action was actually guarded.
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(workspaceApi.delete).not.toHaveBeenCalled()
  })

  it('says that unfiling a report keeps the report', async () => {
    show({ roots: [report({ parent_id: null })], unfiled: [] })
    fireEvent.click(await screen.findByLabelText('Remove Q3 review from the tree'))
    expect(await screen.findByRole('alertdialog'))
      .toHaveTextContent(/dashboard itself is kept/i)
  })

  it('deletes when the prompt is accepted', async () => {
    ;(workspaceApi.delete as any).mockResolvedValue(undefined)
    show({ roots: [folder()], unfiled: [] })
    await openFolderMenu('Sales')
    fireEvent.click(item(/Delete folder/i))
    fireEvent.click(await screen.findByRole('button', { name: /delete folder/i }))
    await waitFor(() => expect(workspaceApi.delete).toHaveBeenCalledWith(1))
  })

  it('creates a folder from the prompt', async () => {
    ;(workspaceApi.create as any).mockResolvedValue(folder())
    show({ roots: [], unfiled: [] })
    fireEvent.click(await screen.findByLabelText('New folder'))
    await answerPrompt('New folder')
    await waitFor(() =>
      expect(workspaceApi.create).toHaveBeenCalledWith({
        node_type: 'folder', name: 'New folder',
      }),
    )
  })

  it('does not create a folder when the prompt is cancelled', async () => {
    show({ roots: [], unfiled: [] })
    fireEvent.click(await screen.findByLabelText('New folder'))
    await answerPrompt(null)
    await waitFor(() => expect(workspaceApi.create).not.toHaveBeenCalled())
  })

  it('files an unfiled report into the tree', async () => {
    ;(workspaceApi.create as any).mockResolvedValue(report())
    show({ roots: [], unfiled: [report({ id: 0, parent_id: null })] })
    fireEvent.click(await screen.findByLabelText('File Q3 review in the tree'))
    await waitFor(() =>
      expect(workspaceApi.create).toHaveBeenCalledWith({
        node_type: 'report', report_id: 42, parent_id: null,
      }),
    )
  })

  it('remembers which folders were open across mounts', async () => {
    const { unmount } = show({ roots: [folder({ children: [report()] })], unfiled: [] })
    fireEvent.click(await screen.findByText('Sales'))
    await screen.findByText('Q3 review')
    unmount()

    show({ roots: [folder({ children: [report()] })], unfiled: [] })
    // Still expanded: the child is visible without clicking again.
    expect(await screen.findByText('Q3 review')).toBeTruthy()
  })

  describe('drag to move', () => {
    it('moves a node into the folder it is dropped on', async () => {
      ;(workspaceApi.update as any).mockResolvedValue({})
      show({ roots: [folder(), folder({ id: 9, name: 'Archive' })], unfiled: [] })

      const dragged = (await screen.findByText('Sales')).parentElement!
      const target = (await screen.findByText('Archive')).parentElement!
      fireEvent.dragStart(dragged)
      fireEvent.dragOver(target)
      fireEvent.drop(target)

      await waitFor(() =>
        expect(workspaceApi.update).toHaveBeenCalledWith(1, { parent_id: 9 }))
    })

    it('moves a node back to the root when dropped on the header', async () => {
      // Without this a node dragged into a folder could never come out again.
      ;(workspaceApi.update as any).mockResolvedValue({})
      show({ roots: [folder({ children: [report()] })], unfiled: [] })

      fireEvent.click(await screen.findByText('Sales'))
      const child = (await screen.findByText('Q3 review')).parentElement!
      fireEvent.dragStart(child)
      const header = await screen.findByText('Workspaces')
      fireEvent.dragOver(header.parentElement!)
      fireEvent.drop(header.parentElement!)

      await waitFor(() =>
        expect(workspaceApi.update).toHaveBeenCalledWith(2, { parent_id: null }))
    })

    it('surfaces the server refusal instead of leaving the tree wrong', async () => {
      // The cycle guard lives on the server; the UI must not pretend the move
      // worked when it was rejected.
      const toast = (await import('react-hot-toast')).default
      ;(workspaceApi.update as any).mockRejectedValue(new Error('400'))
      show({ roots: [folder(), folder({ id: 9, name: 'Archive' })], unfiled: [] })

      const dragged = (await screen.findByText('Sales')).parentElement!
      const target = (await screen.findByText('Archive')).parentElement!
      fireEvent.dragStart(dragged)
      fireEvent.drop(target)

      await waitFor(() => expect(toast.error).toHaveBeenCalled())
    })

    it('does not move a node onto itself', async () => {
      show({ roots: [folder()], unfiled: [] })
      const row = (await screen.findByText('Sales')).parentElement!
      fireEvent.dragStart(row)
      fireEvent.drop(row)
      await waitFor(() => expect(workspaceApi.update).not.toHaveBeenCalled())
    })
  })

  describe('controls follow the server\'s can_manage flag', () => {
    it('hides rename, restrict and delete on a node the viewer cannot manage', async () => {
      show({ roots: [folder({ can_manage: false })], unfiled: [] })
      await screen.findByText('Sales')

      // One menu carries every action now, so its absence is the whole test.
      expect(screen.queryByLabelText('Actions for Sales')).toBeNull()
      expect(screen.queryByLabelText('Remove Sales from the tree')).toBeNull()
    })

    it('still offers New folder to everyone', async () => {
      // Creating stays open: gating it would mean nobody but an admin can
      // organise their own reports.
      show({ roots: [folder({ can_manage: false })], unfiled: [] })
      expect(await screen.findByLabelText('New folder')).toBeTruthy()
    })

    it('shows the controls when the viewer may manage the node', async () => {
      show({ roots: [folder()], unfiled: [] })
      await openFolderMenu('Sales')
      expect(item(/Rename/i)).toBeTruthy()
      expect(item(/Who can see it/i)).toBeTruthy()
    })
  })

  describe('folder visibility', () => {
    it('wears no lock when the folder is visible to everyone', async () => {
      // An unrestricted folder is the ordinary case and spends its whole width
      // on its NAME -- the badge is for the exception.
      show({ roots: [folder({ role_ids: [] })], unfiled: [] })
      await screen.findByText('Sales')
      expect(screen.queryByLabelText(/is restricted to/i)).toBeNull()
    })

    it('shows a closed lock when the folder is restricted', async () => {
      // The badge carries the state: otherwise the only way to know a folder
      // is restricted is to open the dialog, which is how restrictions get
      // lost. It is a MARKER -- the action itself lives in the menu.
      show({ roots: [folder({ role_ids: [3, 4] })], unfiled: [] })
      const badge = await screen.findByLabelText('Sales is restricted to 2 role(s)')
      expect(badge.getAttribute('title')).toMatch(/restricted to 2 role/i)
    })

    it('sends the parsed role ids', async () => {
      ;(workspaceApi.setRoles as any).mockResolvedValue([3, 4])
      show({ roots: [folder()], unfiled: [] })
      await openFolderMenu('Sales')
      fireEvent.click(item(/Who can see it/i))
      await answerPrompt('3, 4')
      await waitFor(() => expect(workspaceApi.setRoles).toHaveBeenCalledWith(1, [3, 4]))
    })

    it('an empty answer clears the restriction', async () => {
      // Visible-to-everyone is the default, so returning to it must not require
      // knowing that "no roles" is how you spell it -- the prompt says so.
      ;(workspaceApi.setRoles as any).mockResolvedValue([])
      show({ roots: [folder({ role_ids: [3] })], unfiled: [] })
      await openFolderMenu('Sales')
      fireEvent.click(item(/Who can see it/i))
      // Submittable while empty on purpose -- that is how the restriction is cleared.
      await answerPrompt('')
      await waitFor(() => expect(workspaceApi.setRoles).toHaveBeenCalledWith(1, []))
    })

    it('cancelling changes nothing', async () => {
      show({ roots: [folder()], unfiled: [] })
      await openFolderMenu('Sales')
      fireEvent.click(item(/Who can see it/i))
      await answerPrompt(null)
      await waitFor(() => expect(workspaceApi.setRoles).not.toHaveBeenCalled())
    })
  })

  describe('my workspaces vs shared with me', () => {
    it('separates mine, genuinely shared, and the organisation\'s own', async () => {
      show({
        roots: [
          folder({ id: 1, name: 'Mine', is_mine: true }),
          folder({ id: 2, name: 'Given', is_mine: false, can_manage: false,
                   shared_with_me: true }),
          folder({ id: 3, name: 'Theirs', is_mine: false, can_manage: false }),
        ],
        unfiled: [],
      })
      expect(await screen.findByText('My workspaces')).toBeTruthy()
      expect(screen.getByText('Shared with me')).toBeTruthy()
      expect(screen.getByText('Organisation')).toBeTruthy()
      // The claim under test: a folder nobody handed me is NOT under
      // "Shared with me" -- it sits under the organisation's own heading.
      const shared = screen.getByText('Shared with me')
      const org = screen.getByText('Organisation')
      expect(shared.compareDocumentPosition(screen.getByText('Given')))
        .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
      expect(org.compareDocumentPosition(screen.getByText('Theirs')))
        .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    })

    it('never files an admin\'s view of a colleague\'s folder as shared', async () => {
      // An admin sees every folder in the org by OFFICE, not by gift. Calling
      // that "Shared with me" claims a privilege nobody granted -- and with a
      // single group there is no heading at all.
      show({
        roots: [folder({ id: 1, name: 'Theirs', is_mine: false, can_manage: true })],
        unfiled: [],
      })
      await screen.findByText('Theirs')
      expect(screen.queryByText('Shared with me')).toBeNull()
      expect(screen.queryByText('My workspaces')).toBeNull()
    })

    it('shows no headings when everything belongs to the viewer', async () => {
      // A new user with one folder should not read a heading above it.
      show({ roots: [folder({ is_mine: true })], unfiled: [] })
      await screen.findByText('Sales')
      expect(screen.queryByText('My workspaces')).toBeNull()
      expect(screen.queryByText('Shared with me')).toBeNull()
    })

    it('labels a lone shared workspace — a newcomer sees nothing else', async () => {
      // A member on their first day, in a clean org: one folder, shared with
      // them. "Shared with me" is a privilege claim worth making even when it
      // is the only group there is.
      show({
        roots: [folder({ id: 2, name: 'Team HQ', is_mine: false, can_manage: false,
                         shared_with_me: true })],
        unfiled: [],
      })
      expect(await screen.findByText('Shared with me')).toBeTruthy()
      expect(screen.queryByText('My workspaces')).toBeNull()
      expect(screen.queryByText('Organisation')).toBeNull()
    })

    it('shows no headings when the viewer owns none of them', async () => {
      // An admin owning nothing must not read a heading over the whole
      // organisation's tree.
      show({
        roots: [folder({ is_mine: false }), folder({ id: 2, name: 'Other', is_mine: false })],
        unfiled: [],
      })
      await screen.findByText('Sales')
      expect(screen.queryByText('Shared with me')).toBeNull()
      expect(screen.queryByText('My workspaces')).toBeNull()
    })

    it('groups on ownership, not on whether the viewer may manage it', async () => {
      // The distinction the flag exists for: an admin can manage a member's
      // folder, but it is not theirs and must not appear under My workspaces.
      show({
        roots: [
          folder({ id: 1, name: 'Mine', is_mine: true, can_manage: true }),
          folder({ id: 2, name: 'Managed', is_mine: false, can_manage: true }),
        ],
        unfiled: [],
      })
      expect(await screen.findByText('My workspaces')).toBeTruthy()
      // "Managed" is manageable but neither owned nor given, so it belongs to
      // the organisation's group, not to a claim of sharing.
      const org = screen.getByText('Organisation')
      expect(screen.queryByText('Shared with me')).toBeNull()
      expect(org.compareDocumentPosition(screen.getByText('Managed')))
        .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    })

    it('unfiled reports land in their own group, not a third bucket', async () => {
      // An unfiled report is still somebody's work or somebody's grant --
      // filing it must not be the price of appearing in the right section.
      // A report whose author named ME carries shared_with_me from the server,
      // exactly like a shared folder does.
      show({
        roots: [folder({ id: 1, name: 'Mine', is_mine: true })],
        unfiled: [report({ id: 0, parent_id: null, is_mine: false,
                           shared_with_me: true, name: 'Granted report' })],
      })
      expect(await screen.findByText('My workspaces')).toBeTruthy()
      const granted = screen.getByText('Shared with me')
      expect(granted.compareDocumentPosition(screen.getByText('Granted report')))
        .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
      expect(screen.queryByText('Unfiled')).toBeNull()
    })

    it('marks a granted view-only report, filed and unfiled alike', async () => {
      show({
        roots: [folder({ id: 1, name: 'Mine', is_mine: true }),
                folder({ id: 3, name: 'Theirs', is_mine: false, children: [
                  report({ id: 4, parent_id: 3, is_mine: false, my_capability: 'view' }),
                ] })],
        unfiled: [report({ id: 0, parent_id: null, is_mine: false, name: 'Read me',
                           my_capability: 'view' })],
      })
      await screen.findByText('Organisation')
      fireEvent.click(screen.getByText('Theirs'))
      expect(screen.getAllByLabelText('View only').length).toBe(2)
    })

    it('a manager can publish a workspace, and the control names the action', async () => {
      ;(workspaceApi.update as any).mockResolvedValue(folder({ published: true }))
      show({ roots: [folder({ id: 1, name: 'Team', published: false })], unfiled: [] })
      await openFolderMenu('Team')
      fireEvent.click(item(/Publish to everyone/i))
      await waitFor(() =>
        expect(workspaceApi.update).toHaveBeenCalledWith(1, { published: true }))
    })

    it('a published workspace is badged, and its menu offers the way back', async () => {
      show({ roots: [folder({ id: 1, name: 'Team', published: true })], unfiled: [] })
      expect(await screen.findByLabelText('Team is published to everyone')).toBeTruthy()
      await openFolderMenu('Team')
      expect(item(/Make private again/i)).toBeTruthy()
      expect(screen.queryByRole('menuitem', { name: /Publish to everyone/i })).toBeNull()
    })

    it('does not mark an editable granted report as view-only', async () => {
      // The marker means "you cannot design this", not "this is not yours" --
      // a granted report with edit capability must carry no eye.
      show({
        roots: [folder({ id: 1, name: 'Mine', is_mine: true })],
        unfiled: [report({ id: 0, parent_id: null, is_mine: false,
                           my_capability: 'edit' })],
      })
      await screen.findByText('Organisation')
      expect(screen.queryByLabelText('View only')).toBeNull()
    })
  })
  describe('putting things inside a workspace', () => {
    it('creates a subfolder INSIDE the folder, not at the root', async () => {
      ;(workspaceApi.create as any).mockResolvedValue(folder({ id: 9 }))
      show({ roots: [folder({ id: 1, name: 'Sales', can_manage: true })], unfiled: [] })
      await openFolderMenu('Sales')
      fireEvent.click(await screen.findByRole('menuitem', { name: /New subfolder/i }))
      await answerPrompt('Q3')
      await waitFor(() => expect(workspaceApi.create).toHaveBeenCalledWith({
        node_type: 'folder', name: 'Q3', parent_id: 1,
      }))
    })

    it('creates a dashboard inside the folder and opens it for design', async () => {
      ;(reportsApi.create as any).mockResolvedValue({ id: 77, name: 'Pipeline' })
      ;(workspaceApi.create as any).mockResolvedValue(report({ id: 5, report_id: 77 }))
      show({ roots: [folder({ id: 1, name: 'Sales', can_manage: true })], unfiled: [] })
      await openFolderMenu('Sales')
      fireEvent.click(await screen.findByRole('menuitem', { name: /New dashboard/i }))
      await answerPrompt('Pipeline')
      await waitFor(() => expect(reportsApi.create).toHaveBeenCalledWith({ name: 'Pipeline' }))
      await waitFor(() => expect(workspaceApi.create).toHaveBeenCalledWith({
        node_type: 'report', report_id: 77, parent_id: 1,
      }))
      // Creating a dashboard means going on to design it.
      await waitFor(() => expect(navigate).toHaveBeenCalledWith('/reports/77'))
    })

    it('says so honestly when the dashboard is made but cannot be filed', async () => {
      // The dashboard EXISTS at this point; reporting "could not create" would
      // be a lie about a thing the user can go and find.
      ;(reportsApi.create as any).mockResolvedValue({ id: 77, name: 'Pipeline' })
      ;(workspaceApi.create as any).mockRejectedValue(new Error('nope'))
      show({ roots: [folder({ id: 1, name: 'Sales', can_manage: true })], unfiled: [] })
      await openFolderMenu('Sales')
      fireEvent.click(await screen.findByRole('menuitem', { name: /New dashboard/i }))
      await answerPrompt('Pipeline')
      await waitFor(() => expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('was created but could not be filed')))
      await waitFor(() => expect(navigate).toHaveBeenCalledWith('/reports/77'))
    })

    it('does nothing when the name prompt is cancelled', async () => {
      show({ roots: [folder({ id: 1, name: 'Sales', can_manage: true })], unfiled: [] })
      await openFolderMenu('Sales')
      fireEvent.click(await screen.findByRole('menuitem', { name: /New dashboard/i }))
      await answerPrompt(null)
      await waitFor(() => expect(reportsApi.create).not.toHaveBeenCalled())
      expect(workspaceApi.create).not.toHaveBeenCalled()
    })

    it('offers no action menu on a folder the viewer may not manage', async () => {
      show({ roots: [folder({ id: 1, name: 'Theirs', can_manage: false, is_mine: false })], unfiled: [] })
      await screen.findByText('Theirs')
      expect(screen.queryByLabelText('Actions for Theirs')).toBeNull()
    })

    it('offers no folder menu on a dashboard — only folders hold things', async () => {
      show({ roots: [report({ id: 2, parent_id: null, name: 'Q3 review' })], unfiled: [] })
      await screen.findByText('Q3 review')
      expect(screen.queryByLabelText('Actions for Q3 review')).toBeNull()
    })

    it('still creates a TOP-LEVEL folder from the header, with no parent', async () => {
      // Pinned because addFolder now takes a parent: passing it straight to
      // onClick would send the click event as one.
      ;(workspaceApi.create as any).mockResolvedValue(folder())
      show({ roots: [], unfiled: [] })
      fireEvent.click(await screen.findByLabelText('New folder'))
      await answerPrompt('Top')
      await waitFor(() => expect(workspaceApi.create).toHaveBeenCalledWith({
        node_type: 'folder', name: 'Top',
      }))
    })
  })

  describe('workspace sharing', () => {
    it('a manageable folder offers Share, and it opens the share dialog', async () => {
      ;(workspaceApi.grants as any).mockResolvedValue([])
      ;(workspaceApi.shareOptions as any).mockResolvedValue({ roles: [], org_units: [] })
      show({ roots: [folder({ id: 1, name: 'Sales', can_manage: true })], unfiled: [] })
      await openFolderMenu('Sales')
      fireEvent.click(item(/Share with people/i))
      // The dialog is live: it loads the folder's grants and the share options.
      expect(await screen.findByRole('dialog', { name: 'Share Sales' })).toBeTruthy()
      await waitFor(() => expect(workspaceApi.grants).toHaveBeenCalledWith(1))
      expect(workspaceApi.shareOptions).toHaveBeenCalled()
    })

    it('offers no Share control where the viewer may not manage', async () => {
      show({ roots: [folder({ id: 1, name: 'Theirs', can_manage: false, is_mine: false })], unfiled: [] })
      await screen.findByText('Theirs')
      expect(screen.queryByLabelText('Actions for Theirs')).toBeNull()
    })

    it('a member who owns nothing still gets the heading over a real share', async () => {
      // The first-day case for exactly the person a workspace was just shared
      // with: org folders render plain, the heading sits over the share alone,
      // and no empty "My workspaces" heading appears.
      show({
        roots: [folder({ id: 1, name: 'Widget gallery', is_mine: false, can_manage: false }),
                folder({ id: 2, name: 'Team HQ', is_mine: false, can_manage: false,
                         shared_with_me: true })],
        unfiled: [],
      })
      const heading = await screen.findByText('Shared with me')
      expect(screen.queryByText('My workspaces')).toBeNull()
      expect(heading.compareDocumentPosition(screen.getByText('Team HQ')))
        .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
      // The org's own folder keeps its own heading rather than borrowing this
      // one's claim of privilege.
      const org = screen.getByText('Organisation')
      expect(org.compareDocumentPosition(screen.getByText('Widget gallery')))
        .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    })

    it('badges a folder that reaches the viewer through a share', async () => {
      // The badge answers "why can I see this?" where the folder is listed.
      show({
        roots: [folder({ id: 1, name: 'Mine', is_mine: true }),
                folder({ id: 2, name: 'Team HQ', is_mine: false, can_manage: false,
                         shared_with_me: true })],
        unfiled: [],
      })
      await screen.findByText('Team HQ')
      expect(screen.getByLabelText('Shared with you')).toBeTruthy()
      // ...and lands under the Shared with me heading.
      const heading = screen.getByText('Shared with me')
      expect(heading.compareDocumentPosition(screen.getByText('Team HQ')))
        .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    })
  })
})


/**
 * Three load outcomes, three different pictures.
 *
 * This used to have two. A failed /workspace/tree was caught and turned into
 * `{roots: [], unfiled: []}`, so an outage and an empty workspace rendered
 * identically -- and the empty one offers no retry, because there is nothing
 * wrong with it. On the rail that was merely unhelpful; on the Dashboards page
 * the tree is the filter for the list beside it, so "the folders are gone" and
 * "we could not fetch the folders" have to be told apart.
 */
describe('the tree tells its three load states apart', () => {
  it('shows skeleton rows while the tree is loading', () => {
    ;(workspaceApi.tree as any).mockReturnValue(new Promise(() => {}))
    const { container } = render(
      <MemoryRouter>
        <WorkspaceTree />
      </MemoryRouter>,
    )
    expect(container.querySelectorAll('.dl-tree__skeleton').length).toBeGreaterThan(0)
  })

  it('renders quiet text -- not an alert -- when the tree is genuinely empty', async () => {
    show({ roots: [], unfiled: [] })
    expect(await screen.findByText(/No folders yet/i)).toBeTruthy()
    // The distinction this whole describe exists for.
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('renders a retryable alert when the tree fails to load', async () => {
    ;(workspaceApi.tree as any).mockRejectedValue(new Error('boom'))
    render(
      <MemoryRouter>
        <WorkspaceTree />
      </MemoryRouter>,
    )
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(/Could not load your workspaces/i)
    expect(screen.queryByText(/No folders yet/i)).toBeNull()
  })

  it('Try again re-fetches and renders what comes back', async () => {
    ;(workspaceApi.tree as any).mockRejectedValueOnce(new Error('boom'))
    ;(workspaceApi.tree as any).mockResolvedValueOnce({ roots: [folder()], unfiled: [] })
    render(
      <MemoryRouter>
        <WorkspaceTree />
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: /Try again/i }))
    expect(await screen.findByText('Sales')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})

/**
 * Folder selection, which is what the tree is FOR on the Dashboards page.
 *
 * The click that selects is the same click that opens -- the row has toggled
 * on click since the tree was written, and a folder whose dashboards stay
 * hidden while it filters the list beside it would read as broken.
 */
describe('selecting a folder', () => {
  const nested = () => folder({
    children: [
      folder({ id: 3, parent_id: 1, name: 'EMEA',
        children: [report({ id: 4, parent_id: 3, report_id: 99, name: 'EMEA Q3' })] }),
      report(),
    ],
  })

  it('reports the folder and every report id beneath it, at any depth', async () => {
    const onSelectFolder = vi.fn()
    show({ roots: [nested()], unfiled: [] }, { onSelectFolder })

    fireEvent.click(await screen.findByText('Sales'))

    expect(onSelectFolder).toHaveBeenCalledTimes(1)
    const sel = onSelectFolder.mock.calls[0][0]
    expect(sel.id).toBe(1)
    expect(sel.name).toBe('Sales')
    // Sorted because the walk order is an implementation detail; the SET is
    // the contract, and a subtree walk that stopped at depth 1 would miss 99.
    expect([...sel.reportIds].sort((a: number, b: number) => a - b)).toEqual([42, 99])
  })

  it('clears the selection when the same folder is clicked again', async () => {
    const onSelectFolder = vi.fn()
    show({ roots: [nested()], unfiled: [] }, { onSelectFolder, selectedFolderId: 1 })
    await screen.findByText('Sales')
    // The load itself re-emits the resolved selection; this test is about
    // the CLICK, so only what the click does is measured.
    onSelectFolder.mockClear()

    fireEvent.click(screen.getByText('Sales'))

    expect(onSelectFolder).toHaveBeenCalledWith(null)
  })

  it('does not close a folder that was already open when it is selected', async () => {
    // Open folders persist in localStorage, so on a normal visit the folder
    // you want to filter by is usually ALREADY open. Toggling unconditionally
    // meant the click that filtered the list also collapsed the folder it was
    // filtering by. Every other test starts from a cleared store, which is why
    // this went unnoticed.
    localStorage.setItem('workspace.open-folders', JSON.stringify([1]))
    const onSelectFolder = vi.fn()
    show({ roots: [nested()], unfiled: [] }, { onSelectFolder })

    fireEvent.click(await screen.findByText('Sales'))

    expect(onSelectFolder).toHaveBeenCalled()
    expect(screen.getByText('EMEA')).toBeTruthy()
  })

  it('does not clear the selection before the tree has loaded', async () => {
    // `tree` starts as an empty placeholder. An unguarded resync fires against
    // it on mount, finds nothing, and drops a filter the user still has -- so
    // the page would clear its own chip a frame after rendering it.
    const onSelectFolder = vi.fn()
    ;(workspaceApi.tree as any).mockReturnValue(new Promise(() => {}))
    render(
      <MemoryRouter>
        <WorkspaceTree selectedFolderId={1} onSelectFolder={onSelectFolder} />
      </MemoryRouter>,
    )
    expect(onSelectFolder).not.toHaveBeenCalled()
  })

  it('keeps the selection when the tree fails to load', async () => {
    // "We could not ask" is not "the folder is gone". Clearing here would make
    // a network blip silently widen the list the user was looking at.
    const onSelectFolder = vi.fn()
    ;(workspaceApi.tree as any).mockRejectedValue(new Error('boom'))
    render(
      <MemoryRouter>
        <WorkspaceTree selectedFolderId={1} onSelectFolder={onSelectFolder} />
      </MemoryRouter>,
    )
    await screen.findByRole('alert')
    expect(onSelectFolder).not.toHaveBeenCalled()
  })

  it('re-emits the selection when the tree changes underneath it', async () => {
    // reportIds is a snapshot. The tree refreshes itself after every action it
    // owns, so a dashboard moved INTO the selected folder has to reach the
    // page too -- otherwise the filter silently describes a tree that is no
    // longer on screen.
    const onSelectFolder = vi.fn()
    ;(workspaceApi.tree as any).mockResolvedValue({ roots: [nested()], unfiled: [] })
    render(
      <MemoryRouter>
        <WorkspaceTree selectedFolderId={1} onSelectFolder={onSelectFolder} />
      </MemoryRouter>,
    )
    await screen.findByText('Sales')
    onSelectFolder.mockClear()

    // A rename is the cheapest action that forces a refresh.
    ;(workspaceApi.update as any).mockResolvedValue({})
    ;(workspaceApi.tree as any).mockResolvedValue({
      roots: [folder({
        name: 'Sales EMEA',
        children: [report(), report({ id: 5, report_id: 77, name: 'New one' })],
      })],
      unfiled: [],
    })
    await openFolderMenu('Sales')
    fireEvent.click(item(/Rename/i))
    await answerPrompt('Sales EMEA')

    await waitFor(() => expect(onSelectFolder).toHaveBeenCalled())
    const sel = onSelectFolder.mock.calls[onSelectFolder.mock.calls.length - 1][0]
    expect(sel.name).toBe('Sales EMEA')
    expect([...sel.reportIds].sort((a: number, b: number) => a - b)).toEqual([42, 77])
  })

  it('clears the selection when the selected folder is deleted', async () => {
    const onSelectFolder = vi.fn()
    ;(workspaceApi.tree as any).mockResolvedValue({ roots: [nested()], unfiled: [] })
    render(
      <MemoryRouter>
        <WorkspaceTree selectedFolderId={1} onSelectFolder={onSelectFolder} />
      </MemoryRouter>,
    )
    await screen.findByText('Sales')
    onSelectFolder.mockClear()

    ;(workspaceApi.delete as any).mockResolvedValue({})
    ;(workspaceApi.tree as any).mockResolvedValue({ roots: [], unfiled: [] })
    await openFolderMenu('Sales')
    fireEvent.click(item(/Delete folder/i))
    fireEvent.click(await screen.findByRole('button', { name: /delete folder/i }))

    // A chip naming a folder that no longer exists is worse than no chip.
    await waitFor(() => expect(onSelectFolder).toHaveBeenCalledWith(null))
  })

  it('still opens the folder it selects', async () => {
    // The pre-existing gesture. Selection rides on it rather than replacing
    // it, so every test above that opens a folder by clicking its name keeps
    // working -- and the folder's dashboards appear, as they always have.
    show({ roots: [nested()], unfiled: [] }, { onSelectFolder: vi.fn() })
    fireEvent.click(await screen.findByText('Sales'))
    expect(await screen.findByText('EMEA')).toBeTruthy()
  })
})
