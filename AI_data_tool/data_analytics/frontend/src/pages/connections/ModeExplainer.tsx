/**
 * Import vs DirectQuery, said where the choice is made (4.4). The HR
 * evaluation found the trade-off only afterwards -- a live dataset had no
 * Models, Data quality or Segment tab, and nothing had said so.
 */
import { useT } from '../../i18n'

export default function ModeExplainer({ mode }: { mode: 'import' | 'directquery' }) {
  const t = useT()
  const row = (m: 'import' | 'directquery', title: string, body: string) => (
    <div style={{ display: 'flex', gap: 6, alignItems: 'baseline',
      fontWeight: mode === m ? 600 : 400, color: mode === m ? 'var(--text)' : 'var(--muted)' }}>
      <span aria-hidden>{mode === m ? '●' : '○'}</span>
      <span><b>{title}</b> — {body}</span>
    </div>
  )
  return (
    <div data-testid="mode-explainer" role="note" style={{ fontSize: 11.5, display: 'grid', gap: 2 }}>
      {row('directquery', t('sb.dqTitle'), t('sb.dqWhy'))}
      {row('import', t('sb.importTitle'), t('sb.importWhy'))}
    </div>
  )
}
