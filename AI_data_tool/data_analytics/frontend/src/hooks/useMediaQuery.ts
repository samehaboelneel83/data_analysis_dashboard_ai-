import { useEffect, useState } from 'react'

// Shared breakpoint queries — use these instead of inlining pixel values so every
// "narrow viewport" check in the app agrees on the same thresholds.
export const MOBILE_QUERY = '(max-width: 767px)'
export const NARROW_DESKTOP_QUERY = '(max-width: 1200px)'

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)

  useEffect(() => {
    const mql = window.matchMedia(query)
    setMatches(mql.matches)
    const onChange = () => setMatches(mql.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [query])

  return matches
}
