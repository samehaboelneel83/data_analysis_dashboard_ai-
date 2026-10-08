/**
 * A dataset's findings in plain words: health lines (what / why / what to
 * do, with "Fix it") and insights. Used by the guided setup's Check &
 * discover step and, read-only or with fixes, on the dataset's own pages
 * (plan phase 5) -- one look everywhere.
 */
import type { ReactNode } from 'react'
import PlainSummary, { type PlainItem } from '../ui/PlainSummary'
import { useT } from '../../i18n'
import type { SetupFindingItem, SetupFindings } from '../../services/api'

export default function FindingsSummary({ findings, onFix, busy, details, healthTitle, insightsTitle }: {
  findings: SetupFindings
  /** Omit to show the lines without buttons. */
  onFix?: (item: SetupFindingItem, how: 'fix' | 'check') => void
  /** "<item id>|<how>" currently being applied. */
  busy?: string | null
  details?: ReactNode
  healthTitle?: string
  insightsTitle?: string
}) {
  const t = useT()
  const done = new Set(findings.fixed)
  const toItem = (i: SetupFindingItem): PlainItem => ({
    id: i.id, tone: i.tone, what: i.what, why: i.why || undefined, todo: i.todo ?? undefined,
    action: onFix && i.action ? {
      label: i.action.label, onClick: () => onFix(i, 'fix'),
      busy: busy === `${i.id}|fix`, done: done.has(`${i.id}|fix`),
    } : undefined,
    secondary: onFix && i.action?.rule ? {
      label: t('setup.c.warnMe'), onClick: () => onFix(i, 'check'),
      busy: busy === `${i.id}|check`, done: done.has(`${i.id}|check`),
    } : undefined,
  })
  const problems = findings.health.filter(i => i.tone !== 'good')
  const lead = problems.length
    ? t('setup.c.lead', { n: problems.length })
    : undefined
  return (
    <>
      <PlainSummary title={healthTitle ?? t('setup.c.health')} lead={lead}
        items={findings.health.map(toItem)} details={details} />
      {findings.insights.length > 0 && (
        <PlainSummary title={insightsTitle ?? t('setup.c.insights')} items={findings.insights.map(toItem)} />
      )}
    </>
  )
}
