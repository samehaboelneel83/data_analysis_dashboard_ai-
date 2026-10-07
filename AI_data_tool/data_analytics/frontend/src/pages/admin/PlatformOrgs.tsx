import { useEffect, useState } from 'react'
import { inlineFieldStyle } from '../../components/ui/fieldStyle'
import { useT, type MessageKey } from '../../i18n'
import { Building2 } from 'lucide-react'
import { platformApi } from '../../services/api'
import type { OrgAiUsage, OrgQuota, PlatformOrg } from '../../services/api'
import toast from 'react-hot-toast'
import EmptyState from '../../components/ui/EmptyState'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

const fmtMb = (bytes: number) => (bytes / (1024 * 1024)).toFixed(1)
/** What each metered feature is, in the words an administrator uses. */
const FEATURE_LABEL: Record<string, MessageKey> = {
  ask: 'pg.adminPlatform.orgs.feature.ask', copilot: 'pg.adminPlatform.orgs.feature.copilot',
  suggest: 'pg.adminPlatform.orgs.feature.suggest', insights: 'pg.adminPlatform.orgs.feature.insights',
  explain: 'pg.adminPlatform.orgs.feature.explain', narrate: 'pg.adminPlatform.orgs.feature.narrate',
  metadata: 'pg.adminPlatform.orgs.feature.metadata', automation: 'pg.adminPlatform.orgs.feature.automation',
}

export default function PlatformOrgs() {
  const t = useT()
  const fmtLimit = (n: number | null) => (n == null ? t('pg.adminPlatform.orgs.unlimited') : n.toLocaleString())
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
    if (!name.trim() || !adminEmail.trim() || !adminPassword) { toast.error(t('pg.adminPlatform.orgs.required')); return }
    setCreating(true)
    try {
      await platformApi.createOrg({ name: name.trim(), admin_email: adminEmail.trim(), admin_password: adminPassword })
      toast.success(t('pg.adminPlatform.orgs.created', { name: name.trim() }))
      setName(''); setAdminEmail(''); setAdminPassword('')
      await load()
    } catch (e: any) { toast.error(e?.response?.data?.detail ?? t('pg.adminPlatform.createFailed')) }
    finally { setCreating(false) }
  }

  const setParent = async (org: PlatformOrg, parentOrgId: number | null) => {
    try {
      await platformApi.setParent(org.id, parentOrgId)
      await load()
    } catch (e: any) { toast.error(e?.response?.data?.detail ?? t('pg.adminPlatform.orgs.parentFailed')) }
  }

  const setMcp = async (org: PlatformOrg, enabled: boolean) => {
    try {
      await platformApi.setMcp(org.id, enabled)
      await load()
      toast.success(t(enabled ? 'pg.adminPlatform.orgs.mcpOn' : 'pg.adminPlatform.orgs.mcpOff', { name: org.name }))
    } catch (e: any) { toast.error(e?.response?.data?.detail ?? t('pg.adminPlatform.orgs.mcpFailed')) }
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
      max_ai_tokens_per_day: org.quota.max_ai_tokens_per_day?.toString() ?? '',
      max_ai_tokens_per_month: org.quota.max_ai_tokens_per_month?.toString() ?? '',
    })
  }

  // E11: the breakdown behind an org's AI tokens, loaded when asked for.
  const [aiUsage, setAiUsage] = useState<{ orgId: number; data: OrgAiUsage | null } | null>(null)
  const toggleAiUsage = async (org: PlatformOrg) => {
    if (aiUsage?.orgId === org.id) { setAiUsage(null); return }
    setAiUsage({ orgId: org.id, data: null })
    try {
      const data = await platformApi.aiUsage(org.id)
      setAiUsage(cur => cur?.orgId === org.id ? { orgId: org.id, data } : cur)
    } catch (e: any) {
      setAiUsage(null)
      toast.error(e?.response?.data?.detail ?? t('pg.adminPlatform.orgs.aiUsageFailed'))
    }
  }

  const saveQuota = async (org: PlatformOrg) => {
    const toNullableInt = (v: string) => (v.trim() === '' ? null : Number(v))
    const body: OrgQuota = {
      max_queries_per_day: toNullableInt(quotaDraft.max_queries_per_day ?? ''),
      max_agent_asks_per_day: toNullableInt(quotaDraft.max_agent_asks_per_day ?? ''),
      max_storage_mb: toNullableInt(quotaDraft.max_storage_mb ?? ''),
      max_concurrent_asks: toNullableInt(quotaDraft.max_concurrent_asks ?? ''),
      max_ai_tokens_per_day: toNullableInt(quotaDraft.max_ai_tokens_per_day ?? ''),
      max_ai_tokens_per_month: toNullableInt(quotaDraft.max_ai_tokens_per_month ?? ''),
    }
    try {
      await platformApi.setQuota(org.id, body)
      toast.success(t('pg.adminPlatform.orgs.quotaUpdated', { name: org.name }))
      setEditingQuotaId(null)
      await load()
    } catch (e: any) { toast.error(e?.response?.data?.detail ?? t('pg.adminPlatform.orgs.quotaFailed')) }
  }

  const nameOf = (id: number | null) => (id == null ? '—' : orgs.find(o => o.id === id)?.name ?? `#${id}`)

  const inp = { style: inlineFieldStyle }
  const cell = { padding: '2px 8px', borderBottom: '1px solid var(--border)' }

  return (
    <div>
      <h1 className="dl-page-title" style={{ marginBottom: 6 }}>{t('nav.organizations')}</h1>
      <div className="dl-page-head__sub" style={{ marginBottom: 20, maxWidth: 720 }}>
        {t('pg.adminPlatform.orgs.sub')}
      </div>

      <div className="card" style={{ padding: 16, marginBottom: 20 }}>
        <div className="dl-rows__title" style={{ marginBottom: 10 }}>{t('pg.adminPlatform.orgs.new')}</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input aria-label={t('pg.adminPlatform.orgs.name')} placeholder={t('pg.adminPlatform.orgs.name')} value={name} onChange={e => setName(e.target.value)} {...inp} />
          <input aria-label={t('pg.adminPlatform.orgs.adminEmail')} placeholder={t('pg.adminPlatform.orgs.adminEmail')} value={adminEmail}
            onChange={e => setAdminEmail(e.target.value)} autoComplete="off" name="new-org-admin-email" {...inp} />
          <input aria-label={t('pg.adminPlatform.orgs.adminPassword')} type="password" placeholder={t('pg.adminPlatform.orgs.adminPassword')} value={adminPassword}
            onChange={e => setAdminPassword(e.target.value)} autoComplete="new-password" name="new-org-admin-password" {...inp} />
          <button className="btn btn-primary btn-sm" onClick={createOrg} disabled={creating}>
            {creating ? t('pg.adminPlatform.creating') : t('pg.adminPlatform.orgs.create')}
          </button>
        </div>
      </div>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what={t('pg.adminPlatform.orgs.loadWhat')} title={t('pg.adminPlatform.loadErr', { what: t('pg.adminPlatform.orgs.loadWhat') })}
          retryLabel={t('pg.adminPlatform.retry')} error={loadError} onRetry={() => { setLoading(true); load().finally(() => setLoading(false)) }} />
      )}

      {!loading && loadError == null && orgs.length === 0 && (
        <EmptyState icon={Building2} title={t('pg.adminPlatform.orgs.empty')}
          description={t('pg.adminPlatform.orgs.emptyDesc')} />
      )}

      <div className="dl-rows">
        {orgs.map(o => (
          <div key={o.id} className="dl-rows__row dl-rows__row--stack">
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
              <div className="dl-rows__main">
                <div className="dl-rows__title"><bdi>{o.name}</bdi></div>
                <div className="dl-rows__meta">
                  {t('pg.adminPlatform.orgs.meta', { n: o.user_count, parent: nameOf(o.parent_org_id) })}
                </div>
              </div>
              <label style={{ fontSize: 11, color: o.mcp_enabled ? 'var(--text)' : 'var(--muted)', display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
                title={t('pg.adminPlatform.orgs.mcpTitle')}>
                <input type="checkbox" aria-label={t('pg.adminPlatform.orgs.mcpAccess', { name: o.name })} checked={o.mcp_enabled}
                  onChange={e => setMcp(o, e.target.checked)} />
                {o.mcp_enabled ? t('pg.adminPlatform.orgs.mcpStateOn') : t('pg.adminPlatform.orgs.mcpStateOff')}
              </label>
              <label style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                {t('pg.adminPlatform.orgs.parent')}
                <select aria-label={t('pg.adminPlatform.orgs.parentOf', { name: o.name })} value={o.parent_org_id ?? ''}
                  onChange={e => setParent(o, e.target.value ? Number(e.target.value) : null)} {...inp}>
                  <option value="">{t('pg.adminPlatform.orgs.noParent')}</option>
                  {orgs.filter(x => x.id !== o.id).map(x => <option key={x.id} value={x.id}>{x.name}</option>)}
                </select>
              </label>
            </div>

            {/* Task E2: usage-vs-quota column */}
            <div style={{ fontSize: 11.5, color: 'var(--muted)', borderTop: '1px dashed var(--border)', paddingTop: 8,
              display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap', fontVariantNumeric: 'tabular-nums' }}>
              <span>{t('pg.adminPlatform.orgs.queriesToday', { used: o.usage.queries_today, limit: fmtLimit(o.quota.max_queries_per_day) })}</span>
              <span>{t('pg.adminPlatform.orgs.agentAsksToday', { used: o.usage.agent_asks_today, limit: fmtLimit(o.quota.max_agent_asks_per_day) })}</span>
              <span>{t('pg.adminPlatform.orgs.storage', { used: fmtMb(o.usage.storage_bytes), limit: fmtLimit(o.quota.max_storage_mb) })}</span>
              <span>{t('pg.adminPlatform.orgs.concurrent', { limit: fmtLimit(o.quota.max_concurrent_asks) })}</span>
              <span>{t('pg.adminPlatform.orgs.tokensToday', { used: o.usage.ai_tokens_today.toLocaleString(), limit: fmtLimit(o.quota.max_ai_tokens_per_day) })}</span>
              <span>{t('pg.adminPlatform.orgs.tokensMonth', { used: o.usage.ai_tokens_month.toLocaleString(), limit: fmtLimit(o.quota.max_ai_tokens_per_month) })}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => toggleAiUsage(o)} aria-expanded={aiUsage?.orgId === o.id}
                style={{ marginInlineStart: 'auto' }}>{t('pg.adminPlatform.orgs.aiUsage')}</button>
              <button className="btn btn-ghost btn-sm" onClick={() => startEditQuota(o)}>{t('pg.adminPlatform.orgs.editQuota')}</button>
            </div>

            {aiUsage?.orgId === o.id && (
              <div data-testid="ai-usage" style={{ fontSize: 11.5, display: 'flex', gap: 24, flexWrap: 'wrap', fontVariantNumeric: 'tabular-nums' }}>
                {aiUsage.data == null ? <span style={{ color: 'var(--muted)' }}>{t('pg.adminPlatform.loading')}</span> : <>
                  <div>
                    <div style={{ fontWeight: 700, marginBottom: 4 }}>
                      {t('pg.adminPlatform.orgs.lastDays', { days: aiUsage.data.days, tokens: aiUsage.data.total_tokens.toLocaleString() })}
                    </div>
                    {aiUsage.data.remaining != null && (
                      <div style={{ color: aiUsage.data.remaining <= 0 ? 'var(--danger, #c0392b)' : 'var(--muted)' }}>
                        {aiUsage.data.remaining <= 0
                          ? t(aiUsage.data.binding_limit === 'ai_tokens_per_month' ? 'pg.adminPlatform.orgs.usedUpMonth' : 'pg.adminPlatform.orgs.usedUpToday')
                          : t(aiUsage.data.binding_limit === 'ai_tokens_per_month' ? 'pg.adminPlatform.orgs.leftMonth' : 'pg.adminPlatform.orgs.leftToday',
                              { n: aiUsage.data.remaining.toLocaleString() })}
                      </div>
                    )}
                  </div>
                  <table style={{ borderCollapse: 'collapse' }} aria-label={t('pg.adminPlatform.orgs.byFeature', { name: o.name })}>
                    <thead><tr><th style={{ ...cell, textAlign: 'start' }}>{t('pg.adminPlatform.orgs.thFeature')}</th><th style={cell}>{t('pg.adminPlatform.orgs.thTokens')}</th><th style={cell}>{t('pg.adminPlatform.orgs.thCalls')}</th><th style={cell}>{t('pg.adminPlatform.orgs.thRefused')}</th></tr></thead>
                    <tbody>
                      {aiUsage.data.by_feature.length === 0 && <tr><td colSpan={4} style={{ ...cell, color: 'var(--muted)' }}>{t('pg.adminPlatform.orgs.noAiUse')}</td></tr>}
                      {aiUsage.data.by_feature.map(f => (
                        <tr key={f.feature}><td style={cell}>{FEATURE_LABEL[f.feature] ? t(FEATURE_LABEL[f.feature]) : <bdi>{f.feature}</bdi>}</td>
                          <td style={{ ...cell, textAlign: 'end' }}>{f.tokens.toLocaleString()}</td>
                          <td style={{ ...cell, textAlign: 'end' }}>{f.calls.toLocaleString()}</td>
                          <td style={{ ...cell, textAlign: 'end' }}>{f.refused.toLocaleString()}</td></tr>
                      ))}
                    </tbody>
                  </table>
                  <table style={{ borderCollapse: 'collapse' }} aria-label={t('pg.adminPlatform.orgs.byPerson', { name: o.name })}>
                    <thead><tr><th style={{ ...cell, textAlign: 'start' }}>{t('pg.adminPlatform.orgs.thPerson')}</th><th style={cell}>{t('pg.adminPlatform.orgs.thTokens')}</th></tr></thead>
                    <tbody>
                      {aiUsage.data.by_user.slice(0, 10).map(u => (
                        <tr key={u.user_id ?? 'none'}><td style={cell}>{u.email ? <bdi dir="ltr">{u.email}</bdi> : t('pg.adminPlatform.orgs.scheduled')}</td>
                          <td style={{ ...cell, textAlign: 'end' }}>{u.tokens.toLocaleString()}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </>}
              </div>
            )}

            {editingQuotaId === o.id && (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <label style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {t('pg.adminPlatform.orgs.q.queries')}
                  <input aria-label={t('pg.adminPlatform.orgs.q.queriesFor', { name: o.name })} placeholder={t('pg.adminPlatform.orgs.unlimited')}
                    value={quotaDraft.max_queries_per_day ?? ''}
                    onChange={e => setQuotaDraft(d => ({ ...d, max_queries_per_day: e.target.value }))} {...inp} />
                </label>
                <label style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {t('pg.adminPlatform.orgs.q.asks')}
                  <input aria-label={t('pg.adminPlatform.orgs.q.asksFor', { name: o.name })} placeholder={t('pg.adminPlatform.orgs.unlimited')}
                    value={quotaDraft.max_agent_asks_per_day ?? ''}
                    onChange={e => setQuotaDraft(d => ({ ...d, max_agent_asks_per_day: e.target.value }))} {...inp} />
                </label>
                <label style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {t('pg.adminPlatform.orgs.q.storage')}
                  <input aria-label={t('pg.adminPlatform.orgs.q.storageFor', { name: o.name })} placeholder={t('pg.adminPlatform.orgs.unlimited')}
                    value={quotaDraft.max_storage_mb ?? ''}
                    onChange={e => setQuotaDraft(d => ({ ...d, max_storage_mb: e.target.value }))} {...inp} />
                </label>
                <label style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {t('pg.adminPlatform.orgs.q.concurrent')}
                  <input aria-label={t('pg.adminPlatform.orgs.q.concurrentFor', { name: o.name })} placeholder={t('pg.adminPlatform.orgs.unlimited')}
                    value={quotaDraft.max_concurrent_asks ?? ''}
                    onChange={e => setQuotaDraft(d => ({ ...d, max_concurrent_asks: e.target.value }))} {...inp} />
                </label>
                <label style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {t('pg.adminPlatform.orgs.q.tokensDay')}
                  <input aria-label={t('pg.adminPlatform.orgs.q.tokensDayFor', { name: o.name })} placeholder={t('pg.adminPlatform.orgs.unlimited')} inputMode="numeric"
                    value={quotaDraft.max_ai_tokens_per_day ?? ''}
                    onChange={e => setQuotaDraft(d => ({ ...d, max_ai_tokens_per_day: e.target.value }))} {...inp} />
                </label>
                <label style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {t('pg.adminPlatform.orgs.q.tokensMonth')}
                  <input aria-label={t('pg.adminPlatform.orgs.q.tokensMonthFor', { name: o.name })} placeholder={t('pg.adminPlatform.orgs.unlimited')} inputMode="numeric"
                    value={quotaDraft.max_ai_tokens_per_month ?? ''}
                    onChange={e => setQuotaDraft(d => ({ ...d, max_ai_tokens_per_month: e.target.value }))} {...inp} />
                </label>
                <button className="btn btn-primary btn-sm" onClick={() => saveQuota(o)}>{t('pg.adminPlatform.orgs.saveQuota')}</button>
                <button className="btn btn-sm" onClick={() => setEditingQuotaId(null)}>{t('pg.adminPlatform.cancel')}</button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
