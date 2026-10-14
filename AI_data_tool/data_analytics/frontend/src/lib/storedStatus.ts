/**
 * The last status of an alert or a scheduled delivery, in the reader's language.
 *
 * The server stores these lines as text when the check or the delivery runs
 * (backend services/alerts.py, delivery.py, delivery_jobs.py), so a line
 * written last week is English whatever the reader's language is today. They
 * are a small fixed vocabulary joined by "; ", which is put into words here.
 * A part this does not know -- a mail server's own error, say -- is shown as
 * stored; the reason after "evaluation failed:" or "build failed:" is too.
 */
import type { MessageKey, TranslateFn } from '../i18n'

const WHOLE: [RegExp, MessageKey, string[]][] = [
  [/^clear$/, 'sst.clear', []],
  [/^still firing \(no re-send\)$/, 'sst.stillFiring', []],
  [/^fired, emailed (\d+)$/, 'sst.firedEmailed', ['n']],
  [/^fired, no valid recipients$/, 'sst.firedNoOne', []],
  [/^posted to webhook$/, 'sst.webhook', []],
  [/^disabled: dataset or creator no longer exists$/, 'sst.disabledDataset', []],
  [/^disabled: report or creator no longer exists$/, 'sst.disabledReport', []],
  [/^no valid recipients$/, 'sst.noRecipients', []],
  [/^nothing to send$/, 'sst.nothing', []],
  [/^no change since the last delivery -- nothing sent$/, 'sst.noChange', []],
  [/^emailed (\d+)$/, 'sst.emailed', ['n']],
  [/^emailed (.+) their own view$/, 'sst.emailedOwn', ['who']],
  [/^skipped (\d+) address\(es\) that are not users here \(each recipient's own view needs an account\)$/, 'sst.skipped', ['n']],
  [/^sending \(job (\d+)\)$/, 'sst.sending', ['n']],
  [/^interrupted while sending: not resent, so no one gets it twice\. Use Send now to deliver it\.$/, 'sst.interrupted', []],
  [/^evaluation failed: (.*)$/s, 'sst.evalFailed', ['why']],
  [/^build failed: (.*)$/s, 'sst.buildFailed', ['why']],
  [/^blocked: the report is Restricted(?: \((.*)\))? -- e-mail would send its rows outside the product$/, 'sst.blocked', ['why']],
]

function part(text: string, t: TranslateFn): string {
  for (const [pattern, key, names] of WHOLE) {
    const m = pattern.exec(text)
    if (!m) continue
    const vars: Record<string, string> = {}
    names.forEach((name, i) => { vars[name] = m[i + 1] ?? '' })
    return t(key, vars).replace(/ \(\)/, '')
  }
  return text
}

export function storedStatus(status: string | null | undefined, t: TranslateFn): string {
  if (!status) return ''
  const whole = part(status, t)
  if (whole !== status) return whole
  return status.split('; ').map(p => part(p, t)).join('; ')
}
