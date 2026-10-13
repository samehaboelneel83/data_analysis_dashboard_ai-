/**
 * How long an AI step has run, and how long that step usually takes here
 * (the median over this organization's recent analyses, from the server).
 * Plain words beside the "working" line; nothing when nothing is known.
 */
import { useEffect, useState } from 'react'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'

/** The server keeps UTC times without a zone mark. */
function startedAt(since: string): number {
  const t = Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(since) ? since : `${since}Z`)
  return Number.isNaN(t) ? NaN : t
}

function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  return localDigits(`${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`)
}

export default function WaitTime({ since, usual }: { since?: string | null; usual?: number | null }) {
  const t = useT()
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!since) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [since])
  const start = since ? startedAt(since) : NaN
  const ran = Number.isNaN(start) ? null : (now - start) / 1000
  const parts: string[] = []
  if (ran != null) parts.push(t('setup.wait.ran', { time: clock(ran) }))
  if (usual != null && usual > 0) {
    parts.push(usual < 90
      ? t('setup.wait.usualSec', { n: localDigits(String(Math.max(5, Math.round(usual / 5) * 5))) })
      : t('setup.wait.usualMin', { n: localDigits(String(Math.round(usual / 60))) }))
  }
  if (!parts.length) return null
  return <span className="setup-wait" data-testid="setup-wait"> {parts.join(' · ')}</span>
}
