import { useCallback, useEffect, useState } from 'react'

/**
 * "Always show details" (guided setup, decision D2).
 *
 * Every plain-language summary hides the full report behind its own
 * Show details. Developers who always want the full report can turn this on
 * once instead of clicking each time. Stored per user in localStorage, like
 * the reading direction and language (see DirectionContext for why reader
 * preferences do not get a server column).
 */
const KEY = 'datalytics.alwaysShowDetails'
const EVENT = 'datalytics:details-preference'

export function readAlwaysShowDetails(): boolean {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    // Private windows and blocked site-data throw on access.
    return false
  }
}

export function writeAlwaysShowDetails(on: boolean): void {
  try {
    if (on) localStorage.setItem(KEY, '1')
    else localStorage.removeItem(KEY)
  } catch { /* the preference simply does not persist */ }
  // Summaries already on screen follow the change without a reload.
  window.dispatchEvent(new CustomEvent(EVENT, { detail: on }))
}

export function useAlwaysShowDetails(): [boolean, (on: boolean) => void] {
  const [on, setOn] = useState(readAlwaysShowDetails)
  useEffect(() => {
    const sync = (e: Event) => setOn(Boolean((e as CustomEvent<boolean>).detail))
    window.addEventListener(EVENT, sync)
    return () => window.removeEventListener(EVENT, sync)
  }, [])
  const set = useCallback((value: boolean) => writeAlwaysShowDetails(value), [])
  return [on, set]
}
