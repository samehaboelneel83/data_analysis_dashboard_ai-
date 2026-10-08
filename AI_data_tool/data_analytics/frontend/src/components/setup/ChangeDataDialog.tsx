/**
 * "Change the data" (owner request, 2026-10-08): add what a dataset left out
 * -- a listing's link, a city -- without SQL and without rebuilding the
 * dashboards on it. Tick columns, or ask in plain words; see what is added,
 * removed and a preview; confirm. The dataset is re-imported in place, so
 * its dashboards keep working, and a column they use is never removed.
 */
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { Sparkles, X } from 'lucide-react'
import { useT } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { localDigits } from '../../lib/arabicFormats'
import { useModalDialog } from '../ui/useModalDialog'
import { jobsApi, setupApi, type DataChangeOptions, type DataChangePreview } from '../../services/api'

const num = (n: number | null | undefined) => localDigits((n ?? 0).toLocaleString())

export default function ChangeDataDialog({ datasetId, datasetName, onClose, onChanged }: {
  datasetId: number; datasetName: string; onClose: () => void; onChanged: () => void
}) {
  const t = useT()
  const { language } = useDirection()
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const [opts, setOpts] = useState<DataChangeOptions | null>(null)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [message, setMessage] = useState('')
  const [preview, setPreview] = useState<DataChangePreview | null>(null)
  const [busy, setBusy] = useState<'preview' | 'apply' | null>(null)

  useEffect(() => {
    setupApi.changeOptions(datasetId).then(setOpts).catch(() => setOpts(null))
  }, [datasetId])

  async function ask(body: { add?: string[]; message?: string }) {
    setBusy('preview'); setPreview(null)
    try { setPreview(await setupApi.changePreview(datasetId, body, language)) }
    catch { setPreview({ error: t('change.failed') }) }
    finally { setBusy(null) }
  }

  async function apply() {
    if (!preview?.sql) return
    setBusy('apply')
    try {
      const { job_id } = await setupApi.changeApply(datasetId, preview.sql)
      for (let i = 0; i < 400; i++) {
        const job = await jobsApi.get(job_id)
        if (job.state === 'succeeded') { toast.success(t('change.done')); onChanged(); onClose(); return }
        if (job.state === 'failed' || job.state === 'cancelled') { toast.error(job.error ?? t('change.failed')); break }
        await new Promise(r => setTimeout(r, 1500))
      }
    } catch { toast.error(t('change.failed')) }
    setBusy(null)
  }

  const reason = opts && !opts.can_change ? opts.reason : null
  const blocked = (preview?.blocked ?? []).length > 0

  return (
    <div className="dl-modal-backdrop" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 60,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="change-title" className="card change-dialog">
        <div className="change-dialog__head">
          <h2 id="change-title">{t('change.title', { name: datasetName })}</h2>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose} aria-label={t('sdd.close')}><X size={16} /></button>
        </div>
        <p className="change-dialog__sub">{t('change.sub')}</p>

        {!opts && <p className="change-dialog__sub">{t('common.loading')}</p>}
        {reason && <p className="change-dialog__note">{t(`change.reason.${reason}` as 'change.reason.live')}</p>}

        {opts?.can_change && !preview && (
          <>
            {opts.addable.length > 0 && (
              <section aria-labelledby="change-add">
                <h3 id="change-add" className="change-dialog__h">{t('change.addTitle')}</h3>
                <ul className="change-dialog__cols">
                  {opts.addable.map(c => (
                    <li key={c.name}>
                      <label>
                        <input type="checkbox" checked={picked.has(c.name)}
                          onChange={() => setPicked(s => { const n = new Set(s); if (n.has(c.name)) n.delete(c.name); else n.add(c.name); return n })} />
                        <span>{c.name}</span>
                        {c.description && <span className="change-dialog__sub"> — {c.description}</span>}
                      </label>
                    </li>
                  ))}
                </ul>
                <button type="button" className="btn btn-primary btn-sm" disabled={!picked.size || !!busy}
                  onClick={() => ask({ add: [...picked] })}>
                  {busy === 'preview' ? t('change.checking') : t('change.previewAdd', { n: num(picked.size) })}
                </button>
              </section>
            )}
            {opts.allow_ai && (
              <form className="change-dialog__ask" onSubmit={e => { e.preventDefault(); if (message.trim()) ask({ message: message.trim() }) }}>
                <label htmlFor="change-msg" className="change-dialog__h">{t('change.askTitle')}</label>
                <div className="setup-chat__form">
                  <input id="change-msg" value={message} onChange={e => setMessage(e.target.value)} disabled={!!busy}
                    placeholder={t('change.askPh')} />
                  <button type="submit" className="btn btn-sm" disabled={!message.trim() || !!busy}>
                    <Sparkles size={13} aria-hidden="true" /> {t('change.askButton')}
                  </button>
                </div>
              </form>
            )}
            {busy === 'preview' && <p className="change-dialog__sub" aria-live="polite">{t('change.checking')}</p>}
          </>
        )}

        {preview && (
          <section aria-live="polite" className="change-dialog__preview">
            {preview.error ? (
              <>
                <p className="change-dialog__note">{t('change.couldNot')} {preview.error !== 'failed' ? preview.error : ''}</p>
                <button type="button" className="btn btn-sm" onClick={() => setPreview(null)}>{t('change.back')}</button>
              </>
            ) : (
              <>
                {preview.reply && <p className="change-dialog__sub">{preview.reply}</p>}
                <ul className="setup-facts">
                  <li>{t('change.adds', { cols: (preview.adds ?? []).join(', ') || '—' })}</li>
                  <li>{t('change.removes', { cols: (preview.removes ?? []).join(', ') || '—' })}</li>
                  <li>{t('setup.u.rowsN', { n: num(preview.test?.row_count) })}</li>
                </ul>
                {blocked && (
                  <p className="change-dialog__note">
                    {t('change.blocked', { cols: preview.blocked!.map(b => b.column).join(', ') })}
                  </p>
                )}
                {!!preview.test?.rows.length && (
                  <div className="setup-sample__scroll">
                    <table className="change-dialog__table">
                      <thead><tr>{preview.test.columns.map(c => (
                        <th key={c} scope="col" className={preview.adds?.includes(c) ? 'is-new' : undefined}>{c}</th>))}</tr></thead>
                      <tbody>{preview.test.rows.slice(0, 5).map((r, i) => (
                        <tr key={i}>{preview.test!.columns.map(c => <td key={c}>{r[c] == null || r[c] === '' ? '—' : String(r[c])}</td>)}</tr>
                      ))}</tbody>
                    </table>
                  </div>
                )}
                <p className="change-dialog__sub">{t('change.keepsDashboards')}</p>
                <div className="setup-editor__actions">
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPreview(null)} disabled={!!busy}>{t('change.back')}</button>
                  <button type="button" className="btn btn-primary btn-sm" onClick={apply} disabled={blocked || !!busy}>
                    {busy === 'apply' ? t('change.applying') : t('change.apply')}
                  </button>
                </div>
              </>
            )}
          </section>
        )}
      </div>
    </div>
  )
}
