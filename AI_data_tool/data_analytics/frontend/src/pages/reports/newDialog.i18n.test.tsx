import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DirectionProvider } from '../../contexts/DirectionContext'
import { NewDashboardDialog } from './dialogs'
import { nextUntitledName } from '../../lib/untitledName'
import { pageTemplatesApi } from '../../services/api'

/** QA T1 (7-QA): the New dashboard dialog spoke English in Arabic -- the
 *  "Untitled dashboard" placeholder and the server's template names. */

vi.mock('../../services/api', async orig => ({
  ...(await orig<Record<string, unknown>>()),
  pageTemplatesApi: { builtins: vi.fn() },
}))

afterEach(() => localStorage.removeItem('datalytics.language'))

describe('New dashboard dialog in Arabic (QA T1)', () => {
  it('names the built-in templates in Arabic by their key, and keeps an unknown one as sent', async () => {
    localStorage.setItem('datalytics.language', 'ar')
    vi.mocked(pageTemplatesApi.builtins).mockResolvedValue([
      { key: 'quad', name: 'Four-panel comparison', widgets: 4 },
      { key: 'custom-x', name: 'Custom layout', widgets: 2 }] as never)
    render(<DirectionProvider><NewDashboardDialog datasets={[]} folders={[]} initialMode="tpl" initialFolder={null}
      placeholderName="لوحة بلا عنوان" busy={false} onClose={() => {}} onCreate={() => {}} /></DirectionProvider>)
    expect(await screen.findByRole('radio', { name: /مقارنة من أربع لوحات/ })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Custom layout/ })).toBeInTheDocument()
    expect(screen.queryByText('Four-panel comparison')).toBeNull()
  })

  it('the untitled name is in the reader’s language, numbered the same way', () => {
    expect(nextUntitledName([], 'لوحة بلا عنوان')).toBe('لوحة بلا عنوان')
    expect(nextUntitledName(['لوحة بلا عنوان'], 'لوحة بلا عنوان')).toBe('لوحة بلا عنوان 2')
    expect(nextUntitledName(['Untitled dashboard'])).toBe('Untitled dashboard 2')
  })
})
