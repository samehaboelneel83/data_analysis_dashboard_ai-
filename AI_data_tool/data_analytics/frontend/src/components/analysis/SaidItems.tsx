import { useT } from '../../i18n'
import { sayText, type SaidI18n } from '../../lib/readbackText'
import { kiSentence } from './KeyInfluencersResult'

/** The server's footnotes as list items, in the reader's language.
 *
 *  A line that came with its key (`*_i18n`, backend `readback._s`) is said from
 *  the catalogue; one of the older fixed sentences is recognised by its words;
 *  anything else is shown as sent. */
export default function SaidItems({ texts, i18n }: { texts?: string[] | null; i18n?: (SaidI18n | null)[] | null }) {
  const t = useT()
  return <>{(texts ?? []).map((c, i) => <li key={i} dir="auto">{i18n?.[i] ? sayText(t, c, i18n[i]) : kiSentence(c, t)}</li>)}</>
}

/** The `caveats_i18n` / `warnings_i18n` a result may carry beside its English lines. */
export function saidOf(result: unknown, field: 'caveats' | 'warnings' = 'caveats'): (SaidI18n | null)[] | undefined {
  const r = result as Record<string, unknown> | null | undefined
  const direct = r?.[`${field}_i18n`]
  const meta = (r?.meta as Record<string, unknown> | undefined)?.[`${field}_i18n`]
  return (Array.isArray(direct) ? direct : Array.isArray(meta) ? meta : undefined) as (SaidI18n | null)[] | undefined
}
