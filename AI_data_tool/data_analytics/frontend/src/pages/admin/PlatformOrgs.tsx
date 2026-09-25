import { useEffect, useState } from 'react'
import { inlineFieldStyle } from '../../components/ui/fieldStyle'
import { useT } from '../../i18n'
import { Building2 } from 'lucide-react'
import { platformApi } from '../../services/api'
import type { OrgQuota, PlatformOrg } from '../../services/api'
import toast from 'react-hot-toast'
import EmptyState from '../../components/ui/EmptyState'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

const fmtLimit = (n: number | null) => (n == null ? 'unlimited' : n.toLocaleString())
const fmtMb = (bytes: number) => (bytes / (1024 * 1024)).toFixed(1)

export default function PlatformOrgs() {
  const t = useT()
  const [orgs, setOrgs] = useState<PlatformOrg[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [name, setName] = useState('')
  const [adminEmail, setAdminEmail] = useState('')
  const [adminPassword, setAdminPassword] = useState('')
  const [creating, setCreating] = useState(false)

  // A load failure gets the persistent inline banner below, not a toast: this is
  // the page's whole reason for existing, not a side-effect of one action, and a
  // toast that has already faded leaves the author staring at an empty list with
  // no explanation. Reused after mutations too (create/setParent/setMcp/saveQuota
  // all call load() to refresh), so a refresh failure surfaces the same way.
  const load = () => {
    setLoadError(null)
    return platformApi.listOrgs().then(setOrgs).catch(setLoadError)
  }

  useEffect(() => { load().finally(() => setLoading(false)) }, [])

  const createOrg = async () => {
    if (!name.trim() || !adminEmail.trim() || !adminPassword) { toast.error('Name, admin email and password are required'); return }
    setCreating(true)
    try {
      await platformApi.createOrg({ name: name.trim(), admin_email: adminEmail.trim(), admin_password: adminPassword })
      toast.success(`Created "${name.trim()}"`)
      setName(''); setAdminEmail(''); setAdminPassword('')
      await load()
    } catch (e: any) { toast.error(e?.response?.data?.detail ?? 'Create failed') }
    finally { setCreating(false) }
  }

  const setParent = async (org: PlatformOrg, parentOrgId: number | null) => {
    try {
      await platformApi.setParent(org.id, parentOrgId)
      await load()
    } catch (e: any) { toast.error(e?.response?.data?.detail ?? 'Could not set parent') }
  }

  const setMcp = async (org: PlatformOrg, enabled: boolean) => {
    try {
      await platformApi.setMcp(org.id, enabled)
      await load()
      toast.success(`MCP ${enabled ? 'activated' : 'deactivated'} for ${org.name}`)
    } catch (e: any) { toast.error(e?.response?.data?.detail ?? 'Could not change MCP access') }
  }

  const [editingQuotaId, setEditingQuotaId] = useState<number | null>(null)
  const [quotaDraft, setQuotaDraft] = useState<Record<string, string>>({})

  const startEditQuota = (org: PlatformOrg) => {
    setEditingQuotaId(org.id)
    setQuotaDraft({
      max_queries_per_day: org.quota.max_queries_per_day?.toString() ?? '',
      max_agent_asks_per_day: org.quota.max_agent_asks_per_day?.toString() ?? '',
      max_storage_mb: org.quota.max_storage_mb?.toString() ?? '',
      max_concurrent_asks: org.quota.max_concurrent_asks?.toString() ?? '',
    })
  }

  const saveQuota = async (org: PlatformOrg) => {
    const toNullableInt = (v: string) => (v.trim() === '' ? null : Number(v))
    const body: OrgQuota = {
      max_queries_per_day: toNullableInt(quotaDraft.max_queries_per_day ?? ''),
      max_agent_asks_per_day: toNullableInt(quotaDraft.max_agent_asks_per_day ?? ''),
      max_storage_mb: toNullableInt(quotaDraft.max_storage_mb ?? ''),
      max_concurrent_asks: toNullableInt(quotaDraft.max_concurrent_asks ?? ''),
    }
    try {
      await platformApi.setQuota(org.id, body)
      toast.success(`Quota updated for ${org.name}`)
      setEditingQuotaId(null)
      await load()
    } catch (e: any) { toast.error(e?.response?.data?.detail ?? 'Could not update quota') }
  }

  const nameOf = (id: number | null) => (id == null ? '—' : orgs.find(o => o.id === id)?.name ?? `#${id}`)

  const inp = { style: inlineFieldStyle }

  return (
    <div>
      <h1 className="dl-page-title" style={{ marginBottom: 6 }}>{t('nav.organizations')}</h1>
      <div className="dl-page-head__sub" style={{ marginBottom: 20, maxWidth: 720 }}>
        Platform super-admin: create organizations and arrange the hierarchy. Setting a parent is structural —
        it does not grant a parent's users access to a child's data.
      </div>

      <div className="card" style={{ padding: 16, marginBottom: 20 }}>
        <div className="dl-rows__title" style={{ marginBottom: 10 }}>New organization</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input aria-label="Organization name" placeholder="Organization name" value={name} onChange={e => setName(e.target.value)} {...inp} />
          <input aria-label="Admin email" placeholder="Admin email" value={adminEmail}
            onChange={e => setAdminEmail(e.target.value)} autoComplete="off" name="new-org-admin-email" {...inp} />
          <input aria-label="Admin password" type="password" placeholder="Admin password" value={adminPassword}
            onChange={e => setAdminPassword(e.target.value)} autoComplete="new-password" name="new-org-admin-password" {...inp} />
          <button className="btn btn-primary btn-sm" onClick={createOrg} disabled={creating}>
            {creating ? 'Creating…' : 'Create organization'}
          </button>
        </div>
      </div>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="organizations" error={loadError} onRetry={() => { setLoading(true); load().finally(() => setLoading(false)) }} />
      )}

      {!loading && loadError == null && orgs.length === 0 && (
        <EmptyState icon={Building2} title="No organizations yet"
          description="Create the first organization above to get started." />
      )}

      <div className="dl-rows">
        {orgs.map(o => (
          <div key={o.id} className="dl-rows__row dl-rows__row--stack">
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
              <div className="dl-rows__main">
                <div className="dl-rows__title">{o.name}</div>
                <div className="dl-rows__meta">
                  {o.user_count} user{o.user_count === 1 ? '' : 's'} · parent: {nameOf(o.parent_org_id)}
                </div>
              </div>
              <label style={{ fontSize: 11, color: o.mcp_enabled ? 'var(--text)' : 'var(--muted)', display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
                title="Activate or deactivate MCP / API-key access for this organization">
                <input type="checkbox" aria-label={`MCP access for ${o.name}`} checked={o.mcp_enabled}
                  onChange={e => setMcp(o, e.target.checked)} />
                MCP {o.mcp_enabled ? 'on' : 'off'}
              </label>
              <label style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                Parent
                <select aria-label={`Parent of ${o.name}`} value={o.parent_org_id ?? ''}
                  onChange={e => setParent(o, e.target.value ? Number(e.target.value) : null)} {...inp}>
                  <option value="">— none (top level) —</option>
                  {orgs.filter(x => x.id !== o.id).map(x => <option key={x.id} value={x.id}>{x.name}</option>)}
                </select>
              </label>
            </div>

            {/* Task E2: usage-vs-quota column */}
            <div style={{ fontSize: 11.5, color: 'var(--muted)', borderTop: '1px dashed var(--border)', paddingTop: 8,
              display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap', fontVariantNumeric: 'tabular-nums' }}>
              <span>Queries today: {o.usage.queries_today} / {fmtLimit(o.quota.max_queries_per_day)}</span>
              <span>Agent asks today: {o.usage.agent_asks_today} / {fmtLimit(o.quota.max_agent_asks_per_day)}</span>
              <span>Storage: {fmtMb(o.usage.storage_bytes)} MB / {fmtLimit(o.quota.max_storage_mb)}</span>
              <span>Concurrent asks: {fmtLimit(o.quota.max_concurrent_asks)}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => startEditQuota(o)} style={{ marginInlineStart: 'auto' }}>Edit quota</button>
            </div>

            {editingQuotaId === o.id && (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <label style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  Max queries/day
                  <input aria-label={`Max queries per day for ${o.name}`} placeholder="unlimited"
                    value={quotaDraft.max_queries_per_day ?? ''}
                    onChange={e => setQuotaDraft(d => ({ ...d, max_queries_per_day: e.target.value }))} {...inp} />
                </label>
                <label style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  Max agent asks/day
                  <input aria-label={`Max agent asks per day for ${o.name}`} placeholder="unlimited"
                    value={quotaDraft.max_agent_asks_per_day ?? ''}
                    onChange={e => setQuotaDraft(d => ({ ...d, max_agent_asks_per_day: e.target.value }))} {...inp} />
                </label>
                <label style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  Max storage (MB)
                  <input aria-label={`Max storage MB for ${o.name}`} placeholder="unlimited"
                    value={quotaDraft.max_storage_mb ?? ''}
                    onChange={e => setQuotaDraft(d => ({ ...d, max_storage_mb: e.target.value }))} {...inp} />
                </label>
                <label style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  Max concurrent asks
                  <input aria-label={`Max concurrent asks for ${o.name}`} placeholder="unlimited"
                    value={quotaDraft.max_concurrent_asks ?? ''}
                    onChange={e => setQuotaDraft(d => ({ ...d, max_concurrent_asks: e.target.value }))} {...inp} />
                </label>
                <button className="btn btn-primary btn-sm" onClick={() => saveQuota(o)}>Save quota</button>
                <button className="btn btn-sm" onClick={() => setEditingQuotaId(null)}>Cancel</button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
