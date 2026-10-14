import { useState } from 'react'
import { MODES, PRESETS, UNITS, presetOf, specProblem, usesN,
  type RelativeAnchor, type RelativeMode, type RelativeSpec, type RelativeUnit } from '../../lib/relativeDates'
import { useT, type MessageKey, type TranslateFn } from '../../i18n'

const MODE_KEY: Record<RelativeMode, MessageKey> = {
  last: 'pg.panelsB.rd.modeLast', rolling: 'pg.panelsB.rd.modeRolling', to_date: 'pg.panelsB.rd.modeToDate',
  this: 'pg.panelsB.rd.modeThis', previous: 'pg.panelsB.rd.modePrevious',
}

/** lib/relativeDates' describeSpec, in the reader's language: one full
 *  template per mode and unit, the count through the plural rules. */
function describeSpecT(s: RelativeSpec, t: TranslateFn): string {
  const n = Number(s.n ?? 1)
  const u = s.unit
  let label: string
  switch (s.mode) {
    case 'to_date': label = u === 'day' ? t('pg.panelsB.rd.today') : t(`pg.panelsB.rd.toDate.${u}`); break
    case 'this': label = u === 'day' ? t('pg.panelsB.rd.today') : t(`pg.panelsB.rd.this.${u}`); break
    case 'previous': label = u === 'day' ? t('pg.panelsB.rd.yesterday') : t(`pg.panelsB.rd.prev.${u}`); break
    case 'rolling': label = t(`pg.panelsB.rd.rolling.${u}`, { n }); break
    default:
      label = u === 'day' ? t('pg.panelsB.rd.last.day', { n })
        : t(s.include_current ? `pg.panelsB.rd.lastIncl.${u}` : `pg.panelsB.rd.lastFull.${u}`, { n })
  }
  return t(s.anchor === 'today' ? 'pg.panelsB.rd.descToday' : 'pg.panelsB.rd.descLatest', { label })
}

interface Props {
  value: RelativeSpec
  onChange: (next: RelativeSpec) => void
  /** Prefix for accessible names, e.g. "Filter 2". */
  label: string
  compact?: boolean
}

/** Relative date picker: a preset list (one click for the common windows) and,
 *  under "Custom…", the parts. The anchor is always its own visible choice —
 *  never implied — and the sentence under it says exactly what will be kept. */
export default function RelativeDateEditor({ value, onChange, label, compact }: Props) {
  // "Custom…" is a mode of the editor, not of the spec: choosing it on a spec
  // that matches a preset must still open the parts.
  const t = useT()
  const [customOpen, setCustomOpen] = useState(false)
  const preset = customOpen ? 'custom' : presetOf(value)
  const problem = specProblem(value)
  const fs = compact ? 10 : 11
  const set = (patch: Partial<RelativeSpec>) => onChange({ ...value, ...patch })
  return (
    <div data-testid="relative-date-editor" style={{ display: 'flex', flexDirection: 'column', gap: 4, width: '100%' }}>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        <select aria-label={t('pg.panelsB.rd.period', { label })} value={preset} style={{ fontSize: fs, flex: 1, minWidth: 110 }}
          onChange={e => {
            const p = PRESETS.find(x => x.id === e.target.value)
            setCustomOpen(!p)
            if (p) onChange({ ...p.spec, anchor: value.anchor })
          }}>
          {PRESETS.map(p => <option key={p.id} value={p.id}>{t(`bc.shell.preset.${p.id}` as MessageKey)}</option>)}
          <option value="custom">{t('pg.panelsB.rd.custom')}</option>
        </select>
        <select aria-label={t('pg.panelsB.rd.countedFrom', { label })} value={value.anchor} style={{ fontSize: fs }}
          onChange={e => set({ anchor: e.target.value as RelativeAnchor })}>
          <option value="data_max">{t('pg.panelsB.rd.fromLatest')}</option>
          <option value="today">{t('pg.panelsB.rd.fromToday')}</option>
        </select>
      </div>
      {preset === 'custom' && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center' }}>
          <select aria-label={t('pg.panelsB.rd.mode', { label })} value={value.mode} style={{ fontSize: fs }}
            onChange={e => set({ mode: e.target.value as RelativeMode })}>
            {MODES.map(m => <option key={m.value} value={m.value}>{t(MODE_KEY[m.value])}</option>)}
          </select>
          {usesN(value.mode) && (
            <input aria-label={t('pg.panelsB.rd.nPeriods', { label })} type="number" min={1} max={1000}
              value={value.n ?? ''} style={{ fontSize: fs, width: 56 }}
              onChange={e => set({ n: e.target.value === '' ? undefined : Number(e.target.value) })} />
          )}
          <select aria-label={t('pg.panelsB.rd.unit', { label })} value={value.unit} style={{ fontSize: fs }}
            onChange={e => set({ unit: e.target.value as RelativeUnit })}>
            {UNITS.map(u => <option key={u} value={u}>{t(usesN(value.mode) ? `pg.panelsB.rd.us.${u}` : `pg.panelsB.rd.u.${u}`)}</option>)}
          </select>
          {value.mode === 'last' && value.unit !== 'day' && (
            <label style={{ fontSize: fs, display: 'inline-flex', gap: 3, alignItems: 'center' }}>
              <input type="checkbox" checked={!!value.include_current}
                onChange={e => set({ include_current: e.target.checked })} />
              {t(`pg.panelsB.rd.incl.${value.unit as Exclude<RelativeUnit, 'day'>}`)}
            </label>
          )}
        </div>
      )}
      <div role={problem ? 'alert' : undefined} style={{ fontSize: 11, color: problem ? 'var(--danger)' : 'var(--muted)' }}>
        {problem ? t('pg.panelsB.rd.problem') : describeSpecT(value, t)}
      </div>
    </div>
  )
}
