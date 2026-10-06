import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { ArrowLeftToLine, ArrowRightToLine, Plus } from 'lucide-react'
import { useT, type MessageKey } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { nonAdditiveKind } from '../../lib/semanticGuard'
import { analysisApi, type DatasetColumn } from '../../services/api'
import { typeTag, type Analysis } from '../datasetDetail/columnProfile'
import { fmtDate } from './dates'

/**
 * The dataset's columns beside the thread (redesign step 4a, AB11): grouped
 * as Groups / Numbers / Dates / Other with a value count or range, and a click
 * puts the column into the question. The counts and ranges come from the
 * dataset's saved profile when there is one; without it the panel still lists
 * the columns. Folds to a thin rail; the choice is remembered like History's.
 */

type Group = 'groups' | 'numbers' | 'dates' | 'other'
const FOLD_KEY = 'datalytics.ask.columnsFolded'
export const readColumnsFold = () => { try { return localStorage.getItem(FOLD_KEY) === '1' } catch { return false } }

function groupOf(c: DatasetColumn): Group {
  if (c.dtype === 'datetime') return 'dates'
  if (c.dtype === 'boolean' || nonAdditiveKind(c.name) === 'identifier') return 'other'
  if (c.dtype === 'numeric') return 'numbers'
  return 'groups'
}

export default function ColumnPanel({ datasetId, columns, onInsert, collapsed, onToggle, mobileOpen, onCloseMobile }: {
  datasetId: number
  columns: DatasetColumn[]
  onInsert: (name: string) => void
  collapsed: boolean
  onToggle: () => void
  mobileOpen?: boolean
  onCloseMobile?: () => void
}) {
  const t = useT()
  const [profile, setProfile] = useState<Analysis>(null)
  useEffect(() => {
    let on = true
    setProfile(null)
    Promise.resolve().then(() => analysisApi?.get?.(datasetId))
      .then(a => { if (on && a) setProfile(a) }).catch(() => {})
    return () => { on = false }
  }, [datasetId])

  const groups = useMemo(() => {
    const g: Record<Group, DatasetColumn[]> = { groups: [], numbers: [], dates: [], other: [] }
    for (const c of columns) g[groupOf(c)].push(c)
    return g
  }, [columns])

  // Numeric ranges read left to right in both languages (-15–211).
  const hint = (c: DatasetColumn): ReactNode => {
    if (nonAdditiveKind(c.name) === 'identifier') return t('askcol.identifier')
    if (c.dtype === 'boolean') return t('askcol.yesNo')
    const num = profile?.numeric?.columns?.[c.name]
    if (num && num.min != null && num.max != null) {
      // Short enough for the panel: 0–100, 1.2k–16k.
      const f = (v: number) => (Math.abs(v) >= 10000
        ? new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(v).toLowerCase()
        : Number.isInteger(v) ? String(v) : String(Math.round(v)))
      return <bdi dir="ltr">{localDigits(`${f(num.min)}–${f(num.max)}`)}</bdi>
    }
    const cat = profile?.categorical?.columns?.[c.name]
    if (cat?.n_unique != null) return t('askcol.values', { n: localDigits(String(cat.n_unique)) })
    const dt = profile?.datetime?.columns?.[c.name]
    if (dt?.min && dt?.max) {
      const m = (s: string) => fmtDate(new Date(s), { month: 'short', year: 'numeric' })
      return localDigits(`${m(dt.min)} – ${m(dt.max)}`)
    }
    return ''
  }

  const cls = ['dl-cols3']
  if (collapsed) cls.push('dl-cols3--collapsed')
  if (mobileOpen) cls.push('dl-cols3--open')
  return (
    <>
      {mobileOpen && <div className="dl-hist__scrim" onClick={onCloseMobile} aria-hidden />}
      <aside className={cls.join(' ')} aria-label={t('askcol.title', { n: localDigits(String(columns.length)) })}
        data-testid="column-panel">
        <div className="dl-cols3__head">
          {!collapsed && <span className="dl-cols3__title">{t('askcol.title', { n: localDigits(String(columns.length)) })}</span>}
          <button type="button" className="dl-hist__icon" onClick={mobileOpen ? onCloseMobile : onToggle}
            aria-expanded={!collapsed} aria-label={collapsed ? t('askcol.expand') : t('askcol.collapse')}
            title={collapsed ? t('askcol.expand') : t('askcol.collapse')}>
            {collapsed ? <ArrowLeftToLine size={16} aria-hidden className="dl-flip" /> : <ArrowRightToLine size={16} aria-hidden className="dl-flip" />}
          </button>
        </div>
        {!collapsed && (
          <div className="dl-cols3__body">
            <p className="dl-cols3__hint">{t('askcol.hint')}</p>
            {(['groups', 'numbers', 'dates', 'other'] as Group[]).filter(g => groups[g].length).map(g => (
              <section key={g} className="dl-cols3__group">
                <h3>{t(`askcol.g.${g}` as MessageKey)}</h3>
                <ul>
                  {groups[g].map(c => (
                    <li key={c.name}>
                      <button type="button" className="dl-cols3__col" onClick={() => onInsert(c.name)}
                        aria-label={t('askcol.insert', { col: c.name })} title={t('askcol.insert', { col: c.name })}>
                        <span className="dl-cols3__tag">{nonAdditiveKind(c.name) === 'identifier' ? 'ID' : typeTag(c.dtype)}</span>
                        <span className="dl-cols3__name" dir="ltr">{c.name}</span>
                        <span className="dl-cols3__meta">{hint(c)}</span>
                        <span className="dl-cols3__add" aria-hidden><Plus size={12} /> {t('askcol.insertShort')}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}
      </aside>
    </>
  )
}
