import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { ConfirmProvider } from '../../components/ui/ConfirmDialog'
import { DirectionProvider } from '../../contexts/DirectionContext'
import { translate } from '../../i18n'
import AdminRoles from './AdminRoles'
import AdminUsers from './AdminUsers'
import AdminRowSecurityRules from './AdminRowSecurityRules'
import AdminColumnSecurityRules from './AdminColumnSecurityRules'
import ConnectionRowPolicies from './ConnectionRowPolicies'
import AdminExportPolicy from './AdminExportPolicy'

/**
 * 8-i18n: the security admin pages (Users, Roles, Row and Column security,
 * Connection rules, Export policy) speak Arabic. Names from the data stay as
 * they are, isolated (U+2068 … U+2069) inside «» in plain strings.
 */

const { dataset } = vi.hoisted(() => ({
  dataset: {
    id: 1, name: 'Orders', row_count: 10, col_count: 2, file_size: 0,
    created_at: '', updated_at: '', calculated_columns: [], measures: [],
    column_meta: {}, column_formats: {}, mode: 'import',
    columns: [
      { id: 1, name: 'owner_email', dtype: 'text', missing_pct: 0, stats: {}, semantic_type: 'email' },
      { id: 2, name: 'salary', dtype: 'numeric', missing_pct: 0, stats: {}, semantic_type: null },
    ],
  },
}))

vi.mock('../../services/api', () => ({
  adminRolesApi: { list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
  adminUsersApi: { list: vi.fn(), bulkCreate: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
  adminRlsRulesApi: {
    list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn(),
    autoGenerate: vi.fn().mockResolvedValue({ proposals: [] }),
    preflight: vi.fn().mockResolvedValue({ columns: [], denied: [] }),
  },
  columnSecurityApi: { list: vi.fn(), create: vi.fn(), remove: vi.fn() },
  datasetsApi: { list: vi.fn() },
  exportPolicyApi: { get: vi.fn(), setAll: vi.fn(), setGranular: vi.fn() },
  agentPoliciesApi: { list: vi.fn(), create: vi.fn(), remove: vi.fn() },
  dataSourcesApi: { list: vi.fn() },
  metadataApi: { review: vi.fn() },
}))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

import {
  adminRolesApi, adminUsersApi, adminRlsRulesApi, columnSecurityApi, datasetsApi,
  exportPolicyApi, agentPoliciesApi, dataSourcesApi, metadataApi,
} from '../../services/api'

const iso = (s: string) => `⁨${s}⁩`
const ar = (k: Parameters<typeof translate>[1], v?: Record<string, string | number>) => translate('ar', k, v)
const renderAr = (ui: ReactNode) => {
  localStorage.setItem('datalytics.language', 'ar')
  return render(<DirectionProvider><ConfirmProvider>{ui}</ConfirmProvider></DirectionProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(adminRolesApi.list).mockResolvedValue([{ id: 1, name: 'Analyst', is_org_admin: true }] as never)
  vi.mocked(adminUsersApi.list).mockResolvedValue([
    { id: 5, email: 'sara@acme.com', is_active: false, role: { id: 1, name: 'Analyst', is_org_admin: true } },
  ] as never)
  vi.mocked(datasetsApi.list).mockResolvedValue([dataset] as never)
  vi.mocked(adminRlsRulesApi.list).mockResolvedValue([
    { id: 9, role_id: 1, dataset_id: 1, filter_expr: "region == 'North'", auto_generated: true },
  ] as never)
  vi.mocked(columnSecurityApi.list).mockResolvedValue([
    { id: 3, role_id: 1, dataset_id: 1, denied_columns: ['salary'] },
  ] as never)
  vi.mocked(exportPolicyApi.get).mockResolvedValue({ export_policy: false, has_security_rules: true } as never)
  vi.mocked(dataSourcesApi.list).mockResolvedValue([{ id: 18, name: 'Moodle', type: 'sqlite' }] as never)
  vi.mocked(metadataApi.review).mockResolvedValue({ datasets: [{ id: 98, name: 'mdl_user' }] } as never)
  vi.mocked(agentPoliciesApi.list).mockResolvedValue([] as never)
})
afterEach(() => { try { localStorage.removeItem('datalytics.language') } catch { /* jsdom */ } })

describe('the security admin pages, in Arabic (8-i18n)', () => {
  it('Roles: the badge, the dialog and the delete question', async () => {
    renderAr(<AdminRoles />)
    expect(await screen.findByText(ar('pg.adminSecurity.roles.orgAdmin'))).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: ar('admin.newRole') }))
    const dlg = screen.getByRole('dialog', { name: 'دور جديد' })
    expect(within(dlg).getByText('اسم الدور *')).toBeInTheDocument()
    expect(within(dlg).getByPlaceholderText('مدير إقليمي')).toBeInTheDocument()
    expect(dlg.textContent).not.toMatch(/Role Name|Org admin|Create|Cancel/)
    fireEvent.click(within(dlg).getByRole('button', { name: ar('common.cancel') }))

    fireEvent.click(screen.getByRole('button', { name: ar('admin.delete') }))
    const ask = await screen.findByRole('alertdialog')
    expect(ask).toHaveAttribute('aria-label', `حذف الدور «${iso('Analyst')}»؟`)
    expect(within(ask).getByText('يفقد المستخدمون الذين يحملون هذا الدور صلاحياته.')).toBeInTheDocument()
  })

  it('Users: the row, the delete question and the bulk-import report with Arabic plurals', async () => {
    vi.mocked(adminUsersApi.bulkCreate).mockResolvedValue({
      created_count: 1, created: ['a@x.com'], errors: [{ row: 2, email: 'bad', error: 'invalid email' }],
    } as never)
    renderAr(<AdminUsers />)
    expect(await screen.findByText('غير نشط')).toBeInTheDocument()
    expect(screen.getByText('(مسؤول)')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: ar('admin.delete') }))
    const ask = await screen.findByRole('alertdialog')
    expect(ask).toHaveAttribute('aria-label', `حذف المستخدم «${iso('sara@acme.com')}»؟`)
    expect(within(ask).getByText('لا يمكن التراجع عن ذلك.')).toBeInTheDocument()
    fireEvent.click(within(ask).getByRole('button', { name: ar('common.cancel') }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())

    fireEvent.click(screen.getByRole('button', { name: ar('admin.bulkImport') }))
    const dlg = screen.getByRole('dialog', { name: 'استيراد المستخدمين جماعيًا' })
    fireEvent.change(within(dlg).getByLabelText('ملف CSV للمستخدمين'),
      { target: { value: 'a@x.com,pw,Analyst\nbad,pw,Analyst' } })
    fireEvent.click(within(dlg).getByRole('button', { name: 'استيراد' }))
    expect(await within(dlg).findByText('أُنشئ مستخدم واحد')).toBeInTheDocument()
    expect(within(dlg).getByText('تُخطّي صف واحد:')).toBeInTheDocument()
    expect(within(dlg).getByText(`الصف ${iso('2')} (${iso('bad')}): ${iso('invalid email')}`)).toBeInTheDocument()
    expect(dlg.textContent).not.toMatch(/One user per line|Created|skipped|Import/)
  })

  it('Row security: the note, the row, its menu and the rule dialog', async () => {
    renderAr(<AdminRowSecurityRules />)
    expect(await screen.findByText(ar('pg.adminSecurity.rls.askNoteStrong'))).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'قواعد الاتصال (اسأل الذكاء الاصطناعي)' })).toBeInTheDocument()
    expect(await screen.findByText('على')).toBeInTheDocument()
    expect(screen.getByText('تلقائية')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: `إجراءات أخرى للقاعدة: الدور «${iso('Analyst')}» على «${iso('Orders')}»` }))
      .toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: ar('admin.newRule') }))
    const dlg = screen.getByRole('dialog', { name: 'قاعدة أمان صفوف جديدة' })
    const match = within(dlg).getByLabelText('المطابقة') as HTMLSelectElement
    expect(Array.from(match.options).map(o => o.textContent)).toContain('البريد الإلكتروني للمستخدم الحالي')
    // The generated expression is code, and stays as it is.
    expect(within(dlg).getByText('owner_email == USEREMAIL()')).toBeInTheDocument()
    expect(dlg.textContent).not.toMatch(/Quick setup|Filter Expression|Rows where|Use this expression/)
  })

  it('Column security: the row and the delete question name the columns, isolated', async () => {
    renderAr(<AdminColumnSecurityRules />)
    expect(await screen.findByText(`يخفي: ${iso('salary')}`)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: ar('admin.delete') }))
    const ask = await screen.findByRole('alertdialog')
    expect(ask).toHaveAttribute('aria-label', 'حذف قاعدة أمان الأعمدة هذه؟')
    expect(within(ask).getByText(
      `الدور «${iso('Analyst')}» على مجموعة البيانات «${iso('Orders')}». تصبح الأعمدة المخفية (${iso('salary')}) مرئية لهذا الدور.`,
    )).toBeInTheDocument()
  })

  it('Connection rules: the heading, the warning and the form', async () => {
    renderAr(<ConnectionRowPolicies />)
    expect(await screen.findByRole('heading', { name: 'قواعد الاتصال: ما يراه «اسأل الذكاء الاصطناعي»' })).toBeInTheDocument()
    expect(screen.getByText(ar('pg.adminSecurity.crp.warnStrong'))).toBeInTheDocument()
    expect(await screen.findByText(ar('pg.adminSecurity.crp.noRules'))).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'إضافة القاعدة' }))
    expect(await screen.findByText('اختر جدولًا ودورًا، واكتب القاعدة.')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/Add a rule|Connection rules|choose/)
  })

  it('Export policy: the checkboxes name the dataset in Arabic', async () => {
    renderAr(<AdminExportPolicy />)
    expect(await screen.findByRole('checkbox', { name: `إيقاف كل عمليات التصدير لـ«${iso('Orders')}»` })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: `إيقاف تصدير ${iso('csv')} لـ«${iso('Orders')}»` })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: `الإيقاف التلقائي عند وجود بيانات خاصة لـ«${iso('Orders')}»` })).toBeInTheDocument()
  })
})
