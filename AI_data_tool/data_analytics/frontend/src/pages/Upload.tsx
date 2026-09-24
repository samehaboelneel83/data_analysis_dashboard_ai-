import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { datasetsApi } from '../services/api'
import type { BatchUploadItem, BatchUploadMode } from '../services/api'
import toast from 'react-hot-toast'
import { useT } from '../i18n'
import LoadingState from '../components/ui/LoadingState'

const ACCEPT = '.csv,.xlsx,.xls,.json,.xml,.parquet,.mdb,.accdb'
const ACCESS_RE = /\.(mdb|accdb)$/i

const isAccess = (f: File) => ACCESS_RE.test(f.name)

const stemOf = (f: File) => f.name.replace(/\.[^.]+$/, '')

/**
 * The base name a batch of files suggests.
 *
 * The server appends each file's OWN stem to this base, so seeding it with the
 * first file's whole stem duplicates that stem in one of the names:
 * `qa_sample.csv` + `qa_sample2.csv` produced "qa_sample \u2014 qa_sample".
 * What the files genuinely share is their common prefix, and that is exactly
 * the part the server's suffix is meant to hang off.
 *
 * Trailing separators are trimmed so the prefix does not read as an unfinished
 * word, and a prefix too short to identify anything (a single letter) is
 * discarded in favour of the first stem: a slightly redundant name beats a
 * cryptic one.
 */
export const batchBaseName = (picked: File[]): string => {
  const stems = picked.map(stemOf)
  if (stems.length < 2) return stems[0] ?? ''
  let i = 0
  while (i < stems[0].length && stems.every(s => s[i] === stems[0][i])) i++
  const prefix = stems[0].slice(0, i).replace(/[\s._-]+$/, '')
  return prefix.length >= 2 ? prefix : stems[0]
}

export default function Upload() {
  const t = useT()
  const navigate    = useNavigate()
  const [files, setFiles] = useState<File[]>([])
  const [name, setName]   = useState('')
  const [desc, setDesc]   = useState('')
  const [mode, setMode]   = useState<BatchUploadMode>('separate')
  const [busy, setBusy]   = useState(false)
  const [drag, setDrag]   = useState(false)
  const [errors, setErrors] = useState<BatchUploadItem[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  const pickFiles = (picked: File[]) => {
    if (!picked.length) return
    setFiles(picked)
    setErrors([])
    // With several files the server appends each file's own stem, so what
    // belongs here is the prefix they share, not the first file's whole name.
    if (!name) setName(batchBaseName(picked))
  }

  const submit = async () => {
    if (!files.length || !name) return toast.error('Please select a file and enter a name')
    setBusy(true)
    setErrors([])
    try {
      // One ordinary file keeps the original single-upload path, so the
      // straight-to-the-dataset flow people already know is untouched. An
      // Access file goes to the batch endpoint even on its own, because it
      // yields one dataset per table.
      if (files.length === 1 && !isAccess(files[0])) {
        const ds = await datasetsApi.upload(files[0], name, desc)
        toast.success('Uploaded!')
        navigate(`/datasets/${ds.id}`)
        return
      }

      const res = await datasetsApi.uploadBatch(files, name, desc, mode)
      const failures = res.items.filter(i => i.status === 'error')
      setErrors(failures)

      if (failures.length) {
        // Deliberately no navigation: leaving the page would take the only
        // record of which files failed, and why, with it.
        toast.error(`${res.created} uploaded, ${res.failed} failed`)
        setBusy(false)
        return
      }

      toast.success(`Uploaded ${res.created} dataset${res.created === 1 ? '' : 's'}`)
      const only = res.items[0]?.dataset
      navigate(res.created === 1 && only ? `/datasets/${only.id}` : '/datasets')
    } catch (e: any) {
      // A total failure comes back as the same body under `detail`.
      const detail = e?.response?.data?.detail
      if (detail?.items) {
        setErrors(detail.items.filter((i: BatchUploadItem) => i.status === 'error'))
        toast.error(`Nothing could be uploaded (${detail.failed} failed)`)
      } else {
        toast.error(typeof detail === 'string' ? detail : 'Upload failed')
      }
      setBusy(false)
    }
  }

  const many = files.length > 1

  return (
    <div>
      <div style={{ maxWidth: 600 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 24 }}>{t('upload.title')}</h1>

      {/* Drop zone */}
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); pickFiles(Array.from(e.dataTransfer.files)) }}
        style={{
          border: `2px dashed ${drag ? 'var(--accent)' : 'var(--border)'}`,
          borderRadius: 'var(--radius)', padding: '40px 20px',
          textAlign: 'center', cursor: 'pointer', marginBottom: 20,
          background: drag ? 'color-mix(in srgb, var(--accent) 5%, transparent)' : 'var(--surface)',
          transition: 'all .2s',
        }}
      >
        <div style={{ fontSize: 36, marginBottom: 8, opacity: .5 }}>↑</div>
        {files.length === 1
          ? <p style={{ color: 'var(--accent)', fontWeight: 600 }}>{files[0].name} ({(files[0].size / 1024).toFixed(1)} KB)</p>
          : files.length > 1
          ? <p style={{ color: 'var(--accent)', fontWeight: 600 }}>
              {files.length} files ({(files.reduce((n, f) => n + f.size, 0) / 1024 / 1024).toFixed(1)} MB)
            </p>
          : <><p style={{ fontWeight: 600 }}>Drop files here or click to browse</p>
             <p style={{ color: 'var(--muted)', fontSize: 12, marginTop: 4 }}>
               CSV, XLSX, JSON, XML, Parquet, Access (MDB/ACCDB) — several at once
             </p></>
        }
        <input ref={inputRef} type="file" accept={ACCEPT} multiple style={{ display: 'none' }}
          onChange={e => pickFiles(Array.from(e.target.files ?? []))} />
      </div>

      {files.some(isAccess) && (
        <p style={{ color: 'var(--muted)', fontSize: 12, marginBottom: 14 }}>
          An Access database becomes <strong>one dataset per table</strong>. Encrypted
          files cannot be read — save an unencrypted copy first.
        </p>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {many && (
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--muted)', marginBottom: 5 }}>
              These files should become
            </label>
            <label style={{ display: 'block', fontSize: 13, marginBottom: 4 }}>
              <input type="radio" name="mode" value="separate" checked={mode === 'separate'}
                     onChange={() => setMode('separate')} style={{ marginInlineEnd: 6 }} />
              Separate datasets — one per file
            </label>
            <label style={{ display: 'block', fontSize: 13 }}>
              <input type="radio" name="mode" value="append" checked={mode === 'append'}
                     onChange={() => setMode('append')} style={{ marginInlineEnd: 6 }} />
              A single dataset — rows appended together
            </label>
          </div>
        )}
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--muted)', marginBottom: 5 }}>
            Dataset name *
          </label>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="My dataset" style={{ width: '100%' }} />
          {many && mode === 'separate' && (
            <p style={{ color: 'var(--muted)', fontSize: 11, marginTop: 4 }}>
              Each file's own name is added, e.g. “{name || 'My dataset'} — {files[0].name.replace(/\.[^.]+$/, '')}”.
            </p>
          )}
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--muted)', marginBottom: 5 }}>
            Description (optional)
          </label>
          <input value={desc} onChange={e => setDesc(e.target.value)} placeholder="Short description…" style={{ width: '100%' }} />
        </div>
        <button onClick={submit} disabled={busy} className="btn btn-primary" style={{ alignSelf: 'flex-start' }}>
          {busy ? 'Uploading…' : 'Upload'}
        </button>
        {busy && (
          // The button label alone is easy to miss on a large file -- a
          // multi-hundred-MB upload or an Access file with many tables can sit
          // here for a while, and a disabled button gives no sense that
          // anything is still happening versus having silently stalled.
          <LoadingState label={`Uploading and processing your ${many ? 'files' : 'file'}…`} />
        )}
      </div>

      {errors.length > 0 && (
        <div style={{ marginTop: 20, border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 14 }}>
          <p style={{ fontWeight: 600, marginBottom: 8 }}>
            {errors.length} file{errors.length === 1 ? '' : 's'} could not be uploaded
          </p>
          <ul style={{ margin: 0, paddingInlineStart: 18 }}>
            {errors.map((e, i) => (
              <li key={i} style={{ fontSize: 12, marginBottom: 4 }}>
                <strong>{e.source_filename}</strong> — {e.error}
              </li>
            ))}
          </ul>
        </div>
      )}
      </div>
    </div>
  )
}
