import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import OutlierDetailsDialog from '../report/OutlierDetailsDialog'
import ExplainDialog from '../report/ExplainDialog'
import { outlierApi, explainApi } from '../../services/api'

/**
 * The modals, checked for the three things nine of them shipped without.
 *
 * A keyboard user could enter any of these and not get out: Tab walked past
 * the dialog into the page behind it while the dialog still covered the
 * screen, and Escape did nothing.
 *
 * These run against two real dialogs rather than every one, because they all
 * now share `useModalDialog` -- the hook's own suite covers the mechanics, and
 * these prove the wiring is real in components that ship.
 */

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  outlierApi: { details: vi.fn() },
  explainApi: { explain: vi.fn() },
}))

const outliers = {
  column: 'amount', method: 'iqr', lower: 0, upper: 100,
  count: 2, total: 20,
  rows: [{ row: 'r20', value: 250 }],
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(outlierApi.details).mockResolvedValue(outliers as never)
  vi.mocked(explainApi.explain).mockResolvedValue({
    column: 'amount', factors: [], relationship: null,
  } as never)
})

describe('every modal is escapable', () => {
  it('closes the outlier dialog on Escape', async () => {
    const onClose = vi.fn()
    render(<OutlierDetailsDialog datasetId={5} column="amount" onClose={onClose} />)
    await screen.findByRole('dialog')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('closes the explain dialog on Escape', async () => {
    const onClose = vi.fn()
    render(<ExplainDialog datasetId={5} column="amount" onClose={onClose} />)
    await screen.findByRole('dialog')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
})

describe('every modal announces itself as modal', () => {
  it('marks the panel, not the backdrop, as the dialog', async () => {
    // The scrim behind a dialog is not the dialog. Putting role="dialog" on the
    // backdrop makes the accessible name cover the whole viewport and puts the
    // page's own content inside the dialog's boundary.
    render(<OutlierDetailsDialog datasetId={5} column="amount" onClose={vi.fn()} />)
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAccessibleName(/outliers in amount/i)

    // The backdrop is the parent, and it must NOT also claim the role.
    expect(dialog.parentElement).not.toHaveAttribute('role', 'dialog')
  })
})

describe('focus is trapped and returned', () => {
  it('moves focus into the dialog on open', async () => {
    render(<OutlierDetailsDialog datasetId={5} column="amount" onClose={vi.fn()} />)
    const dialog = await screen.findByRole('dialog')
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))
  })

  it('keeps Tab inside the dialog', async () => {
    // THE property. Without the trap, Tab from the last control lands on the
    // page behind the scrim, which the user cannot see.
    render(
      <div>
        <button>outside</button>
        <OutlierDetailsDialog datasetId={5} column="amount" onClose={vi.fn()} />
      </div>,
    )
    const dialog = await screen.findByRole('dialog')
    const outside = screen.getByRole('button', { name: 'outside' })

    for (let i = 0; i < 12; i++) fireEvent.keyDown(window, { key: 'Tab' })
    expect(document.activeElement).not.toBe(outside)
    expect(dialog.contains(document.activeElement)).toBe(true)
  })

  it('returns focus to the opener when it closes', async () => {
    render(<button>opener</button>)
    const opener = screen.getByRole('button', { name: 'opener' })
    opener.focus()

    const { unmount } = render(
      <OutlierDetailsDialog datasetId={5} column="amount" onClose={vi.fn()} />)
    await screen.findByRole('dialog')
    unmount()

    // Otherwise focus falls back to <body> and a keyboard user loses their
    // place in the page entirely.
    expect(document.activeElement).toBe(opener)
  })
})
