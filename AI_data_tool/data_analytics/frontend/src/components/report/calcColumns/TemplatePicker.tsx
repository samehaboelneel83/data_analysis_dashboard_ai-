/**
 * "What do you want to make?" -- the first step of a new calculated column.
 * Six everyday tasks as small forms; each writes the formula for the person
 * (lib/calcTemplates.ts) and hands it up, so the column saved is an ordinary
 * calculated column that can still be opened as a formula.
 */
import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import type { DatasetColumn } from '../../../services/api'
import { useT, type MessageKey } from '../../../i18n'
import ConditionBoxes from '../../ConditionBoxes'
import { newRow, type CondNode } from '../../../lib/conditionTree'
import {
  bandsProblem, buildBands, buildClean, buildDate, buildLabel, buildMath, buildText, DATE_PARTS,
  type Band, type Built, type CleanAction, type DatePart, type LabelRule, type MathOp, type TemplateKey,
} from '../../../lib/calcTemplates'

const CARDS: { key: TemplateKey; icon: string }[] = [
  { key: 'math', icon: '±' }, { key: 'bands', icon: '▤' }, { key: 'label', icon: '🏷' },
  { key: 'text', icon: 'Aa' }, { key: 'date', icon: '📅' }, { key: 'clean', icon: '✧' },
]

const field: CSSProperties = { fontSize: 12, padding: '4px 7px' }
const lab: CSSProperties = { fontSize: 11, color: 'var(--muted)', display: 'block', marginBottom: 3 }
let ruleSeq = 0

interface Props {
  columns: DatasetColumn[]
  template: TemplateKey | null
  onTemplate: (t: TemplateKey | null) => void
  /** The formula the form currently writes (null while unfinished). */
  onBuilt: (b: Built | null) => void
  onWriteFormula: () => void
}

export default function TemplatePicker({ columns, template, onTemplate, onBuilt, onWriteFormula }: Props) {
  const t = useT()
  if (!template) {
    return (
      <div data-testid="calc-templates">
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>{t('pg.panelsA.tpl.ask')}</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 8 }}>
          {CARDS.map(c => (
            <button key={c.key} type="button" onClick={() => onTemplate(c.key)}
              style={{ textAlign: 'start', padding: '10px 12px', borderRadius: 8, border: '1px solid var(--border)',
                background: 'var(--surface2)', cursor: 'pointer', color: 'var(--text)' }}>
              <div style={{ fontWeight: 700, fontSize: 13 }}><span aria-hidden style={{ marginInlineEnd: 6 }}>{c.icon}</span>
                {t(`pg.panelsA.tpl.${c.key}.title` as MessageKey)}</div>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 3 }}>{t(`pg.panelsA.tpl.${c.key}.desc` as MessageKey)}</div>
            </button>
          ))}
        </div>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onWriteFormula} style={{ fontSize: 12, marginTop: 8 }}>
          {t('pg.panelsA.tpl.formula')}
        </button>
      </div>
    )
  }
  return (
    <div data-testid={`calc-template-${template}`}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <button type="button" onClick={() => { onTemplate(null); onBuilt(null) }}
          style={{ border: 'none', background: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 12, padding: 0 }}>
          {t('pg.panelsA.tpl.back')}
        </button>
        <span style={{ fontWeight: 700, fontSize: 13 }}>{t(`pg.panelsA.tpl.${template}.title` as MessageKey)}</span>
      </div>
      {template === 'math' && <MathForm columns={columns} onBuilt={onBuilt} />}
      {template === 'bands' && <BandsForm columns={columns} onBuilt={onBuilt} />}
      {template === 'label' && <LabelForm columns={columns} onBuilt={onBuilt} />}
      {template === 'text' && <TextForm columns={columns} onBuilt={onBuilt} />}
      {template === 'date' && <DateForm columns={columns} onBuilt={onBuilt} />}
      {template === 'clean' && <CleanForm columns={columns} onBuilt={onBuilt} />}
    </div>
  )
}

type FormProps = { columns: DatasetColumn[]; onBuilt: (b: Built | null) => void }

function ColumnSelect({ columns, value, onChange, aria, filter }: {
  columns: DatasetColumn[]; value: string; onChange: (v: string) => void; aria: string
  filter?: (c: DatasetColumn) => boolean
}) {
  const t = useT()
  const list = filter ? columns.filter(filter) : columns
  return (
    <select aria-label={aria} value={value} onChange={e => onChange(e.target.value)} style={field}>
      <option value="">{t('pg.panelsA.tpl.pickColumn')}</option>
      {list.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
    </select>
  )
}

const isNumber = (c: DatasetColumn) => c.dtype === 'numeric'
const isDate = (c: DatasetColumn) => c.dtype === 'datetime'
const isText = (c: DatasetColumn) => c.dtype !== 'numeric' && c.dtype !== 'datetime'

function MathForm({ columns, onBuilt }: FormProps) {
  const t = useT()
  const [a, setA] = useState('')
  const [op, setOp] = useState<MathOp>('sub')
  const [bKind, setBKind] = useState<'column' | 'number'>('column')
  const [b, setB] = useState('')
  useEffect(() => { onBuilt(buildMath({ a, op, bKind, b })) }, [a, op, bKind, b]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
      <ColumnSelect columns={columns} filter={isNumber} value={a} onChange={setA} aria={t('pg.panelsA.tpl.math.a')} />
      <select aria-label={t('pg.panelsA.tpl.math.op')} value={op} onChange={e => setOp(e.target.value as MathOp)} style={field}>
        {(['add', 'sub', 'mul', 'div', 'pct_change', 'pct_of'] as MathOp[]).map(o =>
          <option key={o} value={o}>{t(`pg.panelsA.tpl.math.${o}` as MessageKey)}</option>)}
      </select>
      <select aria-label={t('pg.panelsA.tpl.math.bKind')} value={bKind}
        onChange={e => { setBKind(e.target.value as 'column' | 'number'); setB('') }} style={field}>
        <option value="column">{t('pg.panelsA.tpl.math.aColumn')}</option>
        <option value="number">{t('pg.panelsA.tpl.math.aNumber')}</option>
      </select>
      {bKind === 'column'
        ? <ColumnSelect columns={columns} filter={isNumber} value={b} onChange={setB} aria={t('pg.panelsA.tpl.math.b')} />
        : <input aria-label={t('pg.panelsA.tpl.math.b')} value={b} onChange={e => setB(e.target.value)} inputMode="decimal"
            placeholder="1.14" style={{ ...field, width: 90 }} />}
      {(op === 'div' || op === 'pct_change' || op === 'pct_of') && (
        <div style={{ fontSize: 11, color: 'var(--muted)', width: '100%' }}>
          {bKind === 'number' && b.trim() !== '' && Number(b) === 0 ? t('pg.panelsA.tpl.math.zero') : t('pg.panelsA.tpl.math.divNote')}
        </div>
      )}
    </div>
  )
}

function BandsForm({ columns, onBuilt }: FormProps) {
  const t = useT()
  const [column, setColumn] = useState('')
  const [bands, setBands] = useState<Band[]>([{ below: '', label: '' }, { below: '', label: '' }])
  const [elseLabel, setElse] = useState('')
  const [emptyLabel, setEmpty] = useState('')
  const form = { column, bands, elseLabel, emptyLabel }
  const problem = bandsProblem(form)
  useEffect(() => { onBuilt(buildBands(form)) }, [column, bands, elseLabel, emptyLabel]) // eslint-disable-line react-hooks/exhaustive-deps
  const set = (i: number, patch: Partial<Band>) => setBands(p => p.map((x, k) => k === i ? { ...x, ...patch } : x))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label style={lab}>{t('pg.panelsA.tpl.bands.column')}
        <div><ColumnSelect columns={columns} filter={isNumber} value={column} onChange={setColumn} aria={t('pg.panelsA.tpl.bands.column')} /></div>
      </label>
      {bands.map((b, i) => (
        <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', fontSize: 12 }}>
          <span>{t('pg.panelsA.tpl.bands.below')}</span>
          <input aria-label={t('pg.panelsA.tpl.bands.limitN', { n: i + 1 })} value={b.below} inputMode="decimal"
            onChange={e => set(i, { below: e.target.value })} style={{ ...field, width: 110 }} />
          <span aria-hidden>{t('pg.panelsA.tpl.arrow')}</span>
          <input aria-label={t('pg.panelsA.tpl.bands.labelN', { n: i + 1 })} value={b.label}
            placeholder={t('pg.panelsA.tpl.labelPh')} onChange={e => set(i, { label: e.target.value })} style={{ ...field, width: 140 }} />
          {bands.length > 1 && (
            <button type="button" aria-label={t('pg.panelsA.tpl.bands.removeN', { n: i + 1 })}
              onClick={() => setBands(p => p.filter((_, k) => k !== i))}
              style={{ border: 'none', background: 'none', color: 'var(--danger)', cursor: 'pointer' }}>✕</button>
          )}
        </div>
      ))}
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12, flexWrap: 'wrap' }}>
        <span>{t('pg.panelsA.tpl.otherwise')}</span>
        <span aria-hidden>{t('pg.panelsA.tpl.arrow')}</span>
        <input aria-label={t('pg.panelsA.tpl.elseLabel')} value={elseLabel} placeholder={t('pg.panelsA.tpl.labelPh')}
          onChange={e => setElse(e.target.value)} style={{ ...field, width: 140 }} />
      </div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12, flexWrap: 'wrap' }}>
        <span>{t('pg.panelsA.tpl.bands.empty')}</span>
        <span aria-hidden>{t('pg.panelsA.tpl.arrow')}</span>
        <input aria-label={t('pg.panelsA.tpl.bands.emptyLabel')} value={emptyLabel} placeholder={t('pg.panelsA.tpl.optional')}
          onChange={e => setEmpty(e.target.value)} style={{ ...field, width: 140 }} />
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
          onClick={() => setBands(p => [...p, { below: '', label: '' }])}>{t('pg.panelsA.tpl.bands.add')}</button>
      </div>
      {problem && column && (
        <div role="status" style={{ fontSize: 11, color: problem === 'notAscending' ? 'var(--danger)' : 'var(--muted)' }}>
          {t(`pg.panelsA.tpl.bands.p.${problem}` as MessageKey)}
        </div>
      )}
    </div>
  )
}

function LabelForm({ columns, onBuilt }: FormProps) {
  const t = useT()
  const numeric = useMemo(() => new Set(columns.filter(isNumber).map(c => c.name)), [columns])
  const fresh = (): LabelRule => ({ id: `r${++ruleSeq}`, joiner: 'and', conds: [newRow('data')], label: '' })
  const [rules, setRules] = useState<LabelRule[]>(() => [fresh()])
  const [elseLabel, setElse] = useState('')
  useEffect(() => { onBuilt(buildLabel({ rules, elseLabel, name: 'label' }, numeric)) }, [rules, elseLabel, numeric]) // eslint-disable-line react-hooks/exhaustive-deps
  const set = (id: string, patch: Partial<LabelRule>) => setRules(p => p.map(r => r.id === id ? { ...r, ...patch } : r))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {rules.map((r, i) => (
        <div key={r.id} data-testid="calc-label-rule" style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6, display: 'flex', gap: 6, alignItems: 'center' }}>
            {i === 0 ? t('pg.panelsA.tpl.label.if') : t('pg.panelsA.tpl.label.elseIf')}
            {rules.length > 1 && (
              <button type="button" onClick={() => setRules(p => p.filter(x => x.id !== r.id))}
                style={{ marginInlineStart: 'auto', border: 'none', background: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>
                {t('pg.panelsA.tpl.label.remove')}
              </button>
            )}
          </div>
          <ConditionBoxes nodes={r.conds} joiner={r.joiner} rootLabel={t('pg.panelsA.tpl.label.when')}
            onChange={(conds: CondNode[]) => set(r.id, { conds })} onJoiner={j => set(r.id, { joiner: j })}
            tables={[]} base="data" columnsOf={() => columns.map(c => c.name)} />
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12 }}>
            <span>{t('pg.panelsA.tpl.label.then')}</span>
            <input aria-label={t('pg.panelsA.tpl.label.labelN', { n: i + 1 })} value={r.label}
              placeholder={t('pg.panelsA.tpl.labelPh')} onChange={e => set(r.id, { label: e.target.value })} style={{ ...field, width: 160 }} />
          </div>
        </div>
      ))}
      <div><button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
        onClick={() => setRules(p => [...p, fresh()])}>{t('pg.panelsA.tpl.label.add')}</button></div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12, flexWrap: 'wrap' }}>
        <span>{t('pg.panelsA.tpl.otherwise')}</span><span aria-hidden>{t('pg.panelsA.tpl.arrow')}</span>
        <input aria-label={t('pg.panelsA.tpl.elseLabel')} value={elseLabel} placeholder={t('pg.panelsA.tpl.labelPh')}
          onChange={e => setElse(e.target.value)} style={{ ...field, width: 160 }} />
      </div>
    </div>
  )
}

function TextForm({ columns, onBuilt }: FormProps) {
  const t = useT()
  const [parts, setParts] = useState<string[]>(['', ''])
  const [separator, setSep] = useState(' ')
  useEffect(() => { onBuilt(buildText({ parts, separator })) }, [parts, separator]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
      {parts.map((p, i) => (
        <span key={i} style={{ display: 'contents' }}>
          {i > 0 && <span style={{ fontSize: 11, color: 'var(--muted)' }}>+</span>}
          <ColumnSelect columns={columns} value={p} aria={t('pg.panelsA.tpl.text.partN', { n: i + 1 })}
            onChange={v => setParts(x => x.map((y, k) => k === i ? v : y))} />
        </span>
      ))}
      <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
        onClick={() => setParts(x => [...x, ''])}>{t('pg.panelsA.tpl.text.add')}</button>
      <label style={{ ...lab, display: 'flex', gap: 6, alignItems: 'center', margin: 0, width: '100%' }}>
        {t('pg.panelsA.tpl.text.sep')}
        <input aria-label={t('pg.panelsA.tpl.text.sep')} value={separator} onChange={e => setSep(e.target.value)}
          style={{ ...field, width: 60 }} />
        <span>{t('pg.panelsA.tpl.text.sepHint')}</span>
      </label>
    </div>
  )
}

function DateForm({ columns, onBuilt }: FormProps) {
  const t = useT()
  const [column, setColumn] = useState('')
  const [part, setPart] = useState<DatePart>('YEAR')
  useEffect(() => { onBuilt(buildDate({ column, part })) }, [column, part]) // eslint-disable-line react-hooks/exhaustive-deps
  const dates = columns.filter(isDate)
  return (
    <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
      <select aria-label={t('pg.panelsA.tpl.date.part')} value={part} onChange={e => setPart(e.target.value as DatePart)} style={field}>
        {DATE_PARTS.map(p => <option key={p} value={p}>{t(`pg.panelsA.tpl.date.${p}` as MessageKey)}</option>)}
      </select>
      <span style={{ fontSize: 12 }}>{t('pg.panelsA.tpl.date.of')}</span>
      <ColumnSelect columns={dates.length ? dates : columns} value={column} onChange={setColumn} aria={t('pg.panelsA.tpl.date.column')} />
      {!dates.length && <div style={{ fontSize: 11, color: 'var(--muted)', width: '100%' }}>{t('pg.panelsA.tpl.date.none')}</div>}
    </div>
  )
}

function CleanForm({ columns, onBuilt }: FormProps) {
  const t = useT()
  const [column, setColumn] = useState('')
  const [action, setAction] = useState<CleanAction>('TRIM')
  const [find, setFind] = useState('')
  const [replaceWith, setWith] = useState('')
  useEffect(() => { onBuilt(buildClean({ column, action, find, replaceWith })) }, [column, action, find, replaceWith]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
      <select aria-label={t('pg.panelsA.tpl.clean.action')} value={action} onChange={e => setAction(e.target.value as CleanAction)} style={field}>
        {(['TRIM', 'UPPER', 'LOWER', 'REPLACE'] as CleanAction[]).map(a =>
          <option key={a} value={a}>{t(`pg.panelsA.tpl.clean.${a}` as MessageKey)}</option>)}
      </select>
      <span style={{ fontSize: 12 }}>{t('pg.panelsA.tpl.date.of')}</span>
      <ColumnSelect columns={columns} filter={isText} value={column} onChange={setColumn} aria={t('pg.panelsA.tpl.clean.column')} />
      {action === 'REPLACE' && (<>
        <input aria-label={t('pg.panelsA.tpl.clean.find')} placeholder={t('pg.panelsA.tpl.clean.find')} value={find}
          onChange={e => setFind(e.target.value)} style={{ ...field, width: 110 }} />
        <span aria-hidden>{t('pg.panelsA.tpl.arrow')}</span>
        <input aria-label={t('pg.panelsA.tpl.clean.with')} placeholder={t('pg.panelsA.tpl.clean.with')} value={replaceWith}
          onChange={e => setWith(e.target.value)} style={{ ...field, width: 110 }} />
      </>)}
    </div>
  )
}
