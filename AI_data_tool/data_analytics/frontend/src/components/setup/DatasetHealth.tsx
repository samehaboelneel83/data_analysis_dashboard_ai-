/**
 * "What you should know" on a dataset's own pages (guided setup, phase 5).
 *
 * Prefers the findings of the person's guided setup (model-checked rules and
 * insights); otherwise asks for the quick health any dataset gets -- an
 * uploaded file as much as a connection's table. Plain first; the page's
 * own detailed panels stay below it, untouched (decision D6).
 */
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useT } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { setupApi, type SetupFindingItem, type SetupFindings } from '../../services/api'
import FindingsSummary from './FindingsSummary'

export default function DatasetHealth({ datasetId, dataSourceId, onChanged, showInsights = true }: {
  datasetId: number
  /** The connection behind the dataset, if any: offers the guided setup's deeper check. */
  dataSourceId?: number | null
  /** Called after a fix changed the dataset, so the page can reload. */
  onChanged?: () => void
  showInsights?: boolean
}) {
  const t = useT()
  const { language } = useDirection()
  const [findings, setFindings] = useState<SetupFindings | null>(null)
  const [setupSource, setSetupSource] = useState<number | null>(null)
  const [done, setDone] = useState<string[]>([])
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const fromSetup = await setupApi.findings(datasetId)
      if (fromSetup.findings) {
        setFindings(fromSetup.findings); setSetupSource(fromSetup.source_id); return
      }
    } catch { /* fall through to the quick health */ }
    try { setFindings(await setupApi.datasetHealth(datasetId, language)); setSetupSource(null) }
    catch { setFindings(null) }
  }, [datasetId, language])
  useEffect(() => { load() }, [load])

  if (!findings) return null

  async function fix(item: SetupFindingItem, how: 'fix' | 'check') {
    setBusy(`${item.id}|${how}`)
    try {
      if (setupSource) await setupApi.fix(setupSource, datasetId, item.id, how, language)
      else if (item.action) await setupApi.datasetFix(datasetId, item.action, language)
      setDone(d => [...d, `${item.id}|${how}`])
      toast.success(how === 'fix' ? t('setup.c.fixed') : t('setup.c.checkSaved'))
      onChanged?.()
    } catch { toast.error(t('setup.c.fixFailed')) } finally { setBusy(null) }
  }

  const shown: SetupFindings = {
    ...findings,
    fixed: [...findings.fixed, ...done],
    insights: showInsights ? findings.insights : [],
    // The quick health has no saved rule to warn about: only the setup's lines offer "Warn me".
    health: setupSource ? findings.health
      : findings.health.map(i => i.action ? { ...i, action: { ...i.action, rule: undefined } } : i),
  }
  return (
    <div className="dl-health">
      <FindingsSummary findings={shown} busy={busy} onFix={fix} healthTitle={t('setup.p.title')} />
      {!setupSource && dataSourceId && (
        <p className="dl-health__more">
          <Link to={`/setup/${dataSourceId}`}>{t('setup.p.deeper')}</Link>
        </p>
      )}
    </div>
  )
}
