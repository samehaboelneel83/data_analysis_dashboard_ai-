/**
 * E11: what to tell a person whose question was refused by a limit.
 *
 * Ask AI and the copilot said "Could not reach the agent" for every failure,
 * so an org that had used its AI budget (or its daily questions) looked like
 * an outage, and people retried into the same refusal. A 429 is a limit, not
 * a fault: this says so, and when it resets, from the response's Retry-After.
 */
import type { TranslateFn } from '../i18n'
import { localDigits } from './arabicFormats'

interface HttpError { response?: { status?: number; headers?: Record<string, string | undefined> } }

/** The message for a refused request, or null when it was not a limit. */
export function aiLimitMessage(err: unknown, t: TranslateFn): string | null {
  const res = (err as HttpError | null)?.response
  if (res?.status !== 429) return null
  const secs = Number(res.headers?.['retry-after'] ?? res.headers?.['Retry-After'])
  if (!Number.isFinite(secs) || secs <= 0) return t('ai.limit.reached')
  // Intl words the interval in the reader's language, plurals included
  // ("in 9 hours", "خلال 9 ساعات"), which a template with {n} cannot.
  const rtf = new Intl.RelativeTimeFormat(t('ai.limit.locale'), { numeric: 'always' })
  const when = secs >= 86400 ? rtf.format(Math.ceil(secs / 86400), 'day')
    : secs >= 3600 ? rtf.format(Math.floor(secs / 3600), 'hour')
    : rtf.format(Math.max(1, Math.ceil(secs / 60)), 'minute')
  return t('ai.limit.resets', { when: localDigits(when) })
}
