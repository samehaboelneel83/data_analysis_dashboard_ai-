import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, Star } from 'lucide-react'
import toast from 'react-hot-toast'
import { portalApi, type Catalog, type CatalogItem, type CatalogSection, type Facet, type PortalDelivery } from '../services/api'
import { formatTimeAgo, useT, type MessageKey } from '../i18n'
import { localDigits } from '../lib/arabicFormats'
import './portal/portal.css'

/**
 * The reader's portal: every dashboard this person may open, and nothing
 * else, in sections (made by me, shared with me, my team, favourites,
 * recently opened), searched and filtered, one page at a time.
 *
 * The server builds the list from what the person may open and offers only
 * the categories, tags and owners found among those, so nothing here can
 * reveal a dashboard by its name or by a filter value. Rows are light (no
 * pages or widgets): a dashboard's content is fetched when it is opened.
 */

type Section = CatalogSection | 'sent'
const SECTIONS: Section[] = ['all', 'mine', 'shared', 'team', 'favorites', 'recent', 'archived', 'sent']
const PAGE = 24
const EMPTY: Partial<Record<Section, MessageKey>> = {
  shared: 'pub.empty.shared', team: 'pub.empty.shared', favorites: 'pub.empty.favorites', recent: 'pub.empty.recent',
}

export default function Portal() {
  const t = useT()
  const [section, setSection] = useState<Section>('all')
  const [query, setQuery] = useState('')
  const [asked, setAsked] = useState('')            // the query after a short pause in typing
  const [category, setCategory] = useState('')
  const [tag, setTag] = useState('')
  const [owner, setOwner] = useState('')
  const [items, setItems] = useState<CatalogItem[] | null>(null)
  const [total, setTotal] = useState(0)
  const [counts, setCounts] = useState<Catalog['counts'] | null>(null)
  const [failed, setFailed] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [facets, setFacets] = useState<{ categories: Facet[]; tags: Facet[]; owners: Facet[] } | null>(null)
  const [sent, setSent] = useState<PortalDelivery[] | null>(null)
  const turn = useRef(0)                           // an older answer never replaces a newer one

  useEffect(() => { const id = window.setTimeout(() => setAsked(query.trim()), 250); return () => window.clearTimeout(id) }, [query])
  useEffect(() => { portalApi.facets().then(setFacets).catch(() => setFacets({ categories: [], tags: [], owners: [] })) }, [])

  const fetchPage = (offset: number) => {
    if (section === 'sent') return
    const mine = ++turn.current
    if (offset === 0) setItems(null); else setLoadingMore(true)
    portalApi.catalog({ section, q: asked || undefined, category: category || undefined, tag: tag || undefined, owner: owner || undefined, limit: PAGE, offset })
      .then(got => {
        if (mine !== turn.current) return
        setItems(prev => offset === 0 ? got.items : [...(prev ?? []), ...got.items])
        setTotal(got.total); setCounts(got.counts); setFailed(false)
      })
      .catch(() => { if (mine === turn.current) { setFailed(true); if (offset === 0) setItems([]) } })
      .finally(() => { if (mine === turn.current) setLoadingMore(false) })
  }
  useEffect(() => { fetchPage(0) }, [section, asked, category, tag, owner])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (section !== 'sent' || sent) return
    portalApi.deliveries().then(setSent).catch(() => setSent([]))
  }, [section, sent])

  const toggleFavorite = async (item: CatalogItem) => {
    const on = !item.favorite
    setItems(prev => (prev ?? []).map(x => x.id === item.id ? { ...x, favorite: on } : x))
    setCounts(prev => prev ? { ...prev, favorites: Math.max(0, prev.favorites + (on ? 1 : -1)) } : prev)
    try { await portalApi.favorite(item.id, on) }
    catch {
      setItems(prev => (prev ?? []).map(x => x.id === item.id ? { ...x, favorite: !on } : x))
      setCounts(prev => prev ? { ...prev, favorites: Math.max(0, prev.favorites + (on ? -1 : 1)) } : prev)
      toast.error(t('pub.failed'))
    }
  }

  const filtered = !!(asked || category || tag || owner)
  const clear = () => { setQuery(''); setCategory(''); setTag(''); setOwner('') }
  const when = (iso: string | null) => (iso ? formatTimeAgo(iso, t) : null)
  const facetSelect = (label: MessageKey, value: string, set: (v: string) => void, options: Facet[] | undefined) => (
    !!options?.length && (
      <select className="ptl-sel" value={value} onChange={e => set(e.target.value)} aria-label={t(label)}>
        <option value="">{t(label)}: {t('pub.filter.any')}</option>
        {options.map(o => <option key={o.value} value={o.value}>{o.value} ({localDigits(String(o.count))})</option>)}
      </select>
    )
  )

  return (
    <div className="ptl">
      <div className="ptl-h"><h1>{t('pub.portal.title')}</h1><p>{t('pub.portal.sub')}</p></div>

      <div className="ptl-tabs" role="tablist">
        {SECTIONS.map(s => {
          const n = s === 'sent' ? null : counts?.[s]
          if (s === 'archived' && !n) return null     // shown only to someone who has archived dashboards
          return (
            <button key={s} type="button" role="tab" className="ptl-tab" aria-selected={section === s} onClick={() => setSection(s)}>
              {t(`pub.sec.${s}` as MessageKey)}{n != null && <span className="n">{localDigits(String(n))}</span>}
            </button>
          )
        })}
      </div>

      {section === 'sent' ? (
        <div role="tabpanel">
          <p className="ptl-count">{t('pub.sent.help')}</p>
          {sent === null && <div className="ptl-skel" aria-busy="true" />}
          {sent?.length === 0 && <div className="ptl-state">{t('pub.sent.empty')}</div>}
          {!!sent?.length && (
            <ul className="ptl-sent">
              {sent.map(d => (
                <li key={d.id}>
                  <span className="tx"><b dir="auto"><Link to={`/reports/${d.report_id}`}>{d.report}</Link></b>
                    <span>{[when(d.at), d.format !== 'none' ? d.format.toUpperCase() : null, d.status !== 'ok' ? d.error : null].filter(Boolean).join(' · ')}</span>
                  </span>
                  <span className={d.status === 'ok' ? 'ptl-ok' : 'ptl-er'}>{t(d.status === 'ok' ? 'pub.sent.ok' : 'pub.sent.error')}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div role="tabpanel">
          <div className="ptl-bar">
            <label className="ptl-search"><Search size={16} aria-hidden />
              <input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder={t('pub.search')} aria-label={t('pub.search')} dir="auto" />
            </label>
            {facetSelect('pub.filter.category', category, setCategory, facets?.categories)}
            {facetSelect('pub.filter.tag', tag, setTag, facets?.tags)}
            {facetSelect('pub.filter.owner', owner, setOwner, facets?.owners)}
            {filtered && <button type="button" className="ptl-lk" onClick={clear}>{t('pub.filter.clear')}</button>}
          </div>

          {items === null && <div className="ptl-grid" aria-busy="true">{[0, 1, 2, 3, 4, 5].map(i => <div key={i} className="ptl-skel" />)}</div>}
          {items !== null && failed && (
            <div className="ptl-state" role="alert">{t('pub.error')}<br />
              <button type="button" className="btn btn-primary" onClick={() => fetchPage(0)}>{t('pub.retry')}</button>
            </div>
          )}
          {items !== null && !failed && items.length === 0 && (
            <div className="ptl-state">{t(filtered ? 'pub.empty.search' : EMPTY[section] ?? 'pub.empty')}</div>
          )}
          {!!items?.length && !failed && (<>
            <p className="ptl-count" aria-live="polite">{t('pub.count', { n: localDigits(String(total)) })}</p>
            <div className="ptl-grid" data-testid="portal-grid">
              {items.map(item => (
                <article key={item.id} className="ptl-card">
                  <button type="button" className="ptl-fav" aria-pressed={item.favorite} onClick={() => void toggleFavorite(item)}
                    aria-label={t(item.favorite ? 'pub.fav.remove' : 'pub.fav.add', { name: item.name })}>
                    <Star size={17} aria-hidden fill={item.favorite ? 'currentColor' : 'none'} />
                  </button>
                  <h2 dir="auto"><Link to={`/reports/${item.id}`} aria-label={t('pub.open', { name: item.name })}>{item.name}</Link></h2>
                  {item.description && <p className="ptl-desc" dir="auto">{item.description}</p>}
                  <div className="ptl-chips">
                    {item.category && <span className="ptl-chip cat" dir="auto">{item.category}</span>}
                    {item.tags.slice(0, 4).map(x => <span key={x} className="ptl-chip" dir="auto">{x}</span>)}
                    <span className="ptl-chip">{t(`pub.via.${item.via}` as MessageKey)}</span>
                    {item.state !== 'published' && <span className="ptl-chip">{t(`pub.state.${item.state}` as MessageKey)}</span>}
                    {!item.can_export && <span className="ptl-chip warn">{t('pub.noDownloads')}</span>}
                  </div>
                  <div className="ptl-meta">
                    {item.owner && !item.is_mine && <span dir="auto">{t('pub.by', { who: item.owner })}</span>}
                    {item.data_as_of && <span>{t('pub.dataAsOf', { when: when(item.data_as_of) ?? '' })}</span>}
                    {section === 'recent' && item.last_viewed
                      ? <span>{t('pub.viewed', { when: when(item.last_viewed) ?? '' })}</span>
                      : item.published_at && <span>{t('pub.publishedOn', { when: when(item.published_at) ?? '' })}</span>}
                  </div>
                </article>
              ))}
            </div>
            {items.length < total && (
              <div className="ptl-more">
                <button type="button" className="btn btn-ghost" style={{ border: '1px solid var(--mc-border-strong)' }} disabled={loadingMore}
                  onClick={() => fetchPage(items.length)}>{t('pub.more')}</button>
              </div>
            )}
          </>)}
        </div>
      )}
    </div>
  )
}
