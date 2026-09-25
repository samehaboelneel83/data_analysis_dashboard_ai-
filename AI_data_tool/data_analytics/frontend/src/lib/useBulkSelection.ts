import { useCallback, useState } from 'react'
import toast from 'react-hot-toast'
import { useConfirm } from '../components/ui/ConfirmDialog'
import { useT } from '../i18n'

/**
 * Selection + confirmed bulk delete for a list of named records.
 *
 * The confirmation NAMES what will go (up to 15, then "and N more"): a count
 * alone is how the wrong twelve things get deleted. Deletes run one at a time
 * so a failure part-way reports exactly how many went, and only the ones that
 * went leave the list.
 */
export function useBulkSelection<T extends { id: number; name: string }>(opts: {
  remove: (id: number) => Promise<unknown>
  onRemoved: (ids: number[]) => void
  noun: string
}) {
  const t = useT()
  const confirm = useConfirm()
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)

  const toggle = useCallback((id: number) => setSelected(s => {
    const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n
  }), [])
  const setMany = useCallback((ids: number[], on: boolean) => setSelected(s => {
    const n = new Set(s); for (const id of ids) { if (on) n.add(id); else n.delete(id) } return n
  }), [])
  const clear = useCallback(() => setSelected(new Set()), [])

  const deleteSelected = useCallback(async (items: T[]) => {
    const chosen = items.filter(i => selected.has(i.id))
    if (chosen.length === 0) return
    const shown = chosen.slice(0, 15).map(i => `• ${i.name}`)
    if (chosen.length > 15) shown.push(`… +${chosen.length - 15}`)
    if (!await confirm({
      title: t('bulk.confirmTitle', { n: chosen.length, noun: opts.noun }),
      body: t('bulk.confirmBody', { names: shown.join('\n') }),
      confirmLabel: t('bulk.delete'),
    })) return
    setBusy(true)
    const gone: number[] = []
    for (const item of chosen) {
      try { await opts.remove(item.id); gone.push(item.id) } catch { /* counted below */ }
    }
    setBusy(false)
    opts.onRemoved(gone)
    setMany(gone, false)
    if (gone.length === chosen.length) toast.success(t('bulk.done', { n: gone.length, noun: opts.noun }))
    else toast.error(t('bulk.partial', { ok: gone.length, n: chosen.length, fail: chosen.length - gone.length }))
  }, [selected, confirm, t, opts, setMany])

  return { selected, busy, toggle, setMany, clear, deleteSelected }
}
