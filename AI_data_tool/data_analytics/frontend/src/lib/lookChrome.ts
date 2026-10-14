/**
 * A dashboard with a dark (or light) look, opened inside an app of the other
 * theme, sat as a dark island in a light frame. While such a dashboard is
 * open the shell follows its look's mode -- side bar, top bar and all -- and
 * goes back to the person's own theme on leaving. Their stored choice is
 * never changed by this, and pressing the theme switch while there puts them
 * back in charge for the rest of the visit (components/Layout).
 */
import { useEffect } from 'react'

export const LOOK_EVENT = 'datalytics:look-mode'
export type LookMode = 'dark' | 'light' | null

export function useLookChrome(mode: string | null | undefined): void {
  useEffect(() => {
    const m: LookMode = mode === 'dark' || mode === 'light' ? mode : null
    window.dispatchEvent(new CustomEvent<LookMode>(LOOK_EVENT, { detail: m }))
    return () => { window.dispatchEvent(new CustomEvent<LookMode>(LOOK_EVENT, { detail: null })) }
  }, [mode])
}
