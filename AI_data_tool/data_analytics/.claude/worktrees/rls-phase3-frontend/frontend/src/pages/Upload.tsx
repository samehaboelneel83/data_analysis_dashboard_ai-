import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { datasetsApi } from '../services/api'
import toast from 'react-hot-toast'

export default function Upload() {
  const navigate    = useNavigate()
  const [file, setFile]   = useState<File | null>(null)
  const [name, setName]   = useState('')
  const [desc, setDesc]   = useState('')
  const [busy, setBusy]   = useState(false)
  const [drag, setDrag]   = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const pickFile = (f: File) => {
    setFile(f)
    if (!name) setName(f.name.replace(/\.[^.]+$/, ''))
  }

  const submit = async () => {
    if (!file || !name) return toast.error('Please select a file and enter a name')
    setBusy(true)
    try {
      const ds = await datasetsApi.upload(file, name, desc)
      toast.success('Uploaded!')
      navigate(`/datasets/${ds.id}`)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Upload failed')
      setBusy(false)
    }
  }

  return (
    <div style={{ maxWidth: 600 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 24 }}>Upload Dataset</h1>

      {/* Drop zone */}
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) pickFile(f) }}
        style={{
          border: `2px dashed ${drag ? 'var(--accent)' : 'var(--border)'}`,
          borderRadius: 'var(--radius)', padding: '40px 20px',
          textAlign: 'center', cursor: 'pointer', marginBottom: 20,
          background: drag ? 'rgba(108,143,255,.05)' : 'var(--surface)',
          transition: 'all .2s',
        }}
      >
        <div style={{ fontSize: 36, marginBottom: 8, opacity: .5 }}>↑</div>
        {file
          ? <p style={{ color: 'var(--accent)', fontWeight: 600 }}>{file.name} ({(file.size / 1024).toFixed(1)} KB)</p>
          : <><p style={{ fontWeight: 600 }}>Drop a file here or click to browse</p>
             <p style={{ color: 'var(--muted)', fontSize: 12, marginTop: 4 }}>CSV, XLSX, JSON, Parquet — up to 100 MB</p></>
        }
        <input ref={inputRef} type="file" accept=".csv,.xlsx,.xls,.json,.parquet" style={{ display: 'none' }}
          onChange={e => { const f = e.target.files?.[0]; if (f) pickFile(f) }} />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--muted)', marginBottom: 5 }}>
            Dataset name *
          </label>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="My dataset" style={{ width: '100%' }} />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--muted)', marginBottom: 5 }}>
            Description (optional)
          </label>
          <input value={desc} onChange={e => setDesc(e.target.value)} placeholder="Short description…" style={{ width: '100%' }} />
        </div>
        <button onClick={submit} disabled={busy || !file} className="btn btn-primary" style={{ alignSelf: 'flex-start' }}>
          {busy ? 'Uploading…' : 'Upload'}
        </button>
      </div>
    </div>
  )
}
