import { useT } from '../../i18n'

/**
 * Author-placed pins on a coordinate map: "our new depot", "the flood line".
 *
 * A pin is an ANNOTATION, not a row — it is stored on the widget's own config
 * and never touches the data, which is why the renderer keeps it out of
 * cross-filtering and out of the lasso.
 *
 * This editor's real job is telling the author when a pin will not appear. The
 * renderer must drop a pin whose coordinates are not finite numbers (d3 throws
 * on NaN and takes the entire map with it), so without a warning here the only
 * symptom is a pin that never shows up — the exact shape of failure that works
 * for whoever typed a good one and quietly breaks for everyone after.
 */

/**
 * A pin AS EDITED. Coordinates are strings here, and numbers only once saved.
 *
 * This is the pattern every other numeric field in `WidgetConfigPanel` follows
 * (`yMin`, `rankN`, `forecastTarget`, `boundarySetId`) and the reason is worth
 * stating once: a controlled input bound to a parsed number cannot be typed
 * into. Pressing "." after "48" gives "48.", which parses to 48, re-renders as
 * "48", and swallows the keystroke — so 48.85 is unreachable. A leading "-"
 * parses to nothing at all, which rules out every southern latitude and western
 * longitude. The string is what the author is holding; the number is what gets
 * stored.
 */
export interface MapPin {
  label?: string
  lat?: string
  lon?: string
}

/** The stored shape: what the renderer reads out of `config.pins`. */
export interface StoredPin {
  label?: string
  lat?: number | null
  lon?: number | null
}

/** A coordinate as a number, or null while it is not one yet. */
export function pinCoord(raw: string | undefined): number | null {
  const t = (raw ?? '').trim()
  if (t === '') return null
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

/** Editing shape -> stored shape. Half-typed pins are KEPT with a null
 *  coordinate rather than dropped: deleting the row an author is still filling
 *  in would make the editor fight the typing. The renderer skips them. */
export function toStoredPin(pin: MapPin): StoredPin {
  return { label: pin.label, lat: pinCoord(pin.lat), lon: pinCoord(pin.lon) }
}

/** Stored shape -> editing shape, for a widget being reopened. */
export function toDraftPin(pin: StoredPin): MapPin {
  return {
    label: pin.label,
    lat: typeof pin.lat === 'number' ? String(pin.lat) : '',
    lon: typeof pin.lon === 'number' ? String(pin.lon) : '',
  }
}

/** Why this pin will not be drawn (as a message key), or null when it is fine. */
export function pinProblem(pin: MapPin): PinProblem | null {
  const lat = pinCoord(pin.lat)
  const lon = pinCoord(pin.lon)
  if (lat === null || lon === null) {
    return 'pg.modelsMaps.pin.needsBoth'
  }
  // Out of range still projects, just to somewhere meaningless: nothing errors
  // and the author is left doubting the map rather than the number.
  if (lat < -90 || lat > 90) return 'pg.modelsMaps.pin.latRange'
  if (lon < -180 || lon > 180) return 'pg.modelsMaps.pin.lonRange'
  return null
}

type PinProblem = 'pg.modelsMaps.pin.needsBoth' | 'pg.modelsMaps.pin.latRange' | 'pg.modelsMaps.pin.lonRange'

const cell: React.CSSProperties = {
  fontSize: 11, padding: '3px 5px', border: '1px solid var(--border)',
  borderRadius: 4, background: 'var(--surface)', color: 'var(--text)', width: '100%',
}

export default function MapPinsEditor({ value, onChange }: {
  value: MapPin[]
  onChange: (pins: MapPin[]) => void
}) {
  const t = useT()
  const pins = value ?? []

  const patch = (i: number, next: Partial<MapPin>) =>
    onChange(pins.map((p, j) => (j === i ? { ...p, ...next } : p)))

  return (
    <div style={{ marginBottom: 12 }}>
      <label style={{ display: 'block', fontSize: 10, fontWeight: 700, color: 'var(--muted)', marginBottom: 4 }}>
        {t('pg.modelsMaps.pin.pins')}
      </label>

      {pins.length === 0 && (
        <p style={{ fontSize: 11, color: 'var(--muted)', margin: '0 0 6px' }}>{t('pg.modelsMaps.pin.empty')}</p>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {pins.map((p, i) => {
          const name = p.label || t('pg.modelsMaps.pin.fallbackName', { n: i + 1 })
          const problem = pinProblem(p)
          return (
            <div key={i} style={{
              border: '1px solid var(--border)', borderRadius: 6, padding: 6,
              display: 'flex', flexDirection: 'column', gap: 4,
            }}>
              <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                <input value={p.label ?? ''} placeholder={t('pg.modelsMaps.pin.label')}
                  aria-label={t('pg.modelsMaps.pin.labelFor', { name })}
                  onChange={e => patch(i, { label: e.target.value })}
                  style={{ ...cell, flex: 1 }} />
                <button onClick={() => onChange(pins.filter((_, j) => j !== i))}
                  aria-label={t('pg.modelsMaps.pin.remove', { name })} title={t('pg.modelsMaps.pin.remove', { name })}
                  style={{ background: 'none', border: 'none', color: 'var(--muted)',
                    cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: '0 2px' }}>
                  ×
                </button>
              </div>
              <div style={{ display: 'flex', gap: 4 }}>
                <input value={p.lat ?? ''} placeholder={t('pg.modelsMaps.ml.latitude')} inputMode="decimal"
                  aria-label={t('pg.modelsMaps.pin.latFor', { name })}
                  onChange={e => patch(i, { lat: e.target.value })}
                  style={{ ...cell, flex: 1 }} />
                <input value={p.lon ?? ''} placeholder={t('pg.modelsMaps.ml.longitude')} inputMode="decimal"
                  aria-label={t('pg.modelsMaps.pin.lonFor', { name })}
                  onChange={e => patch(i, { lon: e.target.value })}
                  style={{ ...cell, flex: 1 }} />
              </div>
              {problem && (
                <p style={{ fontSize: 10, color: 'var(--danger)', margin: 0 }}>{t(problem)}</p>
              )}
            </div>
          )
        })}
      </div>

      <button onClick={() => onChange([...pins, { label: t('pg.modelsMaps.pin.defaultLabel', { n: pins.length + 1 }), lat: '', lon: '' }])}
        className="btn btn-ghost btn-sm"
        style={{ fontSize: 10, padding: '3px 8px', marginTop: 6 }}>
        {t('pg.modelsMaps.pin.add')}
      </button>
    </div>
  )
}
