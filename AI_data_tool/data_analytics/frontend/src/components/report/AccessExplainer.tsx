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
          {decisions.map(d => (
            <li key={d.action} style={{ display: 'flex', gap: 8 }}>
              <span aria-label={d.allowed ? 'allowed' : 'not allowed'} style={{ color: d.allowed ? 'var(--success)' : 'var(--danger)', fontWeight: 700 }}>
                {d.allowed ? '✓' : '✕'}
              </span>
              <span><b>{ACTION_WORDS[d.action] ?? d.action}</b><br />
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>{d.reason}</span></span>
            </li>
          ))}
        </ul>
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
