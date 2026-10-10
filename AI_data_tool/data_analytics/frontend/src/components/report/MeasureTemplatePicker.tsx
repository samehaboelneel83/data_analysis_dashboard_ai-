/**
 * "What do you want to measure?" -- the first step of a new measure. Four
 * everyday measures as small forms (lib/measureTemplates.ts); each writes the
 * formula, which stays editable in the formula editor.
 */
import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import type { DatasetColumn } from '../../services/api'
import { useT, type MessageKey } from '../../i18n'
import ConditionBoxes from '../ConditionBoxes'
import { newRow, type CondNode } from '../../lib/conditionTree'
import type { SqlJoiner } from '../../lib/sqlWhere'
import {
  buildOnly, buildRatio, buildShare, buildSummary, SUMMARIES,
  type BuiltMeasure, type MeasureTemplateKey, type OnlyHow, type RatioOp, type Summary,
} from '../../lib/measureTemplates'

const CARDS: { key: MeasureTemplateKey; icon: string }[] = [
  { key: 'summary', icon: 'Σ' }, { key: 'ratio', icon: '÷' }, { key: 'share', icon: '%' }, { key: 'only', icon: '⧩' },
]
const field: CSSProperties = { fontSize: 11.5, padding: '3px 6px' }
const row: CSSProperties = { display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', fontSize: 12 }

interface Props {
  columns: DatasetColumn[]
  template: MeasureTemplateKey | null
  onTemplate: (t: MeasureTemplateKey | null) => void
  onBuilt: (b: BuiltMeasure | null) => void
  onWriteFormula: () => void
}

export default function MeasureTemplatePicker({ columns, template, onTemplate, onBuilt, onWriteFormula }: Props) {
  const t = useT()
  if (!template) {
    return (
      <div data-testid="measure-templates">
        <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 6 }}>{t('pg.panelsA.mt.ask')}</div>
        <div style={{ display: 'grid', gap: 6 }}>
          {CARDS.map(c => (
            <button key={c.key} type="button" onClick={() => onTemplate(c.key)}
              style={{ textAlign: 'start', padding: '7px 10px', borderRadius: 7, border: '1px solid var(--border)',
                background: 'var(--surface2)', cursor: 'pointer', color: 'var(--text)' }}>
              <div style={{ fontWeight: 700, fontSize: 12 }}><span aria-hidden style={{ marginInlineEnd: 6 }}>{c.icon}</span>
                {t(`pg.panelsA.mt.${c.key}.title` as MessageKey)}</div>
              <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 2 }}>{t(`pg.panelsA.mt.${c.key}.desc` as MessageKey)}</div>
            </button>
          ))}
        </div>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onWriteFormula} style={{ fontSize: 11, marginTop: 6 }}>
          {t('pg.panelsA.tpl.formula')}
        </button>
      </div>
    )
  }
  return (
    <div data-testid={`measure-template-${template}`}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <button type="button" onClick={() => { onTemplate(null); onBuilt(null) }}
          style={{ border: 'none', background: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 11.5, padding: 0 }}>
          {t('pg.panelsA.tpl.back')}
        </button>
        <span style={{ fontWeight: 700, fontSize: 12 }}>{t(`pg.panelsA.mt.${template}.title` as MessageKey)}</span>
      </div>
      {template === 'summary' && <SummaryForm columns={columns} onBuilt={onBuilt} />}
      {template === 'ratio' && <RatioForm columns={columns} onBuilt={onBuilt} />}
      {template === 'share' && <ShareForm columns={columns} onBuilt={onBuilt} />}
      {template === 'only' && <OnlyForm columns={columns} onBuilt={onBuilt} />}
    </div>
  )
}

type FormProps = { columns: DatasetColumn[]; onBuilt: (b: BuiltMeasure | null) => void }

function HowSelect({ value, onChange, aria, only }: { value: string; onChange: (v: Summary) => void; aria: string; only?: readonly string[] }) {
  const t = useT()
  return (
    <select aria-label={aria} value={value} onChange={e => onChange(e.target.value as Summary)} style={field}>
      {(only ?? SUMMARIES).map(s => <option key={s} value={s}>{t(`pg.panelsA.mt.how.${s}` as MessageKey)}</option>)}
    </select>
  )
}

function Col({ columns, value, onChange, aria, numericOnly }: {
  columns: DatasetColumn[]; value: string; onChange: (v: string) => void; aria: string; numericOnly?: boolean
}) {
  const t = useT()
  const list = numericOnly ? columns.filter(c => c.dtype === 'numeric') : columns
  return (
    <select aria-label={aria} value={value} onChange={e => onChange(e.target.value)} style={field}>
      <option value="">{t('pg.panelsA.tpl.pickColumn')}</option>
      {list.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
    </select>
  )
}

/** Count / distinct work on any column; sums and averages need numbers. */
const needsNumber = (how: string) => !['COUNT', 'COUNTD', 'ROWS'].includes(how)

function SummaryForm({ columns, onBuilt }: FormProps) {
  const t = useT()
  const [how, setHow] = useState<Summary>('SUM')
  const [column, setColumn] = useState('')
  useEffect(() => { onBuilt(buildSummary({ how, column })) }, [how, column]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div style={row}>
      <HowSelect value={how} onChange={v => { setHow(v); setColumn('') }} aria={t('pg.panelsA.mt.howA')} />
      <span>{t('pg.panelsA.tpl.date.of')}</span>
      <Col columns={columns} value={column} onChange={setColumn} aria={t('pg.panelsA.mt.column')} numericOnly={needsNumber(how)} />
    </div>
  )
}

function RatioForm({ columns, onBuilt }: FormProps) {
  const t = useT()
  const [howA, setHowA] = useState<Summary>('SUM')
  const [a, setA] = useState('')
  const [op, setOp] = useState<RatioOp>('div')
  const [howB, setHowB] = useState<Summary>('SUM')
  const [b, setB] = useState('')
  useEffect(() => { onBuilt(buildRatio({ howA, a, op, howB, b })) }, [howA, a, op, howB, b]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={row}>
        <HowSelect value={howA} onChange={setHowA} aria={t('pg.panelsA.mt.howA')} />
        <span>{t('pg.panelsA.tpl.date.of')}</span>
        <Col columns={columns} value={a} onChange={setA} aria={t('pg.panelsA.mt.colA')} numericOnly={needsNumber(howA)} />
      </div>
      <select aria-label={t('pg.panelsA.mt.op')} value={op} onChange={e => setOp(e.target.value as RatioOp)} style={{ ...field, alignSelf: 'flex-start' }}>
        {(['div', 'pct_of', 'pct_change', 'diff'] as RatioOp[]).map(o => <option key={o} value={o}>{t(`pg.panelsA.mt.op.${o}` as MessageKey)}</option>)}
      </select>
      <div style={row}>
        <HowSelect value={howB} onChange={setHowB} aria={t('pg.panelsA.mt.howB')} />
        <span>{t('pg.panelsA.tpl.date.of')}</span>
        <Col columns={columns} value={b} onChange={setB} aria={t('pg.panelsA.mt.colB')} numericOnly={needsNumber(howB)} />
      </div>
      {op !== 'diff' && <div style={{ fontSize: 10.5, color: 'var(--muted)' }}>{t('pg.panelsA.mt.zero')}</div>}
    </div>
  )
}

function ShareForm({ columns, onBuilt }: FormProps) {
  const t = useT()
  const [how, setHow] = useState<Summary>('SUM')
  const [column, setColumn] = useState('')
  useEffect(() => { onBuilt(buildShare({ how, column })) }, [how, column]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={row}>
        <HowSelect value={how} onChange={setHow} aria={t('pg.panelsA.mt.howA')} only={['SUM', 'COUNT', 'COUNTD']} />
        <span>{t('pg.panelsA.tpl.date.of')}</span>
        <Col columns={columns} value={column} onChange={setColumn} aria={t('pg.panelsA.mt.column')} numericOnly={needsNumber(how)} />
      </div>
      <div style={{ fontSize: 10.5, color: 'var(--muted)' }}>{t('pg.panelsA.mt.share.note')}</div>
    </div>
  )
}

let seq = 0
function OnlyForm({ columns, onBuilt }: FormProps) {
  const t = useT()
  const numeric = useMemo(() => new Set(columns.filter(c => c.dtype === 'numeric').map(c => c.name)), [columns])
  const [how, setHow] = useState<OnlyHow>('SUM')
  const [column, setColumn] = useState('')
  const [joiner, setJoiner] = useState<SqlJoiner>('and')
  const [conds, setConds] = useState<CondNode[]>(() => [{ ...newRow('data'), id: `m${++seq}` }])
  useEffect(() => { onBuilt(buildOnly({ how, column, joiner, conds, name: '' }, numeric)) }, [how, column, joiner, conds, numeric]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={row}>
        <select aria-label={t('pg.panelsA.mt.howA')} value={how} onChange={e => setHow(e.target.value as OnlyHow)} style={field}>
          {(['SUM', 'AVG', 'ROWS'] as OnlyHow[]).map(h => <option key={h} value={h}>{t(`pg.panelsA.mt.only.${h}` as MessageKey)}</option>)}
        </select>
        {how !== 'ROWS' && (<>
          <span>{t('pg.panelsA.tpl.date.of')}</span>
          <Col columns={columns} value={column} onChange={setColumn} aria={t('pg.panelsA.mt.column')} numericOnly />
        </>)}
      </div>
      <ConditionBoxes nodes={conds} joiner={joiner} onChange={setConds} onJoiner={setJoiner}
        rootLabel={t('pg.panelsA.mt.only.rows')} tables={[]} base="data" columnsOf={() => columns.map(c => c.name)} />
    </div>
  )
}
