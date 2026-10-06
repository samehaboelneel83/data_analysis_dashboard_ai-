import { useMemo, useState, type ReactNode } from 'react'
import { ArrowRight, Database, Plug, Search } from 'lucide-react'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import type { AgentConversation, Dataset } from '../../services/api'
import { sourceWords, typeName } from '../datasetsList/classify'
import type { PickerItem } from './DataPicker'

/**
 * "What do you want to ask about?" (redesign 4b, no dataset chosen): a
 * search, the data recently asked about (from the conversations' targets,
 * AB9), then every dataset and every connection.
 */
export default function DataChooser({ datasets, sources, conversations, onChoose, footer }: {
  datasets: Dataset[]
  sources: PickerItem[]
  conversations: AgentConversation[]
  onChoose: (key: string) => void
  footer?: ReactNode
}) {
  const t = useT()
  const [q, setQ] = useState('')
  const n = (v: number) => localDigits(v.toLocaleString('en-US'))

  // Conversations per scope key, and the newest conversation per key.
  const { count, newest } = useMemo(() => {
    const count = new Map<string, number>()
    const newest = new Map<string, number>()
    for (const c of conversations) {
      const key = c.data_source_id != null ? `s:${c.data_source_id}`
        : (c.dataset_ids ?? []).length === 1 ? `d:${c.dataset_ids![0]}` : null
      if (!key) continue
      count.set(key, (count.get(key) ?? 0) + 1)
      newest.set(key, Math.max(newest.get(key) ?? 0, c.id))
    }
    return { count, newest }
  }, [conversations])

  const match = (name: string) => !q.trim() || name.toLowerCase().includes(q.trim().toLowerCase())
  const dsMeta = (d: Dataset) => [
    sourceWords(d, null, t),
    t('ask3.rowsCols', { rows: n(d.row_count ?? 0), cols: n(d.col_count ?? d.columns?.length ?? 0) }),
  ].join(' · ')
  const srcMeta = (s: PickerItem) => [typeName(s.sourceType), t('nods.acrossTables')].filter(Boolean).join(' · ')
  const convs = (key: string) => {
    const c = count.get(key) ?? 0
    return c === 0 ? null : c === 1 ? t('nods.conv') : t('nods.convs', { n: n(c) })
  }

  const all = [
    ...datasets.map(d => ({ key: `d:${d.id}`, name: d.name, meta: dsMeta(d), kind: 'dataset' as const })),
    ...sources.map(s => ({ key: s.key, name: s.name, meta: srcMeta(s), kind: 'source' as const })),
  ].filter(x => match(x.name))
  const recent = all.filter(x => newest.has(x.key))
    .sort((a, b) => (newest.get(b.key)! - newest.get(a.key)!)).slice(0, 3)
  const rest = all.filter(x => !recent.includes(x))
  const restDs = rest.filter(x => x.kind === 'dataset')
  const restSrc = rest.filter(x => x.kind === 'source')

  const Icon = ({ kind }: { kind: 'dataset' | 'source' }) => (
    <span className={`dl-choose__icon dl-choose__icon--${kind}`} aria-hidden>
      {kind === 'dataset' ? <Database size={16} /> : <Plug size={16} />}
    </span>
  )

  return (
    <section className="dl-choose" aria-labelledby="dl-choose-title">
      <h1 id="dl-choose-title" className="dl-choose__title">{t('nods.title')}</h1>
      <p className="dl-choose__sub">{t('nods.sub')}</p>
      <label className="dl-choose__search">
        <Search size={15} aria-hidden />
        <input id="dl-choose-search" type="search" value={q} onChange={e => setQ(e.target.value)}
          placeholder={t('nods.search')} aria-label={t('nods.search')} />
      </label>
      {recent.length > 0 && (
        <>
          <h2 className="dl-choose__label">{t('nods.recent')}</h2>
          <ul className="dl-choose__recent">
            {recent.map(x => (
              <li key={x.key}>
                <button type="button" className="dl-choose__row" onClick={() => onChoose(x.key)}>
                  <Icon kind={x.kind} />
                  <span className="dl-choose__text">
                    <strong dir="auto">{x.name}</strong>
                    <span>{x.meta}</span>
                  </span>
                  {convs(x.key) && <span className="dl-choose__count">{convs(x.key)}</span>}
                  <ArrowRight size={15} aria-hidden className="dl-flip dl-choose__go" />
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {(restDs.length > 0 || restSrc.length > 0) && (
        <div className="dl-choose__cols">
          {restDs.length > 0 && (
            <div>
              <h2 className="dl-choose__label">{t('nods.all')}</h2>
              <ul className="dl-choose__grid">
                {restDs.map(x => (
                  <li key={x.key}>
                    <button type="button" className="dl-choose__card" onClick={() => onChoose(x.key)}>
                      <strong dir="auto">{x.name}</strong><span>{x.meta}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {restSrc.length > 0 && (
            <div>
              <h2 className="dl-choose__label">{t('nods.connections')}</h2>
              <ul className="dl-choose__grid">
                {restSrc.map(x => (
                  <li key={x.key}>
                    <button type="button" className="dl-choose__card dl-choose__card--src" onClick={() => onChoose(x.key)}>
                      <Icon kind="source" />
                      <span className="dl-choose__text"><strong dir="auto">{x.name}</strong><span>{x.meta}</span></span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {all.length === 0 && <p className="dl-choose__none">{t('nods.none')}</p>}
      {footer}
    </section>
  )
}
