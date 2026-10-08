import { useModalDialog } from '../ui/useModalDialog'
import type { AuthzDecision } from '../../services/api'
import type { ReactNode } from 'react'
import { useT, type MessageKey } from '../../i18n'

const ACTION_WORDS: Record<string, MessageKey> = {
  view: 'pg.panelsA.ax.action.view', edit: 'pg.panelsA.ax.action.edit', data: 'pg.panelsA.ax.action.data',
  share_link: 'pg.panelsA.ax.action.share_link', download: 'pg.panelsA.ax.action.download',
}

/** A translated sentence with its `{slot}`s filled by elements. */
function slots(text: string, parts: Record<string, ReactNode>): ReactNode[] {
  return text.split(/(\{\w+\})/).map((s, i) => {
    const m = /^\{(\w+)\}$/.exec(s)
    return m && m[1] in parts ? <span key={i}>{parts[m[1]]}</span> : s
  })
}

/** "What can I do here, and why?" -- every decision with the rule behind it,
 *  from the same checks the server enforces (Phase 7.3). */
export default function AccessExplainer({ decisions, sensitivity, onClose }: {
  decisions: AuthzDecision[]; sensitivity?: { effective?: string | null; reasons?: string[] } | null; onClose: () => void
}) {
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const t = useT()
  const dataRules = decisions.find(d => d.action === 'data_rules')
  const actions = decisions.filter(d => d.action !== 'data_rules')
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,.45)',
      display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={t('pg.panelsA.ax.aria')} onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
          padding: 18, width: 'min(520px, calc(100vw - 32px))', display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <b>{t('shx.why')}</b>
          <button type="button" className="btn btn-sm" aria-label={t('pg.panelsA.close')} onClick={onClose}>×</button>
        </div>
        <ul data-testid="access-decisions" style={{ margin: 0, paddingInlineStart: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {actions.map(d => (
            <li key={d.action} style={{ display: 'flex', gap: 8 }}>
              <span aria-label={d.allowed ? t('pg.panelsA.ax.allowed') : t('pg.panelsA.ax.notAllowed')} style={{ color: d.allowed ? 'var(--success)' : 'var(--danger)', fontWeight: 700 }}>
                {d.allowed ? '✓' : '✕'}
              </span>
              <span><b>{ACTION_WORDS[d.action] ? t(ACTION_WORDS[d.action]) : d.action}</b><br />
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>{d.reason}</span></span>
            </li>
          ))}
        </ul>
        {dataRules && dataRules.allowed && (
          <div data-testid="access-data-rules" style={{ fontSize: 12, borderTop: '1px solid var(--border)', paddingTop: 8,
            display: 'flex', flexDirection: 'column', gap: 6 }}>
            <b style={{ fontSize: 13 }}>{t('pg.panelsA.ax.whatData')}</b>
            <span style={{ color: 'var(--muted)' }}>{dataRules.reason}</span>
            {(dataRules.rules ?? []).map(r => (
              <div key={r.dataset_id} style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px' }}>
                <div style={{ fontWeight: 600 }}><bdi>{r.dataset_name}</bdi></div>
                {r.row_rule ? (
                  <div>{slots(t('pg.panelsA.ax.rowsWhere'), { rule: <code dir="ltr">{r.row_rule_for_you ?? r.row_rule}</code> })}
                    {r.row_rule_for_you && r.row_rule_for_you !== r.row_rule && (
                      <span style={{ color: 'var(--muted)' }}>{slots(t('pg.panelsA.ax.ruleNote'), { rule: <code dir="ltr">{r.row_rule}</code> })}</span>
                    )}
                  </div>
                ) : <div>{t('pg.panelsA.ax.rowsAll')}</div>}
                <div>{r.hidden_columns.length
                  ? slots(t('pg.panelsA.ax.colsHidden'), { cols: <b><bdi>{r.hidden_columns.join(', ')}</bdi></b> })
                  : t('pg.panelsA.ax.colsAll')}</div>
              </div>
            ))}
          </div>
        )}
        {sensitivity?.effective && (
          <div data-testid="access-sensitivity" style={{ fontSize: 12, borderTop: '1px solid var(--border)', paddingTop: 8 }}>
            {sensitivity.reasons?.[0]
              ? slots(t('pg.panelsA.ax.sensWhy'), { level: <b><bdi>{sensitivity.effective}</bdi></b>, reason: <bdi>{sensitivity.reasons[0]}</bdi> })
              : slots(t('pg.panelsA.ax.sens'), { level: <b><bdi>{sensitivity.effective}</bdi></b> })}
            {' '}{sensitivity.effective === 'Restricted'
              ? t('pg.panelsA.ax.restricted')
              : sensitivity.effective === 'Confidential'
                ? t('pg.panelsA.ax.confidential')
                : ''}
          </div>
        )}
      </div>
    </div>
  )
}
