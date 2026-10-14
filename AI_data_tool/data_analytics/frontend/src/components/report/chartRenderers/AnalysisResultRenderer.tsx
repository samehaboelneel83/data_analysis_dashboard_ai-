import { useT } from '../../../i18n'
import { ResultFor } from '../../analysis/analysisResults'
import type { ChartRendererProps } from './types'

/**
 * An analysis result as a tile (server: model_widgets.shape_analysis_result):
 * the same view the dataset's Analysis tab draws, run on the rows the page
 * shows -- so a filter on the page re-runs it like every chart beside it.
 * A tile that is not set up, or that the analysis refused, says so in words.
 */
export default function AnalysisResultRenderer({ data }: ChartRendererProps) {
  const t = useT()
  const note = (strong: string, text?: string) => (
    <div role="note" data-testid="analysis-tile-note" style={{ padding: 12, fontSize: 13, display: 'flex', flexDirection: 'column', gap: 6 }}>
      <b>{strong}</b>{text && <span>{text}</span>}
    </div>
  )
  if (!data || data.type !== 'analysis') return null
  if (data.status === 'incomplete') return note(t('atile.notSetUp'))
  if (data.status === 'refused') return note(t('atile.refused'), String(data.reason ?? ''))
  return (
    <div data-testid="analysis-tile" tabIndex={0} style={{ height: '100%', overflow: 'auto' }}
      onMouseDown={e => e.stopPropagation()}>
      <ResultFor kind={String(data.kind)} result={data.result} params={(data.params ?? {}) as Record<string, unknown>} />
    </div>
  )
}
