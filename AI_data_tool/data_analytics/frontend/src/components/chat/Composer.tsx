import { useEffect, useRef, type KeyboardEvent } from 'react'
import { ArrowUp, Lock } from 'lucide-react'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'

/**
 * The question box: a chat-style multi-line field that grows with its text.
 * Enter sends, Shift+Enter starts a new line; the hint under it says so, and
 * counts characters against the limit. `locked` shows the box before there
 * is anything to ask about -- visible, so the next step is obvious, but inert.
 *
 * `page` is the Ask AI page's box (step 10, Part C): the field on top, and
 * under it, inside the same frame, the key hint, the count and Send; the
 * placeholder names the data ("Ask about Demo -- Sales…"); locked, it is
 * dashed and can carry a pill saying what to do first. The limit is the same
 * 2000 either way, and the count turns to the warning colour from 1800.
 */
export const MAX_QUESTION = 2000

export default function Composer({ value, onChange, onSend, busy = false, locked, lockedHint, page }: {
  value: string
  onChange: (v: string) => void
  onSend: () => void
  busy?: boolean
  locked?: boolean
  lockedHint?: string
  page?: { name?: string; pill?: string }
}) {
  const t = useT()
  const ref = useRef<HTMLTextAreaElement>(null)

  // Grow with the text, up to ~8 lines; then scroll inside.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, page ? 168 : 200)}px`
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      if (!busy && value.trim()) onSend()
    }
  }

  const disabled = locked || busy
  const empty = !value.trim()
  const count = (
    <span className={`dl-composer__count${value.length > MAX_QUESTION * 0.9 ? ' dl-composer__count--warn' : ''}`} dir="ltr">
      {localDigits(`${value.length} / ${MAX_QUESTION}`)}
    </span>
  )
  if (page) {
    return (
      <div className={`dl-composer dl-composer--page${locked ? ' dl-composer--locked' : ''}`}>
        <div className="dl-composer__box">
          <textarea ref={ref} rows={1} value={value} maxLength={MAX_QUESTION}
            disabled={disabled}
            onChange={e => onChange(e.target.value)} onKeyDown={onKey}
            placeholder={locked ? (lockedHint ?? t('ask.lockedHint'))
              : page.name ? t('ask2.cmp.placeholder', { name: page.name }) : t('ask.placeholder')}
            aria-label={t('ask.questionLabel')}
            aria-describedby={locked ? (page.pill ? 'dl-composer-pill' : undefined) : 'dl-composer-hint'}
            className="dl-composer__input" />
          <div className="dl-composer__foot">
            {locked && page.pill && (
              <span id="dl-composer-pill" className="dl-composer__pill"><Lock size={13} aria-hidden /> {page.pill}</span>
            )}
            {!locked && (
              <span id="dl-composer-hint" className="dl-composer__keys">
                <kbd>Enter</kbd> {t('ask2.cmp.toSend')} · <kbd>Shift</kbd> + <kbd>Enter</kbd> {t('ask2.cmp.newLine')}
              </span>
            )}
            {!locked && count}
            <button type="button" className="dl-composer__send"
              onClick={() => { if (!empty) onSend() }} disabled={disabled || empty}
              aria-label={busy ? t('ask.asking') : t('ask2.cmp.send')} title={busy ? t('ask.asking') : t('ask2.cmp.send')}>
              <ArrowUp size={18} aria-hidden />
            </button>
          </div>
        </div>
      </div>
    )
  }
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
          {count}
        </div>
      )}
    </div>
  )
}
