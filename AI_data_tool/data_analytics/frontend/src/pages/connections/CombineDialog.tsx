/**
 * One dataset from tables in several database connections (requested
 * 2026-09-25). It used to take an import per connection and then a
 * hand-built prep pipeline; here the person picks a table in each database
 * and how to combine them, and gets one dataset. The per-source imports are
 * kept (the result is rebuilt from them), and the pipeline stays editable.
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { dataSourcesApi, datasetsApi, type DataSource } from '../../services/api'
import { useModalDialog } from '../../components/ui/useModalDialog'
import { useT } from '../../i18n'

type Row = { data_source_id: number | ''; table: string; label: string }

export default function CombineDialog({ sources, onClose }: { sources: DataSource[]; onClose: () => void }) {
  const tr = useT()
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [how, setHow] = useState('append')
  const [on, setOn] = useState('')
  const [rows, setRows] = useState<Row[]>([{ data_source_id: '', table: '', label: '' }, { data_source_id: '', table: '', label: '' }])
  const [tables, setTables] = useState<Record<number, string[]>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    for (const r of rows) {
      const id = r.data_source_id
      if (typeof id === 'number' && !(id in tables)) {
        setTables(t => ({ ...t, [id]: [] }))
        dataSourcesApi.schema(id)
          .then(s => setTables(t => ({ ...t, [id]: s.tables.map(x => x.name) })))
          .catch(() => setTables(t => ({ ...t, [id]: [] })))
      }
    }
  }, [rows, tables])

  const set = (i: number, patch: Partial<Row>) => setRows(rs => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const ready = name.trim() && rows.every(r => typeof r.data_source_id === 'number' && r.table)
    && (how === 'append' || on.trim())

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const ds = await datasetsApi.combine({
        name: name.trim(), how,
        on: how === 'append' ? [] : on.split(/[,،]/).map(s => s.trim()).filter(Boolean),
        sources: rows.map(r => ({ data_source_id: r.data_source_id as number, table: r.table,
                                  label: r.label.trim() || undefined })),
      })
      navigate(`/datasets/${ds.id}`)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? tr('pg.dataPages.combine.failed'))
    } finally {
      setBusy(false)
    }
  }

  const sel = { fontSize: 12, padding: '4px 6px' } as const
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,.45)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={tr('pg.dataPages.combine.open')} onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
          width: 'min(640px, 100%)', maxHeight: '90vh', overflowY: 'auto', padding: 16 }}>
        <h2 style={{ fontSize: 15, margin: '0 0 4px' }}>{tr('pg.dataPages.combine.title')}</h2>
        <p style={{ fontSize: 12, color: 'var(--muted)', margin: '0 0 12px' }}>
          {tr('pg.dataPages.combine.intro')}
        </p>
        <label style={{ display: 'block', fontSize: 12, marginBottom: 8 }}>{tr('pg.dataPages.combine.name')}
          <input value={name} onChange={e => setName(e.target.value)} style={{ display: 'block', width: '100%' }}
            aria-label={tr('pg.dataPages.combine.name')} />
        </label>
        {rows.map((r, i) => (
          <div key={i} style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginBottom: 6 }}>
            <select aria-label={tr('pg.dataPages.combine.connectionN', { n: i + 1 })} value={r.data_source_id} style={sel}
              onChange={e => set(i, { data_source_id: e.target.value ? Number(e.target.value) : '', table: '' })}>
              <option value="">{tr('pg.dataPages.combine.pickConnection')}</option>
              {sources.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <select aria-label={tr('pg.dataPages.combine.tableN', { n: i + 1 })} value={r.table} style={sel} disabled={typeof r.data_source_id !== 'number'}
              onChange={e => set(i, { table: e.target.value })}>
              <option value="">{tr('pg.dataPages.combine.pickTable')}</option>
              {(typeof r.data_source_id === 'number' ? tables[r.data_source_id] ?? [] : []).map(t =>
                <option key={t} value={t}>{t}</option>)}
            </select>
            <input aria-label={tr('pg.dataPages.combine.labelN', { n: i + 1 })} value={r.label} placeholder={tr('pg.dataPages.combine.labelPlaceholder')} style={{ ...sel, width: 130 }}
              onChange={e => set(i, { label: e.target.value })} />
            {rows.length > 2 && (
              <button type="button" className="btn btn-ghost btn-sm" aria-label={tr('pg.dataPages.combine.removeN', { n: i + 1 })}
                onClick={() => setRows(rs => rs.filter((_, j) => j !== i))}>×</button>
            )}
          </div>
        ))}
        {rows.length < 6 && (
          <button type="button" className="btn btn-ghost btn-sm"
            onClick={() => setRows(rs => [...rs, { data_source_id: '', table: '', label: '' }])}>{tr('pg.dataPages.combine.add')}</button>
        )}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginTop: 10, fontSize: 12 }}>
          <label>{tr('pg.dataPages.combine.by')}{' '}
            <select aria-label={tr('pg.dataPages.combine.by')} value={how} style={sel} onChange={e => setHow(e.target.value)}>
              <option value="append">{tr('pg.dataPages.combine.append')}</option>
              <option value="left">{tr('pg.dataPages.combine.left')}</option>
              <option value="inner">{tr('pg.dataPages.combine.inner')}</option>
              <option value="full">{tr('pg.dataPages.combine.full')}</option>
            </select>
          </label>
          {how !== 'append' && (
            <label>{tr('pg.dataPages.combine.on')}{' '}
              <input aria-label={tr('pg.dataPages.combine.keys')} value={on} placeholder={tr('pg.dataPages.combine.keysPlaceholder')}
                style={{ ...sel, width: 220 }} onChange={e => setOn(e.target.value)} />
            </label>
          )}
        </div>
        {error && <p role="alert" style={{ color: 'var(--danger)', fontSize: 12 }}>{error}</p>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 14 }}>
          <button type="button" className="btn btn-ghost" onClick={onClose}>{tr('common.cancel')}</button>
          <button type="button" className="btn btn-primary" disabled={!ready || busy} onClick={() => void create()}>
            {busy ? tr('pg.dataPages.combine.busy') : tr('pg.dataPages.combine.create')}
          </button>
        </div>
      </div>
    </div>
  )
}
