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
  const hours = Math.floor(secs / 3600)
  const when = hours >= 24 ? t('ai.limit.days', { n: localDigits(String(Math.ceil(secs / 86400))) })
    : hours >= 1 ? t('ai.limit.hours', { n: localDigits(String(hours)) })
    : t('ai.limit.minutes', { n: localDigits(String(Math.max(1, Math.ceil(secs / 60)))) })
  return t('ai.limit.resets', { when })
}
