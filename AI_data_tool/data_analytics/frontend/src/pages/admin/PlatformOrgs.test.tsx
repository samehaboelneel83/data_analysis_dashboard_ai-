import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import PlatformOrgs from './PlatformOrgs'
import { DirectionProvider } from '../../contexts/DirectionContext'

vi.mock('../../services/api', () => {
  const noQuota = { max_queries_per_day: null, max_agent_asks_per_day: null, max_storage_mb: null, max_concurrent_asks: null,
    max_ai_tokens_per_day: null, max_ai_tokens_per_month: null }
  const noUsage = { queries_today: 0, agent_asks_today: 0, storage_bytes: 0, ai_tokens_today: 0, ai_tokens_month: 0 }
  return {
  platformApi: {
    listOrgs: vi.fn().mockResolvedValue([
      { id: 1, name: 'Parent Co', user_count: 3, parent_org_id: null, mcp_enabled: true, quota: noQuota, usage: noUsage },
      { id: 2, name: 'Child Co', user_count: 1, parent_org_id: null, mcp_enabled: false,
        quota: { ...noQuota, max_ai_tokens_per_day: 50000 },
        usage: { queries_today: 4, agent_asks_today: 1, storage_bytes: 2 * 1024 * 1024,
                 ai_tokens_today: 12345, ai_tokens_month: 67890 } },
    ]),
    createOrg: vi.fn().mockResolvedValue({ org_id: 9, name: 'Acme', admin_user_id: 5, admin_email: 'a@acme.com' }),
    setParent: vi.fn().mockResolvedValue({ org_id: 2, parent_org_id: 1 }),
    setMcp: vi.fn().mockResolvedValue({ org_id: 2, mcp_enabled: true }),
    aiUsage: vi.fn().mockResolvedValue({
      org_id: 2, days: 30, since: '2026-08-28', total_tokens: 67890, remaining: 0, binding_limit: 'ai_tokens_per_day',
      by_day: [], by_feature: [{ feature: 'ask', tokens: 60000, calls: 40, refused: 3 },
                               { feature: 'metadata', tokens: 7890, calls: 12, refused: 0 }],
      by_user: [{ user_id: 7, email: 'ana@child.co', tokens: 60000, calls: 40, refused: 3 },
                { user_id: null, email: null, tokens: 7890, calls: 12, refused: 0 }],
    }),
    setQuota: vi.fn().mockResolvedValue({ org_id: 2, max_queries_per_day: 100, max_agent_asks_per_day: null, max_storage_mb: null, max_concurrent_asks: null }),
  },
  }
})

import { platformApi } from '../../services/api'

describe('PlatformOrgs', () => {
  it('lists orgs and provisions a new one', async () => {
    render(<PlatformOrgs />)
    expect(await screen.findByText(/3 users/)).toBeInTheDocument()   // the Parent Co row

    fireEvent.change(screen.getByLabelText('Organization name'), { target: { value: 'Acme' } })
    fireEvent.change(screen.getByLabelText('Admin email'), { target: { value: 'a@acme.com' } })
    fireEvent.change(screen.getByLabelText('Admin password'), { target: { value: 'pw' } })
    expect(screen.getByLabelText('Admin password')).toHaveAttribute('autoComplete', 'new-password')
    expect(screen.getByLabelText('Admin email')).toHaveAttribute('autoComplete', 'off')
    fireEvent.click(screen.getByRole('button', { name: 'Create organization' }))

    await waitFor(() => expect(platformApi.createOrg).toHaveBeenCalledWith(
      { name: 'Acme', admin_email: 'a@acme.com', admin_password: 'pw' }))
  })

  it('sets a parent from the per-org dropdown', async () => {
    render(<PlatformOrgs />)
    fireEvent.change(await screen.findByLabelText('Parent of Child Co'), { target: { value: '1' } })
    await waitFor(() => expect(platformApi.setParent).toHaveBeenCalledWith(2, 1))
  })

  it('activates MCP for an org via its toggle', async () => {
    render(<PlatformOrgs />)
    // Child Co starts disabled; ticking the box activates it
    fireEvent.click(await screen.findByLabelText('MCP access for Child Co'))
    await waitFor(() => expect(platformApi.setMcp).toHaveBeenCalledWith(2, true))
  })

  it('shows usage vs quota for each org', async () => {
    render(<PlatformOrgs />)
    expect(await screen.findByText(/Queries today: 4 \/ unlimited/)).toBeInTheDocument()
    expect(screen.getByText(/Storage: 2\.0 MB \/ unlimited/)).toBeInTheDocument()
  })

  it('edits and saves a quota for an org', async () => {
    render(<PlatformOrgs />)
    const editButtons = await screen.findAllByRole('button', { name: 'Edit quota' })
    fireEvent.click(editButtons[1])   // Child Co's row

    fireEvent.change(screen.getByLabelText('Max queries per day for Child Co'), { target: { value: '100' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save quota' }))

    await waitFor(() => expect(platformApi.setQuota).toHaveBeenCalledWith(2, {
      max_queries_per_day: 100, max_agent_asks_per_day: null, max_storage_mb: null, max_concurrent_asks: null,
      max_ai_tokens_per_day: 50000, max_ai_tokens_per_month: null,
    }))
  })

  it('sets an AI token budget (E11)', async () => {
    render(<PlatformOrgs />)
    fireEvent.click((await screen.findAllByRole('button', { name: 'Edit quota' }))[0])   // Parent Co
    fireEvent.change(screen.getByLabelText('Max AI tokens per month for Parent Co'), { target: { value: '2000000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save quota' }))
    await waitFor(() => expect(platformApi.setQuota).toHaveBeenLastCalledWith(1, expect.objectContaining({
      max_ai_tokens_per_day: null, max_ai_tokens_per_month: 2000000 })))
  })

  it('shows AI tokens against the budget, and where they went (E11)', async () => {
    render(<PlatformOrgs />)
    expect(await screen.findByText(/AI tokens today: 12,345 \/ 50,000/)).toBeInTheDocument()
    expect(screen.getByText(/AI tokens this month: 67,890 \/ unlimited/)).toBeInTheDocument()

    const toggle = screen.getAllByRole('button', { name: 'AI usage' })[1]
    fireEvent.click(toggle)
    await waitFor(() => expect(platformApi.aiUsage).toHaveBeenCalledWith(2))
    const panel = await screen.findByTestId('ai-usage')
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(panel).toHaveTextContent('Budget used up today')
    const byFeature = screen.getByRole('table', { name: 'AI tokens by feature for Child Co' })
    expect(byFeature).toHaveTextContent('Ask AI questions')
    expect(byFeature).toHaveTextContent('60,000')
    expect(byFeature).toHaveTextContent('Describing connections')
    const byPerson = screen.getByRole('table', { name: 'AI tokens by person for Child Co' })
    expect(byPerson).toHaveTextContent('ana@child.co')
    expect(byPerson).toHaveTextContent('Scheduled work')

    fireEvent.click(toggle)
    expect(screen.queryByTestId('ai-usage')).not.toBeInTheDocument()
  })
})

describe('PlatformOrgs loading, empty, and error states', () => {
  it('shows an empty state instead of a bare blank list when there are no organizations', async () => {
    vi.mocked(platformApi.listOrgs).mockResolvedValueOnce([])
    render(<PlatformOrgs />)
    await waitFor(() => expect(screen.getByText(/no organizations yet/i)).toBeInTheDocument())
  })

  it('shows a retry-capable error banner, not a silent empty list, when the load fails', async () => {
    vi.mocked(platformApi.listOrgs).mockRejectedValueOnce({ response: { data: { detail: 'Not authorized' } } })
    render(<PlatformOrgs />)

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByText('Not authorized')).toBeInTheDocument()
    // The load failure must not also render the empty state underneath the error.
    expect(screen.queryByText(/no organizations yet/i)).toBeNull()
  })

  it('retries the load when "Try again" is clicked, and clears the error once it succeeds', async () => {
    vi.mocked(platformApi.listOrgs)
      .mockRejectedValueOnce({ response: { data: { detail: 'Not authorized' } } })
      .mockResolvedValueOnce([])
    render(<PlatformOrgs />)

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))

    await waitFor(() => expect(screen.getByText(/no organizations yet/i)).toBeInTheDocument())
    expect(screen.queryByRole('alert')).toBeNull()
  })
})

describe('PlatformOrgs in Arabic (8-i18n)', () => {
  afterEach(() => localStorage.removeItem('datalytics.language'))

  it('reads in Arabic: plural users, quotas, names isolated', async () => {
    localStorage.setItem('datalytics.language', 'ar')
    render(<DirectionProvider><PlatformOrgs /></DirectionProvider>)
    expect(await screen.findByText(/^3 مستخدمين · الأم:/)).toBeInTheDocument()
    expect(screen.getByText(/^مستخدم واحد · الأم:/)).toBeInTheDocument()
    expect(screen.getByText('Parent Co', { selector: '.dl-rows__title bdi' })).toBeInTheDocument()
    expect(screen.getAllByText('استعلامات اليوم: 4 / بلا حد').length).toBe(1)
    expect(screen.getByRole('button', { name: 'إنشاء المؤسسة' })).toBeInTheDocument()
    expect(screen.getByLabelText('المؤسسة الأم لـ «⁨Child Co⁩»')).toBeInTheDocument()
    expect(screen.queryByText(/Queries today/)).toBeNull()
  })
})
