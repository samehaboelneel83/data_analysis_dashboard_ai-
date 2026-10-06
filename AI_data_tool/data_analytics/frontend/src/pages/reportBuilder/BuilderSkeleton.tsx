import { useT } from '../../i18n'

/** While the dashboard loads (redesign 7e5): the builder's shape -- two
 *  header rows, the side panel, a grid of tiles -- not a bare "Loading…". */
export default function BuilderSkeleton() {
  const t = useT()
  return (
    <div className="dl-bd-skel" role="status" aria-busy="true" aria-label={t('bd.loading')}>
      <div className="r1"><i className="sk" style={{ width: 220 }} /><i className="sk" style={{ width: 90 }} /><span className="sp" /><i className="sk" style={{ width: 260 }} /></div>
      <div className="r2"><i className="sk" style={{ width: 200 }} /><i className="sk" style={{ width: 160 }} /><span className="sp" /><i className="sk" style={{ width: 150 }} /></div>
      <div className="body">
        <div className="side">{Array.from({ length: 8 }, (_, i) => <i key={i} className="sk" style={{ width: `${60 + (i * 13) % 35}%` }} />)}</div>
        <div className="grid">{[3, 3, 3, 3, 6, 6, 4, 8].map((w, i) => <i key={i} className="sk" style={{ gridColumn: `span ${w}` }} />)}</div>
      </div>
    </div>
  )
}
