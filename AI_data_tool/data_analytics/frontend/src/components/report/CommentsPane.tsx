import { formatDate } from '../../lib/dateFormat'
import { useT } from '../../i18n'
import { useEffect, useState } from 'react'
import { commentsApi, type ReportComment } from '../../services/api'
import { useConfirm } from '../ui/ConfirmDialog'

/**
 * Discussion on the report: flat thread, newest last, optionally pinned to the
 * page it was written on. Posting notifies every prior participant's bell.
 */
export default function CommentsPane({ reportId, activePageId, pageNames }: {
  reportId: number
  activePageId?: number
  pageNames: Record<number, string>
}) {
  const t = useT()
  const confirm = useConfirm()
  const [comments, setComments] = useState<ReportComment[]>([])
  const [draft, setDraft] = useState('')
  const [pinToPage, setPinToPage] = useState(true)
  const [error, setError] = useState('')

  const refresh = () => commentsApi.list(reportId).then(setComments).catch(() => setComments([]))
  useEffect(() => { refresh() /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [reportId])

  const post = async () => {
    const text = draft.trim()
    if (!text) return
    setError('')
    try {
      await commentsApi.add(reportId, text, pinToPage ? activePageId : undefined)
      setDraft('')
      refresh()
    } catch { setError(t('bc.panes.comments.postFailed')) }
  }

  return (
    <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8, height: '100%' }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
        {t('builder.pane.comments')}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {comments.length === 0 && (
          <p style={{ fontSize: 11, color: 'var(--muted)' }}>{t('bc.panes.comments.empty')}</p>
        )}
        {comments.map(c => (
          <div key={c.id} style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px', fontSize: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 6, marginBottom: 2 }}>
              <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                {c.author}{c.page_id != null && pageNames[c.page_id] ? ` · ${pageNames[c.page_id]}` : ''}
              </span>
              <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>{formatDate(c.created_at)}</span>
                {c.mine && (
                  <button aria-label={t('bc.panes.comments.delete', { id: c.id })}
                    onClick={async () => {
                      // A small ✕ sitting beside the timestamp, with no undo
                      // behind it -- easy to hit while meaning to dismiss.
                      if (!await confirm({
                        title: t('bc.panes.comments.deleteTitle'),
                        body: t('bc.panes.comments.deleteBody'),
                      })) return
                      await commentsApi.delete(reportId, c.id)
                      refresh()
                    }}
                    style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--danger)', fontSize: 11, padding: 0 }}>✕</button>
                )}
              </span>
            </div>
            <div style={{ whiteSpace: 'pre-wrap' }}>{c.text}</div>
          </div>
        ))}
      </div>

      {error && <div role="alert" style={{ fontSize: 11, color: 'var(--danger)' }}>{error}</div>}
      <textarea aria-label={t('bc.panes.comments.write')} value={draft} onChange={e => setDraft(e.target.value)}
        placeholder={t('bc.panes.comments.writePh')} rows={3}
        onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void post() }}
        style={{ width: '100%', fontSize: 12, resize: 'vertical' }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <label style={{ fontSize: 11, display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
          <input type="checkbox" checked={pinToPage} onChange={e => setPinToPage(e.target.checked)} />
          {t('bc.panes.comments.pin')}
        </label>
        <button className="btn btn-primary" style={{ fontSize: 11, marginInlineStart: 'auto' }}
          disabled={!draft.trim()} title={!draft.trim() ? t('bc.panes.comments.writeFirst') : undefined} onClick={() => void post()}>{t('bc.panes.comments.post')}</button>
      </div>
    </div>
  )
}
