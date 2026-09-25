import { useEffect, useRef, useState } from 'react'
import { boundarySetsApi, type BoundaryPack, type BoundarySetSummary } from '../../services/api'
import PackTermsConfirm from './PackTermsConfirm'

/**
 * Which shapes a region map draws — and how a new set gets here.
 *
 * The picker and the upload are one component, deliberately. Boundary sets are
 * org reference data, so the tidy home for uploading them is an admin page; but
 * an author discovers they need one at the moment their choropleth comes back
 * blank, and sending them to a page they may not have rights to, in another
 * part of the app, to come back and try again, is how a feature ends up unused.
 * The need and the fix are in the same place.
 *
 * TopoJSON is converted HERE rather than on the server. `topojson-client` is
 * already bundled for the world atlas, so the browser can do it for free; the
 * alternative is a Python TopoJSON dependency and a second validator to keep
 * honest. The endpoint accepts GeoJSON only and says so by name when it is
 * handed a Topology.
 */
export default function BoundarySetPicker({ value, onChange, inheritedName }: {
  value: string
  onChange: (v: string) => void
  /** The set this widget's DIMENSION COLUMN is classified with, when the widget
   *  itself names none. Shown because the empty select reads as "countries"
   *  while the map beside it draws the classified shapes — a control that
   *  disagrees with the picture sends the author to fix the wrong thing. */
  inheritedName?: string | null
}) {
  const [sets, setSets] = useState<BoundarySetSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const [packs, setPacks] = useState<BoundaryPack[]>([])
  const load = () => {
    boundarySetsApi.list().then(setSets).catch(() => setSets([]))
  }
  useEffect(load, [])
  // Packs are optional (a lean offline build ships none), so a failure here
  // simply shows no starter section.
  useEffect(() => {
    Promise.resolve().then(() => boundarySetsApi.packs?.()).then(p => setPacks(Array.isArray(p) ? p : []))
      .catch(() => setPacks([]))
  }, [])
  const installable = packs.filter(p => !(sets ?? []).some(s => s.name === p.name))

  // A pack whose source attaches terms waits here until they are accepted.
  const [pendingTerms, setPendingTerms] = useState<BoundaryPack | null>(null)
  const install = async (pack: BoundaryPack, accepted = false) => {
    if (pack.requires_acceptance && !accepted) { setPendingTerms(pack); return }
    setBusy(true); setError(null)
    try {
      const made = await boundarySetsApi.installPack(pack.id, accepted)
      setPendingTerms(null)
      load()
      onChange(String(made.id))
    } catch (e: unknown) {
      setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? `Could not install ${pack.name}`)
    } finally {
      setBusy(false)
    }
  }

  const chosen = sets?.find(s => String(s.id) === value) ?? null

  const upload = async (file: File) => {
    setBusy(true); setError(null)
    try {
      const text = await file.text()
      let parsed: unknown
      try { parsed = JSON.parse(text) } catch {
        throw new Error('That file is not JSON. GeoJSON and TopoJSON are supported.')
      }
      const geometry = await toGeoJson(parsed)
      // The file name without its extension: a name is required, and asking for
      // one before the file has even been checked is a form nobody fills in.
      const name = file.name.replace(/\.[^.]+$/, '').slice(0, 200) || 'Boundaries'
      const made = await boundarySetsApi.create(name, geometry)
      load()
      onChange(String(made.id))
    } catch (e: unknown) {
      // The endpoint's own refusal names the problem — "Region 4 is a Point,
      // not an area", "No property is present on every region". Anything
      // generic would leave the author guessing at a file they cannot read.
      setError((e as { response?: { data?: { detail?: string } }; message?: string })
        ?.response?.data?.detail ?? (e as Error)?.message
        ?? 'The boundary file could not be read')
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div style={{ marginTop: 10 }}>
      <label htmlFor="cfg-boundary-set" style={{
        display: 'block', fontSize: 11, fontWeight: 700,
        color: 'var(--muted)', marginBottom: 4,
      }}>Boundaries</label>

      {!value && inheritedName && (
        <p style={{ fontSize: 11, color: 'var(--muted)', margin: '0 0 4px' }}>
          Drawing <strong>{inheritedName}</strong>, from the column's geography
          classification. Choosing here overrides it for this widget only.
        </p>
      )}

      <select id="cfg-boundary-set" value={value} style={{ width: '100%' }}
        onChange={e => onChange(e.target.value)}>
        <option value="">Countries (built in)</option>
        {(sets ?? []).map(s => (
          <option key={s.id} value={String(s.id)}>
            {s.name} ({s.feature_count})
          </option>
        ))}
        {/* The widget's own set, when the list has not arrived yet or no longer
            contains it. Without this the select falls back to showing the first
            option -- so a map configured with governorates reads as "Countries"
            while the list loads, and as "Countries" for ever if somebody deleted
            the set out from under it. The config still says otherwise, so the
            display would be lying about what the map draws. */}
        {value && !(sets ?? []).some(s => String(s.id) === value) && (
          <option value={value}>
            {sets === null ? 'Loading…' : `Set ${value} (unavailable)`}
          </option>
        )}
      </select>

      {/* The names in the file, so an author can tell BEFORE building the
          widget whether their column will match — rather than after, from an
          empty map. */}
      {chosen && chosen.sample_names.length > 0 && (
        <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 3 }}>
          Matches on {chosen.key_properties.join(', ')} — e.g.{' '}
          {chosen.sample_names.slice(0, 4).join(', ')}
          {chosen.feature_count > 4 ? '…' : ''}
        </div>
      )}

      {installable.length > 0 && (
        <div data-testid="boundary-packs" style={{ marginTop: 6 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Starter packs:</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {installable.map(p => (
              <button key={p.id} type="button" className="btn btn-sm" disabled={busy}
                title={`${p.description ?? ''}\nSource: ${p.source}. Licence: ${p.license}.`}
                onClick={() => void install(p)}>
                + {p.name} ({p.feature_count}){p.requires_acceptance ? ' · terms' : ''}
              </button>
            ))}
          </div>
          {pendingTerms && (
            <PackTermsConfirm pack={pendingTerms} busy={busy}
              onAccept={() => void install(pendingTerms, true)}
              onCancel={() => setPendingTerms(null)} />
          )}
        </div>
      )}

      <input ref={fileRef} type="file" accept=".json,.geojson,.topojson,application/json"
        aria-label="Boundary file" style={{ display: 'none' }}
        onChange={e => { const f = e.target.files?.[0]; if (f) void upload(f) }} />
      <button className="btn btn-sm" disabled={busy} style={{ marginTop: 6 }}
        onClick={() => fileRef.current?.click()}>
        {busy ? 'Reading…' : 'Upload boundaries…'}
      </button>

      {error && (
        <div role="alert" style={{ fontSize: 11, color: 'var(--danger)', marginTop: 4 }}>
          {error}
        </div>
      )}
    </div>
  )
}

/**
 * A TopoJSON topology becomes a FeatureCollection; GeoJSON passes through.
 *
 * `topojson-client` is imported lazily so a report that never uploads a
 * boundary file does not pay for it on the config panel's chunk — it is already
 * in the charts chunk for the world atlas, and that is where it should stay.
 */
async function toGeoJson(parsed: unknown): Promise<unknown> {
  const doc = parsed as { type?: string; objects?: Record<string, unknown> }
  if (doc?.type !== 'Topology') return parsed
  const objects = Object.values(doc.objects ?? {})
  if (objects.length === 0) {
    throw new Error('That TopoJSON file contains no layers.')
  }
  if (objects.length > 1) {
    // Guessing which layer somebody meant is how the wrong shapes get drawn.
    throw new Error(
      `That TopoJSON file has ${objects.length} layers. Export the one you want `
      + 'as GeoJSON and upload that.')
  }
  const { feature } = await import('topojson-client')
  return feature(doc as never, objects[0] as never)
}
