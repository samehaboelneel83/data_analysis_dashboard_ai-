import { useEffect, useState } from 'react'
import { inlineFieldStyle } from '../../components/ui/fieldStyle'
import { useT } from '../../i18n'
import { Key } from 'lucide-react'
import { apiKeysApi } from '../../services/api'
import type { ApiKey } from '../../services/api'
import toast from 'react-hot-toast'
import { useConfirm } from '../../components/ui/ConfirmDialog'
import EmptyState from '../../components/ui/EmptyState'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

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
    if (!name.trim()) { toast.error('Name the key first'); return }
    setCreating(true)
    try {
      const k = await apiKeysApi.create(name.trim())
      setFreshKey(k.key)          // reveal once
      setName('')
      await load()
    } catch (e: any) { toast.error(e?.response?.data?.detail ?? 'Create failed') }
    finally { setCreating(false) }
  }

  const revoke = async (k: ApiKey) => {
    // confirmLabel matters here: the default is "Delete", so the dialog for
    // revoking a key read "Delete" while the button that opened it said
    // "Revoke".
    if (!await confirm({
      title: `Revoke "${k.name}"?`,
      body: 'Any agent using this key stops working immediately. This cannot be undone.',
      confirmLabel: 'Revoke key',
    })) return
    // Previously unguarded, unlike `create` right above it. A failed revoke
    // threw out of the handler before the toast: no success message, no error
    // message, the key still listed. An admin revoking a LEAKED key saw
    // nothing happen and had no way to tell the key was still live.
    try {
      await apiKeysApi.revoke(k.id)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Could not revoke this key — it is still active')
      return
    }
    if (freshKey) setFreshKey(null)
    await load()
    toast.success('Revoked')
  }

  const inp = { style: inlineFieldStyle }

  return (
    <div>
      <h1 className="dl-page-title" style={{ marginBottom: 6 }}>{t('nav.apiKeys')}</h1>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 20 }}>
        Durable bearer tokens for machine access — e.g. the MCP server that exposes datalytics to AI agents.
        A key authenticates as you, so it can see and do exactly what you can. Use it as <code>DATALYTICS_TOKEN</code>.
      </div>

      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 16, marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input aria-label="Key name" placeholder="Key name (e.g. MCP agent)" value={name} onChange={e => setName(e.target.value)} {...inp} />
          <button className="btn btn-primary btn-sm" onClick={create} disabled={creating}>
            {creating ? 'Creating…' : 'Create key'}
          </button>
        </div>
        {freshKey && (
          <div style={{ marginTop: 12, padding: 12, background: 'var(--surface2)', border: '1px solid var(--accent)', borderRadius: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent)', marginBottom: 6 }}>
              Copy this key now — it is shown only once and cannot be recovered.
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <code style={{ fontFamily: 'var(--mono)', fontSize: 12, wordBreak: 'break-all', flex: 1 }}>{freshKey}</code>
              <button className="btn btn-ghost btn-sm" onClick={() => { navigator.clipboard.writeText(freshKey).then(() => toast.success('Copied')).catch(() => {}) }}>Copy</button>
            </div>
          </div>
        )}
      </div>

      {loading && <LoadingState />}
      {!loading && loadError != null && (
        <LoadError what="your API keys" error={loadError} onRetry={load} />
      )}
      {!loading && loadError == null && keys.length === 0 && (
        <EmptyState icon={Key} title="No API keys yet"
          description="Create a key above to authenticate machine access, like an MCP agent." />
      )}
      <div className="dl-rows">
        {keys.map(k => (
          <div key={k.id} className="dl-rows__row">
            <div className="dl-rows__main">
              <div className="dl-rows__title">{k.name}</div>
              <div className="dl-rows__meta dl-rows__meta--mono">
                {`dk_${k.prefix}…`}{k.last_used_at ? '' : ' · never used'}
              </div>
            </div>
            <button className="btn btn-ghost btn-sm dl-danger-item" onClick={() => revoke(k)}>{t('admin.revoke')}</button>
          </div>
        ))}
      </div>
    </div>
  )
}
