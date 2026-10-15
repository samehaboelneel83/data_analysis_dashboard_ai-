import { boundarySetsApi } from '../../../services/api'

/**
 * Where this page fetches boundary shapes from.
 *
 * The signed-in `GET /boundary-sets/{id}` by default. A guest share link or an
 * embed has no session, so that route 401s -- and the app's "session expired"
 * handler used to send the whole guest page to /login (QA F2-55). Those pages
 * install a loader that goes through their own surface instead.
 *
 * Its own module, deliberately, NOT part of regionSetCache: that one imports the
 * ~740 kB world atlas, and the shared/embed pages must not import it statically
 * (atlasLazy.test.ts guards this). This file imports nothing but the API client.
 */
export type BoundarySetPayload = {
  geometry: Record<string, unknown> | { features?: unknown[] } | null | undefined
  key_properties?: string[] | null
}
export type BoundarySetLoader = (id: number) => Promise<BoundarySetPayload>

const signedIn: BoundarySetLoader = id => boundarySetsApi.get(id) as Promise<BoundarySetPayload>
let current: BoundarySetLoader = signedIn
const listeners = new Set<() => void>()

/** Install a loader for this page; `null` restores the signed-in route. */
export function setRegionSetLoader(fn: BoundarySetLoader | null) {
  current = fn ?? signedIn
  // A set fetched through one route must not be served as if from the other.
  listeners.forEach(l => l())
}

export function boundarySetLoader(): BoundarySetLoader {
  return current
}

/** For regionSetCache: drop its cache whenever the source changes. */
export function onRegionSetLoaderChange(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}
