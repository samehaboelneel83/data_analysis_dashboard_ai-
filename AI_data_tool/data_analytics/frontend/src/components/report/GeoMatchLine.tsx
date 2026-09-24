import { useGeoMatch } from './GeoMatchCheck'
import { geoMatchSentence } from '../../lib/geoMatch'
import GeoMatchStatus from './GeoMatchStatus'

/** The live match rate under a region map's boundary picker: which of the
 *  dimension's values will not land on a shape, before anyone reads the map.
 *
 *  Its own module so WidgetConfigPanel can load it lazily: matching needs the
 *  bundled world geometry (~740 kB raw), which the builder must not download
 *  for authors who never configure a region map. */
export default function GeoMatchLine({ datasetId, column, setId }: { datasetId: number | null; column: string; setId: number | null }) {
  // No dataset, no check -- and no boundary download for a panel that cannot use it.
  const { report, loading } = useGeoMatch(datasetId, column, datasetId ? setId : null)
  if (!datasetId) return null
  return (
    <GeoMatchStatus danger={!!report && report.unmatched.length > 0}>
      {loading ? `Checking ${column} against the map…` : report ? geoMatchSentence(report) : null}
    </GeoMatchStatus>
  )
}
