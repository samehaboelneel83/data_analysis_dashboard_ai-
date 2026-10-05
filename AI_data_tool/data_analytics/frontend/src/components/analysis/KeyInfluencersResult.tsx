import { useDirection } from '../../contexts/DirectionContext'
import { useT } from '../../i18n'
import { majorityDir } from '../../lib/autoDir'
import { localDigits } from '../../lib/arabicFormats'
import type { KeyInfluencer, KeyInfluencersResult as Result } from '../../services/api'

/** HR re-test: a mean salary read "88,604.645". Whole units from 100 up,
 *  two decimals below -- the precision a reader can use. */
export function fmtMean(v: number): string {
  return Math.abs(v) >= 100
    ? Math.round(v).toLocaleString()
    : v.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

/** A group under this share of the rows is marked "small group" and muted:
 *  its lift moves on few rows, so it reads as a hint, not a finding. */
export const SMALL_GROUP_SHARE = 0.1

const NUM = { fontVariantNumeric: 'tabular-nums' } as const
const BIG = { fontSize: 20, fontWeight: 700, color: 'var(--text)', ...NUM } as const

/** Strongest effect first, in either direction: 0.46x is as strong as 1.54x. */
export const rankInfluencers = (rows: KeyInfluencer[]) =>
  [...rows].sort((a, b) => Math.abs(b.lift - 1) - Math.abs(a.lift - 1))

/**
 * Key influencers as a ranked chart (redesign step 2, KI-7).
 *
 * Built only from the row fields the endpoint returns -- factor, group,
 * rate/mean, lift, rows, share_of_rows. There are no p-values in the payload,
 * so none are shown. Each row is "factor is group", a bar out from the 1.0x
 * baseline, and the rows behind it.
 *
 * Direction is in words and in which side the bar grows, never in red/green:
 * the app cannot know whether more of an outcome is good (salary) or bad
 * (churn), and colouring "more" red told an HR lead a higher salary was a
 * problem.
 */
export default function KeyInfluencersResult({ result, leftOut = [] }: {
  result: Result
  /** Columns the client skipped as identifiers, said under the table. */
  leftOut?: string[]
}) {
  const tr = useT()
  const { direction } = useDirection()
  const { meta } = result
  const rows = rankInfluencers(result.rows)
  const maxDev = Math.max(...rows.map(r => Math.abs(r.lift - 1)), 0.0001)
  const isRate = meta.measure === 'rate'
  return (
    <div className="dl-ki" data-testid="key-influencers"
      style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 14 }}>
      <div data-testid="influencers-baseline" style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 12,
        background: 'var(--surface2)', borderRadius: 'var(--radius)', padding: '10px 12px',
        display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
        {isRate
          ? <>{tr('ki.baselineRate')}
              <strong dir="ltr" style={{ unicodeBidi: 'isolate', color: 'var(--text)' }}>{meta.target} = {meta.target_value}</strong>
              <strong style={BIG}>{(meta.baseline * 100).toFixed(1)}%</strong></>
          : <>{tr('ki.baselineMean')}
              <strong style={BIG}>{fmtMean(meta.baseline)}</strong>
              {tr('ki.for')} <strong style={{ color: 'var(--text)' }}>{meta.target}</strong></>}
        <span>· {tr('ki.rows', { n: meta.n_rows_used.toLocaleString() })}</span>
      </div>
      <table style={{ width: '100%' }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'start' }}>{tr('ki.when')}</th>
            <th style={{ textAlign: 'end' }}>{isRate ? tr('ki.rate') : tr('ki.mean')}</th>
            <th style={{ textAlign: 'start' }}>{tr('ki.effect')}</th>
            <th style={{ textAlign: 'end' }}>{tr('ki.vsBaseline')}</th>
            <th style={{ textAlign: 'end' }}>{tr('ki.rowsCol')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const small = r.share_of_rows < SMALL_GROUP_SHARE
            const width = `${(Math.abs(r.lift - 1) / maxDev) * 50}%`
            const up = r.lift >= 1
            return (
              <tr key={i} data-small={small || undefined}>
                {/* The rule can hold an interval, "(64.5, 70.1]": an LTR
                    isolate keeps its brackets in maths order under RTL,
                    where they otherwise swapped ends with the text. */}
                <td>
                  <span dir="ltr" style={{ unicodeBidi: 'isolate' }}><strong>{r.factor}</strong> {tr('ki.is')} {r.group}</span>
                  {small && (
                    <span className="dl-ki__small" style={{ marginInlineStart: 8, fontSize: 10.5, fontWeight: 600,
                      padding: '1px 7px', borderRadius: 99, color: 'var(--mc-warning)',
                      background: 'var(--mc-warning-soft)', border: '1px solid var(--mc-warning-line)' }}>
                      {tr('ki.smallGroup')}
                    </span>
                  )}
                </td>
                <td style={{ ...NUM, textAlign: 'end', color: small ? 'var(--muted)' : undefined }}>
                  {isRate ? `${((r.rate ?? 0) * 100).toFixed(1)}%` : fmtMean(r.mean ?? 0)}
                </td>
                <td style={{ minWidth: 120 }} aria-hidden>
                  <div style={{ position: 'relative', height: 12 }}>
                    <span style={{ position: 'absolute', insetBlock: -3, insetInlineStart: '50%', width: 1,
                      background: 'var(--border-strong, var(--border))' }} />
                    <span data-testid="influencer-bar" style={{ position: 'absolute', insetBlock: 0, width,
                      ...(up ? { insetInlineStart: '50%' } : { insetInlineEnd: '50%' }),
                      background: 'var(--accent)', opacity: small ? 0.45 : up ? 0.9 : 0.6,
                      borderRadius: 2 }} />
                  </div>
                </td>
                {/* Direction stated in words: "1.9x" alone reads as good news
                    even when the outcome is churn. */}
                <td data-testid="influencer-lift" style={{ ...NUM, textAlign: 'end',
                  color: small ? 'var(--muted)' : 'var(--text)', whiteSpace: 'nowrap' }}>
                  <span aria-hidden style={{ color: 'var(--accent)' }}>{up ? '▲' : '▼'}</span>{' '}
                  {r.lift.toFixed(2)}× {up ? tr('ki.more') : tr('ki.less')}
                </td>
                <td style={{ ...NUM, textAlign: 'end', whiteSpace: 'nowrap', color: small ? 'var(--muted)' : undefined }}>
                  {r.rows.toLocaleString()}
                  <span style={{ color: 'var(--muted)' }}> · {localDigits(String(Math.round(r.share_of_rows * 100)))}%</span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {leftOut.length > 0 && (
        <div data-testid="influencers-left-out" style={{ marginTop: 12, fontSize: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>{tr('ki.leftOut')}</div>
          {leftOut.map(c => (
            <div key={c} style={{ color: 'var(--muted)', marginBottom: 2 }}>
              <code dir="ltr" style={{ fontSize: 11.5, padding: '1px 5px', borderRadius: 4,
                background: 'var(--surface2)', color: 'var(--text)', marginInlineEnd: 6 }}>{c}</code>
              {tr('ki.leftOutIdentifier')}
            </div>
          ))}
        </div>
      )}
      {/* Server-written English for now (AP3): laid out by its own script. */}
      <p dir={majorityDir(meta.caveat, direction)} style={{ fontSize: 11, color: 'var(--muted)', marginTop: 10 }}>{meta.caveat}</p>
      <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
        {tr('ki.smallGroupNote', { pct: localDigits(String(SMALL_GROUP_SHARE * 100)) })}
      </p>
      {result.warnings.length > 0 && (
        <ul style={{ fontSize: 11, color: 'var(--muted)', marginTop: 6, paddingInline: 18 }}>
          {result.warnings.map((w, i) => <li key={i} dir={majorityDir(w, direction)}>{w}</li>)}
        </ul>
      )}
    </div>
  )
}
