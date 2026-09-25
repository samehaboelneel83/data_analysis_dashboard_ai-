import { useEffect, useState } from 'react'
import { useT } from '../../i18n'
import { Database } from 'lucide-react'
import toast from 'react-hot-toast'
import { datasetsApi, exportPolicyApi } from '../../services/api'
import type { Dataset, ExportPolicy } from '../../services/api'
import EmptyState from '../../components/ui/EmptyState'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

const FORMATS = ['csv', 'tsv', 'xlsx'] as const

/**
 * Per-dataset, per-destination export governance (SAS's model): disable all
 * exports, disable specific formats, or auto-disable while the dataset
 * carries row- or column-security rules — the "private data present" signal,
 * evaluated live at export time, so a rule added later closes exports with
 * no policy revisit.
 */
export default function AdminExportPolicy() {
  const t = useT()
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [policies, setPolicies] = useState<Record<number, { policy: ExportPolicy; hasRules: boolean }>>({})
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)

  const load = () => {
    setLoading(true)
    setLoadError(null)
    datasetsApi.list().then(async list => {
      setDatasets(list)
      const entries = await Promise.all(list.map(async ds => {
        try {
          const p = await exportPolicyApi.get(ds.id)
          return [ds.id, { policy: p.export_policy, hasRules: p.has_security_rules }] as const
        } catch {
          return [ds.id, { policy: false as ExportPolicy, hasRules: false }] as const
        }
      }))
      setPolicies(Object.fromEntries(entries))
    })
      // The dataset list failing to load at all is this page's whole content
      // going missing -- the persistent LoadError banner below, not a toast
      // that fades and leaves an unexplained empty table.
      .catch(setLoadError)
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const save = async (dsId: number, next: { formats: string[]; auto_private: boolean; all: boolean }) => {
    try {
      if (next.all) {
        await exportPolicyApi.setAll(dsId, true)
        setPolicies(p => ({ ...p, [dsId]: { ...p[dsId], policy: true } }))
      } else {
        const res = await exportPolicyApi.setGranular(dsId, next.formats, next.auto_private)
        setPolicies(p => ({ ...p, [dsId]: { ...p[dsId], policy: res.export_policy } }))
      }
      toast.success(t('export.saved'))
    } catch (e: unknown) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Save failed')
    }
  }

  const parts = (pol: ExportPolicy) => ({
    all: pol === true,
    formats: typeof pol === 'object' && pol !== null ? (pol.formats ?? []) : [],
    auto: typeof pol === 'object' && pol !== null ? !!pol.auto_private : false,
  })

  return (
    <div style={{ maxWidth: 960 }}>
      <h1 className="dl-page-title" style={{ marginBottom: 4 }}>{t('nav.exportPolicy')}</h1>
      <p className="dl-page-head__sub" style={{ marginBottom: 16, maxWidth: 760 }}>
        {t('export.subtitle')}
      </p>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="datasets" error={loadError} onRetry={load} />
      )}

      {!loading && loadError == null && datasets.length === 0 && (
        <EmptyState icon={Database} title={t('export.noDatasets')}
          description={t('export.noDatasetsBody')} />
      )}

      {!loading && loadError == null && datasets.length > 0 && (
      <div className="card dl-table-card">
      <table className="dl-table dl-table--center-checks">
        <thead>
          <tr>
            <th>{t('export.col.dataset')}</th>
            <th>{t('export.col.allOff')}</th>
            {FORMATS.map(f => <th key={f}>{t('export.col.off', { f })}</th>)}
            <th>{t('export.col.auto')}</th>
            <th>{t('export.col.rules')}</th>
          </tr>
        </thead>
        <tbody>
          {datasets.map(ds => {
            const entry = policies[ds.id]
            if (!entry) return null
            const { all, formats, auto } = parts(entry.policy)
            return (
              <tr key={ds.id}>
                <td style={{ fontWeight: 600 }}>{ds.name}</td>
                <td>
                  <input type="checkbox" checked={all} aria-label={`All exports off for ${ds.name}`}
                    onChange={e => e.target.checked
                      ? save(ds.id, { all: true, formats: [], auto_private: false })
                      : save(ds.id, { all: false, formats: [], auto_private: false })} />
                </td>
                {FORMATS.map(f => (
                  <td key={f}>
                    <input type="checkbox" checked={all || formats.includes(f)} disabled={all} title={all ? 'Everything is allowed: untick "All" to choose' : undefined}
                      aria-label={`${f} export off for ${ds.name}`}
                      onChange={e => save(ds.id, { all: false, auto_private: auto,
                        formats: e.target.checked ? [...formats, f] : formats.filter(x => x !== f) })} />
                  </td>
                ))}
                <td>
                  <input type="checkbox" checked={auto} disabled={all} title={all ? 'Everything is allowed: untick "All" to choose' : undefined}
                    aria-label={`Auto-disable when private for ${ds.name}`}
                    onChange={e => save(ds.id, { all: false, formats, auto_private: e.target.checked })} />
                </td>
                <td>
                  {entry.hasRules
                    ? <span className="badge" style={{ color: 'var(--danger)', background: 'color-mix(in srgb, var(--danger) 10%, transparent)' }}>{t('export.present')}</span>
                    : <span style={{ color: 'var(--muted)' }}>{t('export.none')}</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      </div>
      )}
    </div>
  )
}
