import { useEffect, useState } from 'react'
import { inlineFieldStyle } from '../../components/ui/fieldStyle'
import { useT } from '../../i18n'
import { richNodes } from '../../i18n/pages/adminPlatform'
import { Key } from 'lucide-react'
import { apiKeysApi } from '../../services/api'
import type { ApiKey } from '../../services/api'
import toast from 'react-hot-toast'
import { useConfirm } from '../../components/ui/ConfirmDialog'
import EmptyState from '../../components/ui/EmptyState'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

/** The environment variable an MCP agent reads; a name, not words. */
const TOKEN_ENV = 'DATALYTICS_TOKEN'
const keyHint = (prefix: string) => `dk_${prefix}…`

export default function ApiKeys() {
  const t = useT()
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [loading, setLoading] = useState(true)
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [freshKey, setFreshKey] = useState<string | null>(null)   // shown once
  const confirm = useConfirm()

  const [loadError, setLoadError] = useState<unknown>(null)

  // The swallowed catch rendered "No API keys yet." on an outage -- telling an
  // admin their keys are gone when they are simply unreadable right now.
  const load = () => {
    setLoadError(null)
    return apiKeysApi.list().then(setKeys)
      .catch(e => setLoadError(e ?? new Error('failed')))
  }
  useEffect(() => { load().finally(() => setLoading(false)) }, [])

  const create = async () => {
    if (!name.trim()) { toast.error(t('pg.adminPlatform.keys.nameFirst')); return }
    setCreating(true)
    try {
      const k = await apiKeysApi.create(name.trim())
      setFreshKey(k.key)          // reveal once
      setName('')
      await load()
    } catch (e: any) { toast.error(e?.response?.data?.detail ?? t('pg.adminPlatform.createFailed')) }
    finally { setCreating(false) }
  }

  const revoke = async (k: ApiKey) => {
    // confirmLabel matters here: the default is "Delete", so the dialog for
    // revoking a key read "Delete" while the button that opened it said
    // "Revoke".
    if (!await confirm({
      title: t('pg.adminPlatform.keys.revokeTitle', { name: k.name }),
      body: t('pg.adminPlatform.keys.revokeBody'),
      confirmLabel: t('pg.adminPlatform.keys.revokeConfirm'),
    })) return
    // Previously unguarded, unlike `create` right above it. A failed revoke
    // threw out of the handler before the toast: no success message, no error
    // message, the key still listed. An admin revoking a LEAKED key saw
    // nothing happen and had no way to tell the key was still live.
    try {
      await apiKeysApi.revoke(k.id)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? t('pg.adminPlatform.keys.revokeFailed'))
      return
    }
    if (freshKey) setFreshKey(null)
    await load()
    toast.success(t('pg.adminPlatform.keys.revoked'))
  }

  const inp = { style: inlineFieldStyle }

  return (
    <div>
      <h1 className="dl-page-title" style={{ marginBottom: 6 }}>{t('nav.apiKeys')}</h1>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 20 }}>
        {richNodes(t('pg.adminPlatform.keys.intro'), { code: <code dir="ltr">{TOKEN_ENV}</code> })}
      </div>

      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 16, marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input aria-label={t('pg.adminPlatform.keys.keyName')} placeholder={t('pg.adminPlatform.keys.keyNamePh')} value={name} onChange={e => setName(e.target.value)} {...inp} />
          <button className="btn btn-primary btn-sm" onClick={create} disabled={creating}>
            {creating ? t('pg.adminPlatform.creating') : t('pg.adminPlatform.keys.create')}
          </button>
        </div>
        {freshKey && (
          <div style={{ marginTop: 12, padding: 12, background: 'var(--surface2)', border: '1px solid var(--accent)', borderRadius: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent)', marginBottom: 6 }}>
              {t('pg.adminPlatform.keys.copyNow')}
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <code dir="ltr" style={{ fontFamily: 'var(--mono)', fontSize: 12, wordBreak: 'break-all', flex: 1 }}>{freshKey}</code>
              <button className="btn btn-ghost btn-sm" onClick={() => { navigator.clipboard.writeText(freshKey).then(() => toast.success(t('pg.adminPlatform.keys.copied'))).catch(() => {}) }}>{t('pg.adminPlatform.keys.copy')}</button>
            </div>
          </div>
        )}
      </div>

      {loading && <LoadingState />}
      {!loading && loadError != null && (
        <LoadError what={t('pg.adminPlatform.keys.loadWhat')} title={t('pg.adminPlatform.loadErr', { what: t('pg.adminPlatform.keys.loadWhat') })}
          retryLabel={t('pg.adminPlatform.retry')} error={loadError} onRetry={load} />
      )}
      {!loading && loadError == null && keys.length === 0 && (
        <EmptyState icon={Key} title={t('pg.adminPlatform.keys.empty')}
          description={t('pg.adminPlatform.keys.emptyDesc')} />
      )}
      <div className="dl-rows">
        {keys.map(k => (
          <div key={k.id} className="dl-rows__row">
            <div className="dl-rows__main">
              <div className="dl-rows__title"><bdi>{k.name}</bdi></div>
              <div className="dl-rows__meta dl-rows__meta--mono">
                <bdi dir="ltr">{keyHint(k.prefix)}</bdi>{k.last_used_at ? '' : t('pg.adminPlatform.keys.neverUsed')}
              </div>
            </div>
            <button className="btn btn-ghost btn-sm dl-danger-item" onClick={() => revoke(k)}>{t('admin.revoke')}</button>
          </div>
        ))}
      </div>
    </div>
  )
}
