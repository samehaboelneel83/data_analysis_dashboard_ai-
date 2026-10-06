import { useEffect, useRef, type KeyboardEvent } from 'react'
import { ArrowUp, Lock } from 'lucide-react'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'

/**
 * The question box: a chat-style multi-line field that grows with its text.
 * Enter sends, Shift+Enter starts a new line; the hint under it says so, and
 * counts characters against the limit. `locked` shows the box before there
 * is anything to ask about -- visible, so the next step is obvious, but inert.
 */
export const MAX_QUESTION = 2000

export default function Composer({ value, onChange, onSend, busy = false, locked, lockedHint }: {
  value: string
  onChange: (v: string) => void
  onSend: () => void
  busy?: boolean
  locked?: boolean
  lockedHint?: string
}) {
  const t = useT()
  const ref = useRef<HTMLTextAreaElement>(null)

  // Grow with the text, up to ~8 lines; then scroll inside.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [value])

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      if (!busy && value.trim()) onSend()
    }
  }

  const disabled = locked || busy
  const empty = !value.trim()
  return (
    <div className={`dl-composer${locked ? ' dl-composer--locked' : ''}`}>
      <div className="dl-composer__box">
        {locked && <Lock size={15} className="dl-composer__lock" aria-hidden />}
        <textarea ref={ref} rows={1} value={value} maxLength={MAX_QUESTION}
          disabled={disabled}
          onChange={e => onChange(e.target.value)} onKeyDown={onKey}
          placeholder={locked ? (lockedHint ?? t('ask.lockedHint')) : t('ask.placeholder')}
          aria-label={t('ask.questionLabel')}
          aria-describedby={locked ? undefined : 'dl-composer-hint'}
          className="dl-composer__input" />
        {/* Empty is shown (dimmed), not disabled: a disabled control can't be
            focused or explained, and Send on an empty box is simply a no-op. */}
        <button type="button" className={`dl-composer__send${empty ? ' is-empty' : ''}`}
          onClick={() => { if (!empty) onSend() }} disabled={disabled}
          aria-label={busy ? t('ask.asking') : t('ask.send')} title={busy ? t('ask.asking') : t('ask.send')}>
          <ArrowUp size={18} aria-hidden />
        </button>
      </div>
      {!locked && (
        <div id="dl-composer-hint" className="dl-composer__hint">
          <span>{t('ask.enterHint')}</span>
          <span className={value.length > MAX_QUESTION * 0.9 ? 'dl-composer__count--warn' : undefined} dir="ltr">
            {localDigits(`${value.length} / ${MAX_QUESTION}`)}
          </span>
        </div>
      )}
    </div>
  )
}
