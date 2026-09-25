import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { datasetsApi } from '../services/api'
import type { BatchUploadItem, BatchUploadMode } from '../services/api'
import toast from 'react-hot-toast'
import { useT } from '../i18n'
import LoadingState from '../components/ui/LoadingState'
import { FileUp, UploadCloud } from 'lucide-react'

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
  // A synchronous lock: `busy` is React state and does not change until the
  // next render, so two clicks in the same tick both passed the check and
  // uploaded the file twice.
  const inFlight = useRef(false)
  // Whether the person typed the name themselves. An auto-generated name
  // follows the chosen file; a typed one is theirs to keep.
  const nameTyped = useRef(false)

  const pickFiles = (picked: File[]) => {
    if (!picked.length) return
    setFiles(picked)
    setErrors([])
    // With several files the server appends each file's own stem, so what
    // belongs here is the prefix they share, not the first file's whole name.
    if (!nameTyped.current) setName(batchBaseName(picked))
  }

  const submit = async () => {
    if (inFlight.current) return
    if (!files.length || !name) return toast.error(t('upload.needFile'))
    inFlight.current = true
    setBusy(true)
    setErrors([])
    try {
      // One ordinary file keeps the original single-upload path, so the
      // straight-to-the-dataset flow people already know is untouched. An
      // Access file goes to the batch endpoint even on its own, because it
      // yields one dataset per table.
      if (files.length === 1 && !isAccess(files[0])) {
        const ds = await datasetsApi.upload(files[0], name, desc)
        toast.success(t('upload.done'))
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
        toast.error(typeof detail === 'string' ? detail : t('upload.failed'))
      }
      setBusy(false)
    } finally {
      inFlight.current = false
    }
  }

  const many = files.length > 1

  return (
    <div>
      <div className="dl-upload">
      <h1 className="dl-page-title" style={{ marginBottom: 4 }}>{t('upload.title')}</h1>
      <p className="dl-page-head__sub" style={{ marginBottom: 24 }}>
        {t('upload.subtitle')}
      </p>

      {/* Drop zone */}
      {/* A real button to the keyboard and to a screen reader: it was a bare
          div with a click handler, so the only way to pick a file without a
          mouse was not to have one. */}
      <div
        role="button" tabIndex={0}
        aria-label={t('upload.choose')}
        className={`dl-dropzone${drag ? ' dl-dropzone--over' : ''}${files.length ? ' dl-dropzone--has' : ''}`}
        onClick={() => inputRef.current?.click()}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); inputRef.current?.click() } }}
        onDragOver={e => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); pickFiles(Array.from(e.dataTransfer.files)) }}
      >
        <span className="dl-dropzone__icon" aria-hidden>
          {files.length ? <FileUp size={22} /> : <UploadCloud size={22} />}
        </span>
        {files.length === 1
          ? <p className="dl-dropzone__title dl-dropzone__title--file">{files[0].name} ({(files[0].size / 1024).toFixed(1)} KB)</p>
          : files.length > 1
          ? <p className="dl-dropzone__title dl-dropzone__title--file">
              {t('upload.nFiles', { n: files.length, size: (files.reduce((n, f) => n + f.size, 0) / 1024 / 1024).toFixed(1) })}
            </p>
          : <><p className="dl-dropzone__title">{t('upload.drop')}</p>
             <p className="dl-dropzone__hint">
               {t('upload.formats')}
             </p></>
        }
        {files.length > 0 && <p className="dl-dropzone__hint">{t('upload.chooseOther')}</p>}
        <input ref={inputRef} type="file" accept={ACCEPT} multiple style={{ display: 'none' }}
          onChange={e => pickFiles(Array.from(e.target.files ?? []))} />
      </div>

      {files.some(isAccess) && (
        <p style={{ color: 'var(--muted)', fontSize: 12, marginBottom: 14 }}>
          An Access database becomes <strong>one dataset per table</strong>. Encrypted
          files cannot be read — save an unencrypted copy first.
        </p>
      )}

      <div className="card dl-upload__form">
        {many && (
          <div>
            <div className="dl-field__label" style={{ marginBottom: 6 }}>
              {t('upload.become')}
            </div>
            <label style={{ display: 'block', fontSize: 13, marginBottom: 4 }}>
              <input type="radio" name="mode" value="separate" checked={mode === 'separate'}
                     onChange={() => setMode('separate')} style={{ marginInlineEnd: 6 }} />
              {t('upload.separate')}
            </label>
            <label style={{ display: 'block', fontSize: 13 }}>
              <input type="radio" name="mode" value="append" checked={mode === 'append'}
                     onChange={() => setMode('append')} style={{ marginInlineEnd: 6 }} />
              {t('upload.append')}
            </label>
          </div>
        )}
        <div>
          <label className="dl-field" style={{ marginBottom: 0 }}>
            <span className="dl-field__label">{t('upload.name')}</span>
            <input value={name} onChange={e => { nameTyped.current = e.target.value.trim().length > 0; setName(e.target.value) }} maxLength={120} placeholder={t('upload.namePh')} className="dl-field__input" />
          </label>
          {many && mode === 'separate' && (
            <p style={{ color: 'var(--muted)', fontSize: 11, marginTop: 4 }}>
              Each file's own name is added, e.g. “{name || 'My dataset'} — {files[0].name.replace(/\.[^.]+$/, '')}”.
            </p>
          )}
        </div>
        <label className="dl-field" style={{ marginBottom: 0 }}>
          <span className="dl-field__label">{t('upload.desc')}</span>
          <input value={desc} onChange={e => setDesc(e.target.value)} placeholder={t('upload.descPh')} className="dl-field__input" />
        </label>
        <button onClick={submit} disabled={busy} className="btn btn-primary" style={{ alignSelf: 'flex-start' }}>
          {busy ? t('upload.uploading') : t('upload.upload')}
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
        <div role="alert" className="dl-upload__errors">
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
