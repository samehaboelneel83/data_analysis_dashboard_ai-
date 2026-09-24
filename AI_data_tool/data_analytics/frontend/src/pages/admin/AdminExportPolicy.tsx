import { useEffect, useState } from 'react'
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
      toast.success('Export policy saved')
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
    <div style={{ padding: 24, maxWidth: 900 }}>
      <h1 style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>Export policy</h1>
      <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 16 }}>
        Governs data downloads per dataset and per destination. “Auto when private” disables every export
        while the dataset has row- or column-security rules — checked live, so a rule added later closes
        exports immediately. Display in reports keeps working either way. Changes are audited.
      </p>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="datasets" error={loadError} onRetry={load} />
      )}

      {!loading && loadError == null && datasets.length === 0 && (
        <EmptyState icon={Database} title="No datasets yet"
          description="Export policy applies per dataset — upload or connect one first." />
      )}

      {!loading && loadError == null && datasets.length > 0 && (
      <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ textAlign: 'start', color: 'var(--muted)' }}>
            <th style={{ padding: '6px 8px' }}>Dataset</th>
            <th style={{ padding: '6px 8px' }}>All off</th>
            {FORMATS.map(f => <th key={f} style={{ padding: '6px 8px' }}>{f} off</th>)}
            <th style={{ padding: '6px 8px' }}>Auto when private</th>
            <th style={{ padding: '6px 8px' }}>Security rules</th>
          </tr>
        </thead>
        <tbody>
          {datasets.map(ds => {
            const entry = policies[ds.id]
            if (!entry) return null
            const { all, formats, auto } = parts(entry.policy)
            return (
              <tr key={ds.id} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: '6px 8px', fontWeight: 600 }}>{ds.name}</td>
                <td style={{ padding: '6px 8px' }}>
                  <input type="checkbox" checked={all} aria-label={`All exports off for ${ds.name}`}
                    onChange={e => e.target.checked
                      ? save(ds.id, { all: true, formats: [], auto_private: false })
                      : save(ds.id, { all: false, formats: [], auto_private: false })} />
                </td>
                {FORMATS.map(f => (
                  <td key={f} style={{ padding: '6px 8px' }}>
                    <input type="checkbox" checked={all || formats.includes(f)} disabled={all} title={all ? 'Everything is allowed: untick "All" to choose' : undefined}
                      aria-label={`${f} export off for ${ds.name}`}
                      onChange={e => save(ds.id, { all: false, auto_private: auto,
                        formats: e.target.checked ? [...formats, f] : formats.filter(x => x !== f) })} />
                  </td>
                ))}
                <td style={{ padding: '6px 8px' }}>
                  <input type="checkbox" checked={auto} disabled={all} title={all ? 'Everything is allowed: untick "All" to choose' : undefined}
                    aria-label={`Auto-disable when private for ${ds.name}`}
                    onChange={e => save(ds.id, { all: false, formats, auto_private: e.target.checked })} />
                </td>
                <td style={{ padding: '6px 8px', color: entry.hasRules ? 'var(--danger)' : 'var(--muted)' }}>
                  {entry.hasRules ? 'present' : 'none'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      )}
    </div>
  )
}
