import { useCallback, useEffect, useState } from 'react'
import { useT, type MessageKey } from '../../i18n'
import { takeawayText } from '../../lib/readbackText'
import { discoveryApi, type PageTakeaway, type PageTakeaways as Result } from '../../services/api'

/**
 * This page's key takeaways (docs/discovery/PLAN.md, phase 2 #16).
 *
 * Each line is one chart's own result read back as a sentence by the server
 * (services/discovery/takeaways.py) -- computed as THIS reader sees the page,
 * with no model. So it works with AI off, and it cannot say anything a chart
 * on the page does not show.
 */
const SECTIONS: PageTakeaway['section'][] = ['headline', 'over_time', 'comparison', 'spread', 'where', 'together', 'other']

export default function PageTakeaways({ reportId, pageId }: { reportId: number; pageId: number }) {
  const t = useT()
  const [data, setData] = useState<Result | null>(null)
  const [failed, setFailed] = useState(false)

  const load = useCallback(() => {
    setFailed(false)
    setData(null)
    discoveryApi.takeaways(reportId, pageId).then(setData).catch(() => setFailed(true))
  }, [reportId, pageId])
  useEffect(() => { load() }, [load])

  if (failed) {
    return (
      <div role="alert" style={{ padding: 12, fontSize: 13 }}>
        {t('tk.failed')} <button type="button" className="btn btn-sm" onClick={load}>{t('tk.retry')}</button>
      </div>
    )
  }
  if (!data) return <p style={{ padding: 12, fontSize: 13, color: 'var(--muted)' }} aria-busy="true">{t('tk.loading')}</p>
  if (!data.takeaways.length) return <p style={{ padding: 12, fontSize: 13, color: 'var(--muted)' }}>{t('tk.empty')}</p>

  return (
    <div data-testid="page-takeaways" style={{ padding: '8px 12px', fontSize: 13 }}>
      {SECTIONS.filter(sec => data.takeaways.some(x => x.section === sec)).map(sec => (
        <section key={sec} style={{ marginBottom: 12 }}>
          <h3 style={{ fontSize: 12, fontWeight: 650, margin: '0 0 4px', color: 'var(--muted)' }}>
            {t(`tk.sec.${sec}` as MessageKey)}
          </h3>
          <ul style={{ margin: 0, paddingInlineStart: 18 }}>
            {data.takeaways.filter(x => x.section === sec).map(x => (
              <li key={x.widget_id} style={{ marginBottom: 6 }} dir="auto">
                {/* In the reader's language when the server sent the sentence as a key. */}
                <span>{takeawayText(t, { takeaway: x.sentence, takeaway_i18n: x.sentence_i18n }) ?? x.sentence}</span>
                <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                  <bdi>{x.title}</bdi>{x.sampled ? ` · ${t('tk.sampled')}` : ''}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
      {data.left_out > 0 && <p style={{ fontSize: 11, color: 'var(--muted)' }}>{t('tk.leftOut', { n: data.left_out })}</p>}
      <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0 }}>{t('tk.note')}</p>
    </div>
  )
}
