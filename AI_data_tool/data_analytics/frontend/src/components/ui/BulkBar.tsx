import { Trash2, X } from 'lucide-react'
import { useT } from '../../i18n'

/**
 * The bar that appears while rows are selected: how many, delete them, clear
 * the selection. Sticky at the bottom of the list so it stays in reach while
 * you scroll and tick.
 */
export default function BulkBar({ count, busy, onDelete, onClear, noun }: {
  count: number
  busy?: boolean
  onDelete: () => void
  onClear: () => void
  /** Already-translated plural noun: "datasets", "dashboards". */
  noun: string
}) {
  const t = useT()
  if (count === 0) return null
  return (
    <div role="region" aria-label={t('bulk.aria')} className="dl-bulkbar">
      <span className="dl-bulkbar__count">{t('bulk.selected', { n: count, noun })}</span>
      <button type="button" className="btn btn-sm dl-bulkbar__delete" onClick={onDelete} disabled={busy}>
        <Trash2 size={14} aria-hidden /> {busy ? t('bulk.deleting') : t('bulk.delete')}
      </button>
      <button type="button" className="btn btn-ghost btn-sm" onClick={onClear} disabled={busy}>
        <X size={14} aria-hidden /> {t('bulk.clear')}
      </button>
    </div>
  )
}
