import type { AgentPresentation } from '../../services/api'

/**
 * The ways to continue, as buttons, under a question the agent asked back.
 *
 * "i need chart" does not say what to chart, and guessing produced the two
 * pictures that started this: a column plotted against itself, and
 * thirty-three identical bars. The agent asks instead -- and an ask that
 * leaves the person to phrase the answer themselves is only half an answer,
 * so the concrete ways forward are offered here.
 *
 * Each option IS the message it sends: clicking one is exactly the same as
 * typing it, so nothing about a choice needs to be understood by this
 * component or transported back. That is what keeps the channel generic --
 * whatever asks can offer options, and it never needs a renderer of its own.
 */
export interface ChoicesPresentation {
  kind: 'choices'
  options: string[]
}

export function isChoices(p: AgentPresentation | ChoicesPresentation | null | undefined):
  p is ChoicesPresentation {
  const kind = (p as { kind?: string } | null | undefined)?.kind
  return kind === 'choices' && Array.isArray((p as ChoicesPresentation).options)
}

export default function ChoiceOptions(
  { presentation, onChoose, disabled }: {
    presentation: ChoicesPresentation
    onChoose: (option: string) => void
    disabled?: boolean
  },
) {
  const options = presentation.options.filter(o => typeof o === 'string' && o.trim())
  if (options.length === 0) return null
  return (
    <div role="group" aria-label="Ways to continue"
      style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {options.map(option => (
        <button key={option} type="button" disabled={disabled}
          onClick={() => onChoose(option)}
          style={{
            padding: '5px 10px', fontSize: 12, borderRadius: 999,
            border: '1px solid var(--border)', background: 'var(--surface)',
            color: 'var(--text)', cursor: disabled ? 'default' : 'pointer',
            opacity: disabled ? 0.5 : 1,
          }}>
          {option}
        </button>
      ))}
    </div>
  )
}
