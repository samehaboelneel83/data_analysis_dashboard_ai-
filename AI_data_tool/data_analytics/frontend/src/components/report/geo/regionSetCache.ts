import { useEffect, useState } from 'react'
import { boundarySetsApi } from '../../../services/api'
import { COUNTRY_SET, buildRegionSet, type RegionSet } from './worldGeometry'

/**
 * Fetch a boundary set once per page, not once per widget.
 *
 * A boundary file is megabytes of polygons. Three choropleths on a page all
 * drawing the same governorates must not fetch it three times, and React's
 * StrictMode double-mounts every effect in development — so the cache holds the
 * PROMISE, not the result. A second caller during the first flight joins it
 * rather than starting another.
 *
 * Module-level and never evicted, deliberately: this is reference data that
 * does not change while a page is open, and the alternative — a cache keyed to
 * a component — is the same fetch again on every tab switch.
 */
const cache = new Map<number, Promise<RegionSet>>()

export function loadRegionSet(id: number): Promise<RegionSet> {
  const hit = cache.get(id)
  if (hit) return hit
  // Through Promise.resolve so even a synchronous failure lands in the catch.
  const flight = Promise.resolve().then(() => boundarySetsApi.get(id))
    .then(d => buildRegionSet(d.geometry, d.key_properties ?? []))
    .catch(err => {
      // A failed fetch must not be cached: the set may be there on the next
      // render, and a poisoned entry would make one network blip permanent for
      // the life of the page.
      cache.delete(id)
      throw err
    })
  cache.set(id, flight)
  return flight
}

/** Forget one set, after its pins changed, so the next load sees them. Maps
 *  already on screen keep the shapes they have until they re-mount. */
export function invalidateRegionSet(id: number) {
  cache.delete(id)
}

/** Test-only: the cache is module state, so it survives between tests. */
export function _clearRegionSetCache() {
  cache.clear()
}

/**
 * The region set a widget should draw, and whether it is still arriving.
 *
 * Falls back to countries whenever no set is chosen — which is also what a map
 * shows while a set loads, so the first frame is a world map rather than a
 * blank tile. `loading` is exposed so the renderer can say so instead of
 * briefly showing every row as unmatched, which reads as broken data.
 */
export function useRegionSet(id: number | null | undefined, version = 0): {
  set: RegionSet; loading: boolean; error: string | null
} {
  const [state, setState] = useState<{ set: RegionSet; loading: boolean; error: string | null }>(
    () => ({ set: COUNTRY_SET, loading: id != null, error: null }))

  useEffect(() => {
    if (id == null) {
      setState({ set: COUNTRY_SET, loading: false, error: null })
      return
    }
    let alive = true
    setState(s => ({ ...s, loading: true, error: null }))
    loadRegionSet(id)
      .then(set => { if (alive) setState({ set, loading: false, error: null }) })
      .catch(() => {
        // Countries, not an empty set: an empty one would report every row as
        // unmatched, which blames the data for a failed request.
        if (alive) setState({
          set: COUNTRY_SET, loading: false,
          error: 'The boundary set could not be loaded',
        })
      })
    // Guards the STALE case, not the double-mount: switching a widget from set
    // A to set B while A is in flight must not paint A's shapes afterwards.
    return () => { alive = false }
  }, [id, version])

  return state
}
