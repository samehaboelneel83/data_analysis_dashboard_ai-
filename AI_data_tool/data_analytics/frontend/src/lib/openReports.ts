/**
 * The reports a person has open in this browser tab's session -- SAS's
 * "Opened reports (N)" switcher, so moving between two dashboards is one click
 * instead of a trip back through the list. Session-scoped on purpose: it is a
 * working set, not a history (Home's Recents is the history).
 */
export interface OpenReport { id: number; name: string }

const KEY = 'datalytics:open-reports'
export const MAX_OPEN = 8

export function readOpen(): OpenReport[] {
  try {
    const v = JSON.parse(sessionStorage.getItem(KEY) ?? '[]')
    return Array.isArray(v) ? v.filter(r => r && typeof r.id === 'number' && typeof r.name === 'string') : []
  } catch { return [] }
}

function write(list: OpenReport[]) {
  try { sessionStorage.setItem(KEY, JSON.stringify(list)) } catch { /* private mode: the strip just stays short */ }
}

/** Add (or rename) a report, keeping order of first opening; the oldest drops past MAX_OPEN. */
export function markOpen(r: OpenReport): OpenReport[] {
  const list = readOpen()
  const i = list.findIndex(x => x.id === r.id)
  const next = i >= 0 ? list.map(x => (x.id === r.id ? r : x)) : [...list, r]
  const trimmed = next.length > MAX_OPEN ? next.slice(next.length - MAX_OPEN) : next
  write(trimmed)
  return trimmed
}

export function closeOpen(id: number): OpenReport[] {
  const next = readOpen().filter(x => x.id !== id)
  write(next)
  return next
}
