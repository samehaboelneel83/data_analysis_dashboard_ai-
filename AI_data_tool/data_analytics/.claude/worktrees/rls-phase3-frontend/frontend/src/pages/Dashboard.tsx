import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { datasetsApi, DatasetSummary } from '../services/api'
import { Database, Trash2, Plus, BarChart2, Rows } from 'lucide-react'
import toast from 'react-hot-toast'

function fmtBytes(b: number) {
  if (b < 1024) return `${b} B`
  if (b < 1024 ** 2) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1024 ** 2).toFixed(1)} MB`
}

function fmtDate(s: string) {
  return new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function Dashboard() {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    datasetsApi.list().then(setDatasets).finally(() => setLoading(false))
  }, [])

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`Delete "${name}"? This cannot be undone.`)) return
    await datasetsApi.delete(id)
    setDatasets(d => d.filter(x => x.id !== id))
    toast.success('Dataset deleted')
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Datasets</h1>
          <p style={{ color: 'var(--muted)', fontSize: 13 }}>Upload and analyse your data files</p>
        </div>
        <Link to="/upload" className="btn btn-primary">
          <Plus size={15} /> Upload dataset
        </Link>
      </div>

      {loading && <p style={{ color: 'var(--muted)' }}>Loading…</p>}

      {!loading && datasets.length === 0 && (
        <div className="card" style={{ textAlign: 'center', padding: '56px 24px' }}>
          <Database size={40} color="var(--muted)" style={{ margin: '0 auto 16px' }} />
          <p style={{ fontWeight: 600, marginBottom: 8 }}>No datasets yet</p>
          <p style={{ color: 'var(--muted)', marginBottom: 20 }}>Upload a CSV, Excel, JSON, or Parquet file to get started.</p>
          <Link to="/upload" className="btn btn-primary">Upload your first dataset</Link>
        </div>
      )}

      {datasets.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Rows</th>
                <th>Columns</th>
                <th>Size</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {datasets.map(ds => (
                <tr key={ds.id}>
                  <td>
                    <Link to={`/datasets/${ds.id}`} style={{ fontWeight: 600, color: 'var(--text)' }}>
                      {ds.name}
                    </Link>
                    {ds.description && (
                      <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 2 }}>{ds.description}</div>
                    )}
                  </td>
                  <td style={{ fontFamily: 'var(--mono)', color: 'var(--muted)' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <Rows size={12} /> {ds.row_count.toLocaleString()}
                    </span>
                  </td>
                  <td style={{ fontFamily: 'var(--mono)', color: 'var(--muted)' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <BarChart2 size={12} /> {ds.col_count}
                    </span>
                  </td>
                  <td style={{ color: 'var(--muted)', fontFamily: 'var(--mono)' }}>{fmtBytes(ds.file_size)}</td>
                  <td style={{ color: 'var(--muted)' }}>{fmtDate(ds.created_at)}</td>
                  <td>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => handleDelete(ds.id, ds.name)}
                      style={{ color: 'var(--danger)' }}
                    >
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
