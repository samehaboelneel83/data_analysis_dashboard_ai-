/**
 * A request abandoned on purpose (E14): a widget let go of its data because
 * the page closed or a newer request replaced it. Axios rejects an aborted
 * request with `code: 'ERR_CANCELED'`; one that never left the client queue
 * is given the same shape, so callers need one test.
 *
 * Its own module, not api.ts: many tests replace api.ts wholesale, and a
 * check that vanished with the mock would turn every widget error into a
 * crash in those tests.
 */
export function canceledRequest(): Error {
  return Object.assign(new Error('canceled'), { name: 'CanceledError', code: 'ERR_CANCELED' })
}

export const isCanceledRequest = (e: unknown): boolean =>
  (e as { code?: string } | null)?.code === 'ERR_CANCELED'
