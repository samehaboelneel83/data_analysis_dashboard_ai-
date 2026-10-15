import { useEffect, useState } from 'react'
import { useT } from '../../i18n'
import { choiceLight, effectiveChoice } from '../../components/LlmPicker'
import { getLlmChoice, lastLlmEndpoints, LLM_CHOICE_EVENT, LLM_ENDPOINTS_EVENT } from '../../services/api'

/**
 * Is the model this person's questions go to unreachable? (redesign 4b, AB4)
 *
 * Read from the answers to the top bar's own `/llm/endpoints` poll, which
 * `llmApi.endpoints` broadcasts -- no second poller. Offline is exactly what
 * the top-bar light shows as red: `choiceLight(...) === 'down'`. `checkedAt`
 * is when that answer arrived, for "Checked 20 s ago".
 */
export function useAiOffline(): { offline: boolean; checkedAt: number | null } {
  const [seen, setSeen] = useState(lastLlmEndpoints)
  const [picked, setPicked] = useState(getLlmChoice)
  useEffect(() => {
    const onSeen = (e: Event) => setSeen((e as CustomEvent<ReturnType<typeof lastLlmEndpoints>>).detail)
    const onChoice = (e: Event) => setPicked((e as CustomEvent<string | null>).detail ?? null)
    window.addEventListener(LLM_ENDPOINTS_EVENT, onSeen)
    window.addEventListener(LLM_CHOICE_EVENT, onChoice)
    return () => {
      window.removeEventListener(LLM_ENDPOINTS_EVENT, onSeen)
      window.removeEventListener(LLM_CHOICE_EVENT, onChoice)
    }
  }, [])
  if (!seen) return { offline: false, checkedAt: null }
  return { offline: choiceLight(seen.data, effectiveChoice(seen.data, picked)) === 'down', checkedAt: seen.at }
}

/**
 * The one AI gate for buttons that start model work (AD-01): `offline` from
 * the same broadcast as `useAiOffline`, plus the sentence to show as the
 * disabled control's title. A trigger either gets `disabled={offline}` with
 * `title={reason}`, or goes straight to its no-AI path.
 */
export function useAiGate(): { offline: boolean; reason: string | undefined } {
  const { offline } = useAiOffline()
  const t = useT()
  return { offline, reason: offline ? t('off.composer') : undefined }
}
