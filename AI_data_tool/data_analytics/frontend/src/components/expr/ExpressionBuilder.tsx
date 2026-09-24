import { useRef, useState } from 'react'
import type { DatasetColumn } from '../../services/api'
import type { SimpleConditionRow, SimpleExprState, SimpleJoiner, SimpleOperator, SimpleValueKind } from '../../lib/simpleExpr'
import { FUNCTION_ARITY, compileSimple, emptyConditionRow } from '../../lib/simpleExpr'

const SIMPLE_OPERATORS: { value: SimpleOperator; label: string }[] = [
  { value: 'eq', label: '=' }, { value: 'ne', label: '≠' },
  { value: 'gt', label: '>' }, { value: 'gte', label: '≥' },
  { value: 'lt', label: '<' }, { value: 'lte', label: '≤' },
  { value: 'isnull', label: 'is blank' }, { value: 'notnull', label: 'is not blank' },
]

/**
 * Shared codeless expression-authoring widget: a textarea plus click-to-insert-at-
 * cursor palettes for Attributes / Functions / Operators. Extracted from
 * `CalcColumnsPanel`'s `BuilderModal` (the best UX we had) so `CalcColumnsPanel`,
 * `MeasuresPanel` and the dataset filter builder all share one implementation
 * instead of drifting copies.
 *
 * Deliberately does NOT own the surrounding chrome (name field, format section,
 * save/cancel footer) — each caller keeps that, since it differs per use. `onTest`
 * is optional: pass it to get a built-in Test button + result banner (used by the
 * dataset filter, which had none before); callers that already render their own
 * Test/Preview UI (CalcColumns, Measures) simply don't pass it.
 */

export interface PaletteItem { label: string; snippet: string; back?: number; hint?: string }
export interface PaletteGroup { label: string; color?: string; items: PaletteItem[] }
export interface AttributeExtra { name: string; icon?: string }

// System parameters — always available, expand server-side via apply_user_context.
export const SYSTEM_GROUP: PaletteGroup = {
  label: 'System', color: '#94a3b8',
  items: [
    { label: 'USEREMAIL()', snippet: 'USEREMAIL()', back: 0, hint: 'Current user email' },
    { label: 'USERID()',    snippet: 'USERID()',    back: 0, hint: 'Current user id' },
    { label: 'ORGID()',     snippet: 'ORGID()',     back: 0, hint: 'Current organization id' },
    { label: 'ORGNAME()',   snippet: 'ORGNAME()',   back: 0, hint: 'Current organization name' },
  ],
}

const DEFAULT_OP_GROUPS: { label: string; items: PaletteItem[] }[] = [
  { label: 'Arithmetic', items: [
    { label: '+', snippet: ' + ' }, { label: '-', snippet: ' - ' },
    { label: '*', snippet: ' * ' }, { label: '/', snippet: ' / ' },
    { label: '**', snippet: ' ** ' }, { label: '%', snippet: ' % ' },
  ]},
  { label: 'Comparison', items: [
    { label: '==', snippet: ' == ' }, { label: '!=', snippet: ' != ' },
    { label: '>', snippet: ' > ' }, { label: '<', snippet: ' < ' },
    { label: '>=', snippet: ' >= ' }, { label: '<=', snippet: ' <= ' },
  ]},
  { label: 'Logical', items: [
    { label: 'and', snippet: ' and ' }, { label: 'or', snippet: ' or ' },
    { label: 'not', snippet: ' not ' }, { label: '(', snippet: '(' }, { label: ')', snippet: ')' },
  ]},
]

// Wrap column name in backticks if it contains spaces or starts with a digit
const colRef = (name: string) => (/\s/.test(name) || /^\d/.test(name) ? `\`${name}\`` : name)

export interface ExpressionBuilderProps {
  columns: DatasetColumn[]
  functionsCatalog: PaletteGroup[]
  value: string
  onChange: (v: string) => void
  onTest?: (expr: string) => Promise<unknown>
  renderTestResult?: (result: unknown) => React.ReactNode
  extraPaletteGroups?: PaletteGroup[]
  /** Calculated columns / measures already defined on the dataset — shown in the
   *  Attributes pane marked with ƒx, same as CalcColumnsPanel's original modal. */
  attributeExtras?: AttributeExtra[]
  opGroups?: { label: string; items: PaletteItem[] }[]
  /** 'panels' = the original 3-box grid (CalcColumns modal, dataset filter).
   *  'flat' = wrapped chip rows matching MeasuresPanel's compact inline layout. */
  layout?: 'panels' | 'flat'
  /** Id for the expression textarea, so a caller's own <label htmlFor> binds to
   *  it. Without one the textarea has no accessible name at all: every consumer
   *  renders its own heading above this component, and a heading is not a label
   *  -- a screen reader reaches the field and announces nothing. Optional so the
   *  existing callers are unchanged. */
  textareaId?: string
  rows?: number
  placeholder?: string
  testLabel?: string
  /** Which mode the Simple|Advanced toggle starts in. Both C1 consumers (CalcColumns,
   *  Measures) keep 'advanced' but still show the toggle; the dataset filter (C2's
   *  primary use case) defaults to 'simple'. */
  defaultMode?: 'simple' | 'advanced'
}

const SYSTEM_VALUE_ITEMS = SYSTEM_GROUP.items // USEREMAIL()/USERID()/ORGID()/ORGNAME()

export default function ExpressionBuilder({
  columns, functionsCatalog, value, onChange, onTest, renderTestResult,
  extraPaletteGroups = [], attributeExtras = [], opGroups = DEFAULT_OP_GROUPS,
  layout = 'panels', textareaId, rows = 3, placeholder, testLabel = 'Test',
  defaultMode = 'advanced',
}: ExpressionBuilderProps) {
  const [openCats, setOpenCats] = useState<Record<string, boolean>>({})
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<unknown>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)

  // ── Simple mode (C2) ──────────────────────────────────────────────────────
  // Text (`value`) stays the source of truth throughout. `simpleState` only tracks
  // what the Simple UI is currently showing; `lastCompiled` is the text the builder
  // itself last produced, so re-entering Simple can tell a builder-generated
  // expression apart from a hand-edited one by exact string match — never by
  // parsing `value` back into rows.
  const [mode, setMode] = useState<'simple' | 'advanced'>(defaultMode)
  const [simpleState, setSimpleState] = useState<SimpleExprState>({
    rows: [emptyConditionRow(columns[0]?.name ?? '')],
    joiner: 'and',
  })
  const [lastCompiled, setLastCompiled] = useState('')
  const builderGenerated = value === lastCompiled

  const commitSimple = (next: SimpleExprState) => {
    setSimpleState(next)
    const text = compileSimple(next)
    setLastCompiled(text)
    onChange(text)
  }

  const startOver = () => {
    const next: SimpleExprState = { rows: [emptyConditionRow(columns[0]?.name ?? '')], joiner: 'and' }
    commitSimple(next)
  }

  const allFuncCats = [...functionsCatalog, ...extraPaletteGroups, SYSTEM_GROUP]
  const isOpen = (label: string) => openCats[label] ?? true
  const toggleCat = (label: string) => setOpenCats(p => ({ ...p, [label]: !isOpen(label) }))

  const insert = (snippet: string, back = 0) => {
    const ta = taRef.current
    const start = ta?.selectionStart ?? value.length
    const end = ta?.selectionEnd ?? value.length
    const next = value.slice(0, start) + snippet + value.slice(end)
    const cursor = start + snippet.length - back
    onChange(next)
    setTestResult(null)
    requestAnimationFrame(() => {
      ta?.focus()
      ta?.setSelectionRange(cursor, cursor)
    })
  }

  const insertCol = (name: string) => insert(colRef(name))

  const runTest = async () => {
    if (!onTest || !value.trim()) return
    setTesting(true)
    try {
      setTestResult(await onTest(value.trim()))
    } finally {
      setTesting(false)
    }
  }

  const panelHd: React.CSSProperties = {
    fontSize: 10, fontWeight: 700, color: 'var(--muted)',
    textTransform: 'uppercase', letterSpacing: '.06em',
    padding: '0 0 5px', marginBottom: 4, borderBottom: '1px solid var(--border)',
  }
  const chip: React.CSSProperties = {
    display: 'block', width: '100%', textAlign: 'start',
    padding: '3px 7px', margin: '1px 0', border: 'none',
    borderRadius: 4, cursor: 'pointer', fontSize: 11,
    fontFamily: 'var(--mono)', background: 'transparent', color: 'var(--text)',
  }
  const flatChip: React.CSSProperties = {
    fontSize: 9.5, padding: '2px 6px', background: 'var(--surface2)',
    border: '1px solid var(--border)', borderRadius: 4, cursor: 'pointer', color: 'var(--text)',
  }

  const attributeButtons = (
    <>
      {columns.map(col => (
        <button key={col.name} style={layout === 'flat' ? flatChip : chip} title={`${col.name} (${col.dtype})`}
          onClick={() => insertCol(col.name)}>
          <span>{col.name}</span>
          {layout === 'panels' && <span style={{ color: 'var(--muted)', fontSize: 9, marginInlineStart: 5 }}>{col.dtype}</span>}
        </button>
      ))}
      {attributeExtras.map(extra => (
        <button key={extra.name} style={layout === 'flat' ? flatChip : chip} title={`ƒx ${extra.name}`}
          onClick={() => insertCol(extra.name)}>
          <span style={{ color: 'var(--accent)', marginInlineEnd: 4 }}>{extra.icon ?? 'ƒx'}</span>
          <span>{extra.name}</span>
        </button>
      ))}
    </>
  )

  const functionGroups = allFuncCats.map(cat => (
    <div key={cat.label} style={{ marginBottom: layout === 'flat' ? 5 : 4 }}>
      {layout === 'panels' ? (
        <button onClick={() => toggleCat(cat.label)}
          style={{ display: 'flex', alignItems: 'center', gap: 5, width: '100%',
            background: 'none', border: 'none', cursor: 'pointer', padding: '3px 0',
            fontSize: 10, fontWeight: 700, color: cat.color ?? 'var(--muted)',
            textTransform: 'uppercase', letterSpacing: '.06em' }}>
          <span style={{ fontSize: 9 }}>{isOpen(cat.label) ? '▼' : '▶'}</span>
          {cat.label}
        </button>
      ) : (
        <div style={{ fontSize: 8.5, fontWeight: 700, color: cat.color ?? 'var(--muted)',
          textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 3 }}>{cat.label}</div>
      )}
      {(layout === 'flat' || isOpen(cat.label)) && (
        <div style={layout === 'flat' ? { display: 'flex', flexWrap: 'wrap', gap: 3 } : undefined}>
          {cat.items.map(fn => (
            <button key={fn.label} style={layout === 'flat' ? { ...flatChip, border: `1px solid ${cat.color ?? 'var(--border)'}55` } : chip}
              title={fn.hint} onClick={() => insert(fn.snippet, fn.back ?? 0)}>
              {fn.label}
            </button>
          ))}
        </div>
      )}
    </div>
  ))

  const operatorButtons = layout === 'flat'
    ? (
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
        {opGroups.flatMap(g => g.items).map(op => (
          <button key={op.label} onClick={() => insert(op.snippet, op.back ?? 0)}
            style={{ ...flatChip, fontFamily: 'var(--mono)' }}>{op.label}</button>
        ))}
      </div>
    )
    : opGroups.map(grp => (
      <div key={grp.label} style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--muted)',
          textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 5 }}>{grp.label}</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {grp.items.map(op => (
            <button key={op.label} onClick={() => insert(op.snippet, op.back ?? 0)} title={op.hint}
              style={{ padding: '4px 9px', border: '1px solid var(--border)', borderRadius: 5,
                cursor: 'pointer', fontSize: 12, fontFamily: 'var(--mono)', fontWeight: 600,
                background: 'var(--surface)', color: 'var(--text)' }}>
              {op.label}
            </button>
          ))}
        </div>
      </div>
    ))

  // ── Simple mode row editing ─────────────────────────────────────────────
  const updateRow = (i: number, patch: Partial<SimpleConditionRow>) => {
    const nextRows = simpleState.rows.map((r, j) => (j === i && r.type === 'condition' ? { ...r, ...patch } : r))
    commitSimple({ ...simpleState, rows: nextRows })
  }
  const updateFnArgs = (i: number, args: string[]) => {
    const nextRows = simpleState.rows.map((r, j) => (j === i && r.type === 'function' ? { ...r, args } : r))
    commitSimple({ ...simpleState, rows: nextRows })
  }
  const setFnKind = (i: number, fn: string) => {
    const argSlots = FUNCTION_ARITY[fn] ?? ['arguments (comma-separated)']
    const nextRows = simpleState.rows.map((r, j) =>
      j === i && r.type === 'function' ? { type: 'function' as const, fn, args: new Array(argSlots.length).fill('') } : r)
    commitSimple({ ...simpleState, rows: nextRows })
  }
  const removeRow = (i: number) => commitSimple({ ...simpleState, rows: simpleState.rows.filter((_, j) => j !== i) })
  const addConditionRow = () => commitSimple({ ...simpleState, rows: [...simpleState.rows, emptyConditionRow(columns[0]?.name ?? '')] })
  const addFunctionRow = () => {
    const fn = Object.keys(FUNCTION_ARITY)[0] ?? ''
    commitSimple({ ...simpleState, rows: [...simpleState.rows, { type: 'function', fn, args: new Array((FUNCTION_ARITY[fn] ?? ['']).length).fill('') }] })
  }
  const setJoiner = (joiner: SimpleJoiner) => commitSimple({ ...simpleState, joiner })

  const rowInp: React.CSSProperties = { fontSize: 11, padding: '4px 6px',
    background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' }

  const simpleRowsEditor = (
    <div>
      {simpleState.rows.map((row, i) => (
        <div key={i} style={{ display: 'flex', flexWrap: 'wrap', gap: 5, alignItems: 'center',
          background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6, padding: 6, marginBottom: 5 }}>
          {i > 0 && (
            <select aria-label="Join with" value={simpleState.joiner} onChange={e => setJoiner(e.target.value as SimpleJoiner)}
              style={{ ...rowInp, fontWeight: 700, width: 62 }}>
              <option value="and">AND</option>
              <option value="or">OR</option>
            </select>
          )}
          {row.type === 'condition' ? (
            <>
              <select aria-label="Column" value={row.column} onChange={e => updateRow(i, { column: e.target.value })} style={rowInp}>
                {columns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
              </select>
              <select aria-label="Operator" value={row.op} onChange={e => updateRow(i, { op: e.target.value as SimpleOperator })} style={rowInp}>
                {SIMPLE_OPERATORS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              {row.op !== 'isnull' && row.op !== 'notnull' && (
                <>
                  <select aria-label="Value type" value={row.valueKind}
                    onChange={e => updateRow(i, { valueKind: e.target.value as SimpleValueKind, value: '' })} style={rowInp}>
                    <option value="literal">Value</option>
                    <option value="column">Column</option>
                    <option value="system">Parameter</option>
                  </select>
                  {row.valueKind === 'literal' && (
                    <input aria-label="Value" value={row.value} onChange={e => updateRow(i, { value: e.target.value })}
                      style={{ ...rowInp, flex: 1, minWidth: 80 }} />
                  )}
                  {row.valueKind === 'column' && (
                    <select aria-label="Value" value={row.value} onChange={e => updateRow(i, { value: e.target.value })} style={rowInp}>
                      <option value="">Select column…</option>
                      {columns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                    </select>
                  )}
                  {row.valueKind === 'system' && (
                    <select aria-label="Value" value={row.value} onChange={e => updateRow(i, { value: e.target.value })} style={rowInp}>
                      <option value="">Select parameter…</option>
                      {SYSTEM_VALUE_ITEMS.map(it => <option key={it.snippet} value={it.snippet}>{it.hint}</option>)}
                    </select>
                  )}
                </>
              )}
            </>
          ) : (
            <>
              <select aria-label="Function" value={row.fn} onChange={e => setFnKind(i, e.target.value)} style={rowInp}>
                {Object.keys(FUNCTION_ARITY).map(fn => <option key={fn} value={fn}>{fn}</option>)}
              </select>
              {(FUNCTION_ARITY[row.fn] ?? ['arguments (comma-separated)']).map((label, ai) => (
                <input key={ai} aria-label={label} placeholder={label} value={row.args[ai] ?? ''}
                  onChange={e => { const args = [...row.args]; args[ai] = e.target.value; updateFnArgs(i, args) }}
                  style={{ ...rowInp, width: 90 }} />
              ))}
            </>
          )}
          <button aria-label="Remove row" onClick={() => removeRow(i)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', fontSize: 14, marginInlineStart: 'auto' }}>×</button>
        </div>
      ))}
      <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
        <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }} onClick={addConditionRow}>+ Condition</button>
        <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }} onClick={addFunctionRow}>+ Function</button>
      </div>
      <div style={{ fontFamily: 'var(--mono)', fontSize: 11, padding: '6px 8px', background: 'var(--surface2)',
        border: '1px solid var(--border)', borderRadius: 5, color: 'var(--muted)', marginBottom: 6, minHeight: 16 }}>
        {value || <span style={{ opacity: .6 }}>(empty expression)</span>}
      </div>
    </div>
  )

  const simplePane = builderGenerated || value.trim() === ''
    ? simpleRowsEditor
    : (
      <div style={{ fontSize: 11, color: 'var(--muted)', padding: '10px 8px', background: 'var(--surface2)',
        border: '1px solid var(--border)', borderRadius: 6, marginBottom: 8 }}>
        <div style={{ marginBottom: 8 }}>hand-written expression — switching to Simple starts over</div>
        <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }} onClick={startOver}>Start over</button>
      </div>
    )

  return (
    <div>
      <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
        <button className={mode === 'simple' ? 'btn btn-primary btn-sm' : 'btn btn-ghost btn-sm'}
          style={{ fontSize: 11 }} aria-pressed={mode === 'simple'} onClick={() => setMode('simple')}>Simple</button>
        <button className={mode === 'advanced' ? 'btn btn-primary btn-sm' : 'btn btn-ghost btn-sm'}
          style={{ fontSize: 11 }} aria-pressed={mode === 'advanced'} onClick={() => setMode('advanced')}>Advanced</button>
      </div>

      {mode === 'simple' && simplePane}

      {mode === 'advanced' && (
      <textarea ref={taRef} id={textareaId} value={value} rows={rows}
        placeholder={placeholder}
        onChange={e => { onChange(e.target.value); setTestResult(null) }}
        style={{ width: '100%', fontFamily: 'var(--mono)', fontSize: layout === 'flat' ? 11.5 : 12,
          padding: '8px 10px', resize: 'vertical', lineHeight: 1.6, marginBottom: 6,
          boxSizing: 'border-box' }} />
      )}

      {mode === 'advanced' && (layout === 'panels' ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 8, minHeight: 220 }}>
          <div style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 7,
            padding: 10, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={panelHd}>Attributes</div>
            <div style={{ flex: 1, overflowY: 'auto' }}>{attributeButtons}</div>
          </div>
          <div style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 7,
            padding: 10, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={panelHd}>Functions</div>
            <div style={{ flex: 1, overflowY: 'auto' }}>{functionGroups}</div>
          </div>
          <div style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 7,
            padding: 10, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={panelHd}>Operators</div>
            <div style={{ flex: 1, overflowY: 'auto' }}>{operatorButtons}</div>
          </div>
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginBottom: 6 }}>{attributeButtons}</div>
          {functionGroups}
          <div style={{ marginBottom: 8 }}>{operatorButtons}</div>
        </>
      ))}

      {onTest && (
        <div style={{ marginTop: 8 }}>
          <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }} disabled={testing || !value.trim()} title={!value.trim() ? 'Write an expression first' : undefined} onClick={runTest}>
            {testing ? 'Testing…' : testLabel}
          </button>
          {testResult != null && (
            <div style={{ marginTop: 6 }}>
              {renderTestResult ? renderTestResult(testResult) : <pre style={{ fontSize: 10 }}>{JSON.stringify(testResult)}</pre>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
