import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { reportsApi, datasetsApi } from '../services/api'
import type { ReportSummary, DatasetSummary } from '../services/api'
import { FileBarChart, Plus, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'

export default function Reports() {
  const [reports, setReports]   = useState<ReportSummary[]>([])
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [loading, setLoading]   = useState(true)
  const [creating, setCreating] = useState(false)
  const [name, setName]         = useState('')
  const [desc, setDesc]         = useState('')
  const [dsId, setDsId]         = useState<number | ''>('')

  useEffect(() => {
    Promise.all([reportsApi.list(), datasetsApi.list()])
      .then(([r, d]) => { setReports(r); setDatasets(d) })
      .finally(() => setLoading(false))
  }, [])

  const handleCreate = async () => {
    if (!name.trim()) return
    const r = await reportsApi.create({ name: name.trim(), description: desc || undefined, dataset_id: dsId || undefined })
    toast.success('Report created')
    setCreating(false); setName(''); setDesc(''); setDsId('')
    setReports(prev => [r, ...prev])
  }

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`Delete report "${name}"?`)) return
    await reportsApi.delete(id)
    setReports(r => r.filter(x => x.id !== id))
    toast.success('Report deleted')
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Reports</h1>
          <p style={{ color: 'var(--muted)', fontSize: 13 }}>Build multi-page interactive reports with drag-and-drop widgets</p>
        </div>
        <button className="btn btn-primary" onClick={() => setCreating(true)}>
          <Plus size={14} /> New report
        </button>
      </div>

      {/* Create form */}
      {creating && (
        <div className="card" style={{ marginBottom: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <h3 style={{ fontWeight: 600 }}>New Report</h3>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="Report name *" style={{ width: '100%' }} />
          <input value={desc} onChange={e => setDesc(e.target.value)} placeholder="Description (optional)" style={{ width: '100%' }} />
          <select value={dsId} onChange={e => setDsId(e.target.value ? Number(e.target.value) : '')} style={{ width: '100%' }}>
            <option value="">— No dataset (add later) —</option>
            {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" onClick={handleCreate} disabled={!name.trim()}>Create & Open</button>
            <button className="btn btn-ghost" onClick={() => setCreating(false)}>Cancel</button>
          </div>
        </div>
      )}

      {loading && <p style={{ color: 'var(--muted)' }}>Loading…</p>}

      {!loading && reports.length === 0 && (
        <div className="card" style={{ textAlign: 'center', padding: '56px 24px' }}>
          <FileBarChart size={40} color="var(--muted)" style={{ margin: '0 auto 16px' }} />
          <p style={{ fontWeight: 600, marginBottom: 8 }}>No reports yet</p>
          <p style={{ color: 'var(--muted)', marginBottom: 20 }}>Create a report and design it with charts, tables, KPIs, and more.</p>
          <button className="btn btn-primary" onClick={() => setCreating(true)}>Create your first report</button>
        </div>
      )}

      {reports.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
          {reports.map(r => {
            const ds = datasets.find(d => d.id === r.dataset_id)
            return (
              <div key={r.id} className="card" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <Link to={`/reports/${r.id}`} style={{ fontWeight: 600, fontSize: 15, color: 'var(--text)', textDecoration: 'none', lineHeight: 1.3 }}>
                    {r.name}
                  </Link>
                  <button className="btn btn-ghost btn-sm" onClick={() => handleDelete(r.id, r.name)} style={{ color: 'var(--danger)', flexShrink: 0 }}>
                    <Trash2 size={12} />
                  </button>
                </div>
                {r.description && <p style={{ fontSize: 12, color: 'var(--muted)' }}>{r.description}</p>}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 'auto' }}>
                  {ds ? <span className="badge badge-categorical">{ds.name}</span> : <span style={{ fontSize: 11, color: 'var(--muted)' }}>No dataset</span>}
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>{new Date(r.created_at).toLocaleDateString()}</span>
                </div>
                <Link to={`/reports/${r.id}`} className="btn btn-ghost btn-sm" style={{ justifyContent: 'center' }}>
                  Open designer →
                </Link>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
