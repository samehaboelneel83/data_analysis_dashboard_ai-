/**
 * Session recovery for the one builder edit that is not saved instantly.
 *
 * Every builder action is its own server write -- except the settings panel,
 * which batches keystrokes for 600 ms. Close the tab (or crash) inside that
 * window and the last change is gone with no trace. SAS keeps unsaved editor
 * state server-side and offers "Restore previous session"; the local
 * equivalent here is a journal: the pending edit is written before the timer
 * starts and removed the moment the write is sent. Anything still in the
 * journal on the next open is, by construction, an edit that never reached
 * the server.
 *
 * Per-viewer, per-browser convenience state -- so localStorage, and every
 * access is guarded: private windows and blocked storage must never break the
 * builder.
 */
const PREFIX = 'datalytics:pending-widget:'
export const PENDING_MAX_AGE_MS = 24 * 60 * 60 * 1000

export interface PendingEdit { widgetId: number; config: Record<string, unknown>; title: string; at: number }

export function savePending(widgetId: number, config: Record<string, unknown>, title: string): void {
  try { localStorage.setItem(PREFIX + widgetId, JSON.stringify({ widgetId, config, title, at: Date.now() })) } catch { /* storage unavailable */ }
}

export function clearPending(widgetId: number): void {
  try { localStorage.removeItem(PREFIX + widgetId) } catch { /* storage unavailable */ }
}

/** Journal entries for these widgets that are recent enough to offer. */
export function readPending(widgetIds: number[], now: number = Date.now()): PendingEdit[] {
  const out: PendingEdit[] = []
  for (const id of widgetIds) {
    try {
      const raw = localStorage.getItem(PREFIX + id)
      if (!raw) continue
      const e = JSON.parse(raw) as PendingEdit
      if (e && typeof e.at === 'number' && now - e.at <= PENDING_MAX_AGE_MS && e.config && typeof e.config === 'object') out.push(e)
      else clearPending(id)
    } catch { clearPending(id) }
  }
  return out
}
