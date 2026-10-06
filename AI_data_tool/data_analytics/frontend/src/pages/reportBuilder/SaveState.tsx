import { useEffect, useRef, useState } from 'react'
import { Check, Loader2 } from 'lucide-react'
import { formatTimeAgo, useT } from '../../i18n'

/**
 * "Saved · 2s ago" in the builder header (redesign 7e1). Every edit saves as
 * it goes; this says whether the last one has landed and when. Before any
 * save in this visit it says just "Saved".
 */
export default function SaveState({ saving }: { saving: boolean }) {
  const t = useT()
  const [at, setAt] = useState<string | null>(null)
  const was = useRef(saving)
  const [, tick] = useState(0)
  useEffect(() => {
    if (was.current && !saving) setAt(new Date().toISOString())
    was.current = saving
  }, [saving])
  // Re-read "how long ago" while it is on screen.
  useEffect(() => {
    if (!at) return
    const id = setInterval(() => tick(n => n + 1), 30_000)
    return () => clearInterval(id)
  }, [at])
  const ago = at ? formatTimeAgo(at, t) : null
  return (
    <span className="dl-bd-save" role="status" data-saving={saving || undefined}>
      {saving ? <Loader2 size={13} className="dl-spin" aria-hidden /> : <Check size={14} aria-hidden />}
      {saving ? t('status.saving') : ago ? t('bd.savedAgo', { when: ago }) : t('status.saved')}
    </span>
  )
}
