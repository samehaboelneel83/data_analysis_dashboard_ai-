/* Row rules for a CONNECTION — the ones Ask AI obeys.
 *
 * The platform has two row-security systems and they do not know about each
 * other. `row_security_rules` narrow a DATASET, and every admin screen was about
 * those. Ask AI reads the CONNECTION, which obeys `object_row_policies` — and
 * those had no page at all. Searching the whole frontend for "row-policies"
 * returned nothing.
 *
 * The consequence, proven against the real app: a student restricted to their own
 * row by a dataset rule opened Ask AI and pulled 5,000 other students' grades. The
 * control existed and worked; an admin simply could not reach it, and had no way
 * to know it was missing.
 *
 * So this page exists, and the dataset-rule screen now says out loud that its
 * rules stop at Ask AI.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import ConnectionRowPolicies from './ConnectionRowPolicies'
import { agentPoliciesApi, adminRolesApi as rolesApi, dataSourcesApi, metadataApi } from '../../services/api'

vi.mock('../../services/api', () => ({
  agentPoliciesApi: { list: vi.fn(), create: vi.fn(), remove: vi.fn() },
  dataSourcesApi: { list: vi.fn() },
  metadataApi: { review: vi.fn() },
  adminRolesApi: { list: vi.fn() },
}))

const SOURCES = [{ id: 18, name: 'Moodle LMS (Egyptian University)', type: 'sqlite' }]
const ROLES = [{ id: 35, name: 'Student', is_org_admin: false },
               { id: 33, name: 'Instructor', is_org_admin: true }]
const OBJECTS = { datasets: [{ id: 98, name: 'mdl_grade_grades' },
                             { id: 107, name: 'mdl_user' }] }
const POLICIES = [{ id: 1, source_object_id: 98, object_name: 'mdl_grade_grades',
                    role_id: 35, role_name: 'Student', predicate: 'userid = 13828' }]

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(dataSourcesApi.list).mockResolvedValue(SOURCES as never)
  vi.mocked(rolesApi.list).mockResolvedValue(ROLES as never)
  vi.mocked(metadataApi.review).mockResolvedValue(OBJECTS as never)
  vi.mocked(agentPoliciesApi.list).mockResolvedValue(POLICIES as never)
  vi.mocked(agentPoliciesApi.create).mockResolvedValue(POLICIES[0] as never)
  vi.mocked(agentPoliciesApi.remove).mockResolvedValue(undefined as never)
})

describe('ConnectionRowPolicies', () => {
  it('says plainly what these rules are for', async () => {
    render(<ConnectionRowPolicies />)
    // The warning is the point of the page: an admin arriving here has probably
    // just set a dataset rule and believes they are done.
    expect(await screen.findByText(/do not reach Ask AI/i)).toBeInTheDocument()
  })

  it('lists the rules already set on the chosen connection', async () => {
    render(<ConnectionRowPolicies />)
    expect(await screen.findByText('userid = 13828')).toBeInTheDocument()
    expect(screen.getAllByText('mdl_grade_grades').length).toBeGreaterThan(0)
    expect(screen.getByRole('cell', { name: 'Student' })).toBeInTheDocument()
  })

  it('offers the connection tables to choose from', async () => {
    render(<ConnectionRowPolicies />)
    await waitFor(() => expect(metadataApi.review).toHaveBeenCalledWith(18))
    expect(await screen.findByRole('option', { name: 'mdl_user' })).toBeInTheDocument()
  })

  it('creates a rule for the chosen table, role and predicate', async () => {
    render(<ConnectionRowPolicies />)
    await screen.findByText('userid = 13828')

    fireEvent.change(screen.getByLabelText(/table/i), { target: { value: '107' } })
    fireEvent.change(screen.getByLabelText(/role/i), { target: { value: '35' } })
    fireEvent.change(screen.getByLabelText(/rule/i), { target: { value: 'id = USERID()' } })
    fireEvent.click(screen.getByRole('button', { name: /add rule/i }))

    await waitFor(() => expect(agentPoliciesApi.create).toHaveBeenCalledWith({
      source_object_id: 107, role_id: 35, predicate: 'id = USERID()',
    }))
  })

  it('will not submit an empty rule', async () => {
    render(<ConnectionRowPolicies />)
    await screen.findByText('userid = 13828')
    fireEvent.click(screen.getByRole('button', { name: /add rule/i }))
    expect(agentPoliciesApi.create).not.toHaveBeenCalled()
  })

  it('shows the server’s reason when a predicate is rejected', async () => {
    vi.mocked(agentPoliciesApi.create).mockRejectedValue(
      { response: { data: { detail: 'could not parse the predicate' } } })
    render(<ConnectionRowPolicies />)
    await screen.findByText('userid = 13828')

    fireEvent.change(screen.getByLabelText(/table/i), { target: { value: '107' } })
    fireEvent.change(screen.getByLabelText(/role/i), { target: { value: '35' } })
    fireEvent.change(screen.getByLabelText(/rule/i), { target: { value: 'not sql' } })
    fireEvent.click(screen.getByRole('button', { name: /add rule/i }))

    expect(await screen.findByText(/could not parse the predicate/)).toBeInTheDocument()
  })

  it('removes a rule', async () => {
    render(<ConnectionRowPolicies />)
    await screen.findByText('userid = 13828')
    fireEvent.click(screen.getByRole('button', { name: /remove/i }))
    await waitFor(() => expect(agentPoliciesApi.remove).toHaveBeenCalledWith(1))
  })

  it('tells an admin with no connection rules that Ask AI is unrestricted', async () => {
    vi.mocked(agentPoliciesApi.list).mockResolvedValue([] as never)
    render(<ConnectionRowPolicies />)
    expect(await screen.findByText(/no rules|unrestricted|sees every row/i)).toBeInTheDocument()
  })
})
