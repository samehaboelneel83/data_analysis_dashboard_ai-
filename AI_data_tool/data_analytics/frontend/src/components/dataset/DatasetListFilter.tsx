/**
 * The All / Certified / Mine switch and the "show test data" toggle (4.7),
 * shared by every dataset picker so a newcomer sees the same clean list
 * everywhere. Remembered per browser.
 */
import { useContext, useMemo, useState } from 'react'
import { AuthContext } from '../../contexts/AuthContext'
import { useT } from '../../i18n'
import type { Dataset } from '../../services/api'
import { cleanDatasets, type DatasetView } from '../../lib/cleanDatasets'

const KEY = 'datalytics:dataset-view'
const read = (): DatasetView => {
  try { const v = localStorage.getItem(KEY); return v === 'certified' || v === 'mine' ? v : 'all' } catch { return 'all' }
}

export function useCleanDatasets<T extends Pick<Dataset, 'name' | 'column_meta'> & { created_by?: number | null }>(list: T[]) {
  const userId = useContext(AuthContext)?.user?.id ?? null
  const [view, setViewState] = useState<DatasetView>(read)
  const [showTest, setShowTest] = useState(false)
  const setView = (v: DatasetView) => {
    setViewState(v)
    try { localStorage.setItem(KEY, v) } catch { /* per-browser nicety only */ }
  }
  const got = useMemo(() => cleanDatasets(list, view, userId, showTest), [list, view, userId, showTest])
  // A view that would show nothing falls back to all, rather than an empty picker.
  const effective = got.visible.length === 0 && view !== 'all' && list.length > 0
    ? cleanDatasets(list, 'all', userId, showTest) : got
  return { ...effective, view, setView, showTest, setShowTest, userId }
}

export default function DatasetListFilter({ state }: { state: ReturnType<typeof useCleanDatasets> }) {
  const t = useT()
  const { view, setView, certified, mine, hiddenTest, showTest, setShowTest } = state
  if (certified === 0 && mine === 0 && hiddenTest === 0 && !showTest) return null
  const pill = (v: DatasetView, label: string, n?: number, disabled?: boolean) => (
    <button key={v} type="button" role="radio" aria-checked={view === v} disabled={disabled}
      onClick={() => setView(v)}
      style={{ fontSize: 11.5, padding: '2px 9px', borderRadius: 999, cursor: disabled ? 'default' : 'pointer',
        border: '1px solid var(--border)', opacity: disabled ? 0.5 : 1,
        background: view === v ? 'var(--accent-soft, var(--surface2))' : 'transparent',
        color: view === v ? 'var(--accent)' : 'var(--text)', fontWeight: view === v ? 600 : 400 }}>
      {label}{n != null ? ` (${n})` : ''}
    </button>
  )
  return (
    <div data-testid="dataset-list-filter" style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', fontSize: 12 }}>
      <span role="radiogroup" aria-label={t('dsf.label')} style={{ display: 'inline-flex', gap: 4 }}>
        {pill('all', t('dsf.all'))}
        {pill('certified', t('dsf.certified'), certified, certified === 0)}
        {pill('mine', t('dsf.mine'), mine, mine === 0)}
      </span>
      {(hiddenTest > 0 || showTest) && (
        <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 11.5 }}
          onClick={() => setShowTest(!showTest)}>
          {showTest ? t('dsf.hideTest') : t('dsf.showTest', { n: hiddenTest })}
        </button>
      )}
    </div>
  )
}
