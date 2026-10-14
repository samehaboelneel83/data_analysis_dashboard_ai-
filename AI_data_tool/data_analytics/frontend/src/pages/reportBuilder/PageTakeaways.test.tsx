import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import PageTakeaways from './PageTakeaways'
import { discoveryApi } from '../../services/api'

vi.mock('../../services/api', () => ({ discoveryApi: { takeaways: vi.fn() } }))
beforeEach(() => vi.clearAllMocks())

const line = (over: Record<string, unknown>) => ({
  widget_id: 1, title: 'Total', widget_type: 'kpi', family: 'basics', section: 'headline', claim: 'observation',
  sentence: 'Total amount: 840.', sentence_i18n: null, sampled: false, ...over,
})

describe('PageTakeaways', () => {
  it('lists each chart\'s sentence under its section, and says no AI wrote it', async () => {
    vi.mocked(discoveryApi.takeaways).mockResolvedValue({
      report_id: 3, page_id: 9, page: 'Overview', widgets_read: 3, nothing_to_say: 0, left_out: 2, source: 'deterministic',
      takeaways: [line({}), line({ widget_id: 2, title: 'By group', section: 'comparison', sentence: 'A leads with 500.', sampled: true })],
    } as never)
    render(<PageTakeaways reportId={3} pageId={9} />)
    expect(await screen.findByText('Total amount: 840.')).toBeInTheDocument()
    expect(screen.getByText('Headline numbers')).toBeInTheDocument()
    expect(screen.getByText('Comparisons')).toBeInTheDocument()
    expect(screen.getByText(/from a sample/)).toBeInTheDocument()
    expect(screen.getByText('2 more charts are not listed.')).toBeInTheDocument()
    expect(screen.getByText(/No AI wrote this/)).toBeInTheDocument()
    expect(discoveryApi.takeaways).toHaveBeenCalledWith(3, 9)
  })

  it('says so when the page has nothing to report, and offers to try again when it fails', async () => {
    vi.mocked(discoveryApi.takeaways).mockResolvedValueOnce({ takeaways: [], left_out: 0 } as never)
    const { unmount } = render(<PageTakeaways reportId={3} pageId={9} />)
    expect(await screen.findByText('Nothing on this page has a number to report yet.')).toBeInTheDocument()
    unmount()
    vi.mocked(discoveryApi.takeaways).mockRejectedValueOnce(new Error('down'))
      .mockResolvedValueOnce({ takeaways: [line({})], left_out: 0 } as never)
    render(<PageTakeaways reportId={3} pageId={9} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(screen.getByText('Total amount: 840.')).toBeInTheDocument())
  })
})
