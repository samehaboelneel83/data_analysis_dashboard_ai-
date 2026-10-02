import { useModalDialog } from '../ui/useModalDialog'
import type { AuthzDecision } from '../../services/api'

const ACTION_WORDS: Record<string, string> = {
  view: 'Open this report', edit: 'Change this report', data: 'Change its data model',
  share_link: 'Share it by guest link', download: 'Download it (PDF, package, CSV)',
}

/** "What can I do here, and why?" -- every decision with the rule behind it,
 *  from the same checks the server enforces (Phase 7.3). */
export default function AccessExplainer({ decisions, sensitivity, onClose }: {
  decisions: AuthzDecision[]; sensitivity?: { effective?: string | null; reasons?: string[] } | null; onClose: () => void
}) {
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const dataRules = decisions.find(d => d.action === 'data_rules')
  const actions = decisions.filter(d => d.action !== 'data_rules')
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,.45)',
      display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label="Your access" onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
          padding: 18, width: 'min(520px, calc(100vw - 32px))', display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <b>Your access, and why</b>
          <button type="button" className="btn btn-sm" aria-label="Close" onClick={onClose}>×</button>
        </div>
        <ul data-testid="access-decisions" style={{ margin: 0, paddingInlineStart: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {actions.map(d => (
            <li key={d.action} style={{ display: 'flex', gap: 8 }}>
              <span aria-label={d.allowed ? 'allowed' : 'not allowed'} style={{ color: d.allowed ? 'var(--success)' : 'var(--danger)', fontWeight: 700 }}>
                {d.allowed ? '✓' : '✕'}
              </span>
              <span><b>{ACTION_WORDS[d.action] ?? d.action}</b><br />
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>{d.reason}</span></span>
            </li>
          ))}
        </ul>
        {dataRules && dataRules.allowed && (
          <div data-testid="access-data-rules" style={{ fontSize: 12, borderTop: '1px solid var(--border)', paddingTop: 8,
            display: 'flex', flexDirection: 'column', gap: 6 }}>
            <b style={{ fontSize: 13 }}>What data you see</b>
            <span style={{ color: 'var(--muted)' }}>{dataRules.reason}</span>
            {(dataRules.rules ?? []).map(r => (
              <div key={r.dataset_id} style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px' }}>
                <div style={{ fontWeight: 600 }}>{r.dataset_name}</div>
                {r.row_rule ? (
                  <div>Rows: only where <code dir="ltr">{r.row_rule_for_you ?? r.row_rule}</code>
                    {r.row_rule_for_you && r.row_rule_for_you !== r.row_rule && (
                      <span style={{ color: 'var(--muted)' }}> (rule: <code dir="ltr">{r.row_rule}</code>)</span>
                    )}
                  </div>
                ) : <div>Rows: all</div>}
                <div>Columns: {r.hidden_columns.length
                  ? <>hidden from you — <b>{r.hidden_columns.join(', ')}</b></>
                  : 'all'}</div>
              </div>
            ))}
          </div>
        )}
        {sensitivity?.effective && (
          <div data-testid="access-sensitivity" style={{ fontSize: 12, borderTop: '1px solid var(--border)', paddingTop: 8 }}>
            Sensitivity in force: <b>{sensitivity.effective}</b>{sensitivity.reasons?.[0] ? ` — ${sensitivity.reasons[0]}` : ''}.
            {' '}{sensitivity.effective === 'Restricted'
              ? 'No guest links or embeds; downloads need data-level access.'
              : sensitivity.effective === 'Confidential'
                ? 'Guest links need a signed-in member; personal-data columns are redacted from links, embeds and files.'
                : ''}
          </div>
        )}
      </div>
    </div>
  )
}
