import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { boundarySetsApi } from '../../../services/api'
import { _clearRegionSetCache } from '../geo/regionSetCache'

// Spread the real module: a partial mock of `services/api` has previously
// broken an unrelated test file a hundred files later.
vi.mock('../../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  boundarySetsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), remove: vi.fn() },
}))
import GeoChoroplethRenderer from './GeoChoroplethRenderer'
import { GeoPointsRenderer, GeoBubblesRenderer, markersWithin } from './GeoPointMapRenderer'
import { GeoLinesRenderer, GeoClustersRenderer } from './GeoLineClusterRenderer'
import { GeoPiesRenderer, GeoLayersRenderer } from './GeoPieLayerRenderer'
import GeoNetworkRenderer from './GeoNetworkRenderer'
import type { ChartRendererProps } from './types'

const base: Omit<ChartRendererProps, 'rows'> = {
  data: {}, cfg: {}, rtl: false, broadcasts: false, localSelected: null,
  onClickPoint: () => {},
  plotW: 960, plotH: 540,
}

describe('GeoChoroplethRenderer', () => {
  it('paints matched countries and leaves the rest as base fill', () => {
    const { container } = render(
      <GeoChoroplethRenderer {...base} rows={[
        { name: 'US', value: 100 }, { name: 'France', value: 50 },
      ]} />
    )
    const us = container.querySelector('[data-country="United States of America"]')!
    const fr = container.querySelector('[data-country="France"]')!
    const de = container.querySelector('[data-country="Germany"]')!
    expect(us.getAttribute('data-value')).toBe('100')
    expect(fr.getAttribute('data-value')).toBe('50')
    // Germany has no data: base fill, no value. Asserting the CONTRAST between painted
    // and unpainted is what a "renders an svg" smoke test cannot do.
    expect(de.getAttribute('data-value')).toBeNull()
    expect(us.getAttribute('fill')).not.toBe(de.getAttribute('fill'))
  })

  it('sums rows that resolve to the same country rather than overwriting', () => {
    // "US" and "United States" are the same place arriving under two spellings; last-
    // write-wins would silently halve the total.
    const { container } = render(
      <GeoChoroplethRenderer {...base} rows={[
        { name: 'US', value: 60 }, { name: 'United States', value: 40 },
      ]} />
    )
    expect(container.querySelector('[data-country="United States of America"]')!
      .getAttribute('data-value')).toBe('100')
  })

  it('surfaces unmatched rows as a visible count, never silently', () => {
    render(
      <GeoChoroplethRenderer {...base} rows={[
        { name: 'US', value: 1 }, { name: 'Atlantis', value: 2 }, { name: 'Mordor', value: 3 },
      ]} />
    )
    expect(screen.getByTestId('geo-unmatched')).toHaveTextContent('2 rows did not match')
  })

  it('renders no unmatched note when everything matched', () => {
    render(<GeoChoroplethRenderer {...base} rows={[{ name: 'France', value: 1 }]} />)
    expect(screen.queryByTestId('geo-unmatched')).not.toBeInTheDocument()
  })
})

describe('GeoPointMapRenderer', () => {
  it('plots lat/lon rows directly', () => {
    const { container } = render(
      <GeoPointsRenderer {...base} rows={[
        { lat: 48.85, lon: 2.35, name: 'Paris', value: 10 },
      ]} />
    )
    const marker = container.querySelector('[data-marker="Paris"]')!
    expect(marker).toBeTruthy()
    expect(Number(marker.getAttribute('cx'))).toBeGreaterThan(0)
  })

  it('plots country rows at centroids, so coordinate-free data still maps', () => {
    const { container } = render(
      <GeoPointsRenderer {...base} rows={[{ name: 'Brazil', value: 5 }]} />
    )
    expect(container.querySelector('[data-marker="Brazil"]')).toBeTruthy()
  })

  it('scales bubble AREA with value: quadrupled value doubles the radius', () => {
    const { container } = render(
      <GeoBubblesRenderer {...base} rows={[
        { name: 'US', value: 100 }, { name: 'France', value: 25 },
      ]} />
    )
    const r = (name: string) =>
      Number(container.querySelector(`[data-marker="${name === 'US' ? 'United States of America' : name}"]`)!.getAttribute('r'))
    // sqrt scaling: value ratio 4:1 must give radius ratio ~2:1 on the variable part.
    // Radius proportional to value would give 4:1 and make the small bubble unreadable.
    const variableUS = r('US') - 4
    const variableFR = r('France') - 4
    expect(variableUS / variableFR).toBeCloseTo(2, 1)
  })

  it('keeps every point the same size on a point map', () => {
    const { container } = render(
      <GeoPointsRenderer {...base} rows={[
        { name: 'US', value: 100 }, { name: 'France', value: 1 },
      ]} />
    )
    const radii = [...container.querySelectorAll('circle')].map(c => c.getAttribute('r'))
    expect(new Set(radii).size).toBe(1)
  })
})

describe('display rules reach the map markers', () => {
  /**
   * Display rules already drove colour everywhere else — bars, bubbles,
   * butterflies, table cells — and stopped at the map. `ChartRendererProps`
   * has carried `ruleStyles` all along and `RuleStyle` has carried an `icon`
   * all along; the point map simply never read either, so "flag the sites that
   * missed target" worked on every chart type except the one where location is
   * the point.
   *
   * Rows are indexed the same way every other renderer indexes them, so a rule
   * that colours the third bar colours the third marker.
   */
  const styles = (rows: (Record<string, unknown> | null)[]) =>
    ({ rows, cells: {}, widget: {} } as never)

  it('paints a marker with its rule colour', () => {
    const { container } = render(
      <GeoPointsRenderer {...base}
        rows={[{ name: 'Brazil', value: 5 }]}
        ruleStyles={styles([{ fill: '#ff0000' }])} />
    )
    expect(container.querySelector('[data-marker="Brazil"]')!
      .getAttribute('fill')).toBe('#ff0000')
  })

  it('leaves an unruled marker its default colour', () => {
    const { container } = render(
      <GeoPointsRenderer {...base}
        rows={[{ name: 'Brazil', value: 5 }, { name: 'France', value: 5 }]}
        ruleStyles={styles([{ fill: '#ff0000' }, null])} />
    )
    const ruled = container.querySelector('[data-marker="Brazil"]')!
    const plain = container.querySelector('[data-marker="France"]')!
    expect(ruled.getAttribute('fill')).toBe('#ff0000')
    expect(plain.getAttribute('fill')).not.toBe('#ff0000')
  })

  it('draws the rule icon at the marker', () => {
    // The matrix cell: SAS puts custom icons on map markers via display rules.
    const { container } = render(
      <GeoPointsRenderer {...base}
        rows={[{ name: 'Brazil', value: 5 }]}
        ruleStyles={styles([{ icon: '▲' }])} />
    )
    const icon = container.querySelector('[data-marker-icon="Brazil"]')!
    expect(icon).toBeTruthy()
    expect(icon.textContent).toBe('▲')
  })

  it('keeps the rule index aligned when an earlier row does not match', () => {
    /**
     * The bug this shape invites. Markers are built by SKIPPING unmatched rows,
     * so the marker list is shorter than the row list — indexing rules by
     * marker position would shift every rule up by one and colour the wrong
     * country. "Atlantis" is row 0 and matches nothing.
     */
    const { container } = render(
      <GeoPointsRenderer {...base}
        rows={[{ name: 'Atlantis', value: 1 }, { name: 'Brazil', value: 5 }]}
        ruleStyles={styles([{ fill: '#00ff00' }, { fill: '#0000ff' }])} />
    )
    expect(container.querySelector('[data-marker="Brazil"]')!
      .getAttribute('fill')).toBe('#0000ff')
  })

  it('bubbles honour rules too', () => {
    const { container } = render(
      <GeoBubblesRenderer {...base}
        rows={[{ name: 'Brazil', value: 5 }]}
        ruleStyles={styles([{ fill: '#abcdef' }])} />
    )
    expect(container.querySelector('[data-marker="Brazil"]')!
      .getAttribute('fill')).toBe('#abcdef')
  })
})

describe('a choropleth drawn on uploaded boundaries', () => {
  /**
   * The failure this closes, found on a real dashboard: a hospital choropleth
   * of 27 Egyptian governorates matched none of them and drew a bare world
   * map. The atlas is countries and only countries, and admin-1 for every
   * country is tens of megabytes, so the shapes have to come from the customer.
   *
   * The governorate names below are real; the polygons are unit squares,
   * because a test fixture must not pretend to be a claim about where Egyptian
   * governorates actually are.
   */
  const square = (x: number, y: number) => ({
    type: 'Polygon',
    coordinates: [[[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1], [x, y]]],
  })
  const EGYPT = {
    type: 'FeatureCollection',
    features: [
      { type: 'Feature', geometry: square(31, 30), properties: { name: 'Cairo' } },
      { type: 'Feature', geometry: square(30, 29), properties: { name: 'Giza' } },
      { type: 'Feature', geometry: square(29, 31), properties: { name: 'Alexandria' } },
    ],
  }

  beforeEach(() => {
    // Both, and for different reasons: the spy counts calls across every test
    // in the file, and the region cache is module state that survives them.
    vi.clearAllMocks()
    _clearRegionSetCache()
    vi.mocked(boundarySetsApi.get).mockResolvedValue({
      id: 7, name: 'Egypt governorates', feature_count: 3,
      key_properties: ['name'], sample_names: [], created_by: 1,
      created_at: null, geometry: EGYPT,
    } as never)
  })

  const GOV_ROWS = [
    { name: 'Cairo', value: 900 },
    { name: 'Giza', value: 400 },
    { name: 'Alexandria', value: 100 },
  ]

  it('leaves governorates unmatched with no boundary set — the old behaviour', async () => {
    // Pinned so the fix cannot be mistaken for the bug having never existed.
    const { container } = render(<GeoChoroplethRenderer {...base} rows={GOV_ROWS} />)
    expect(await screen.findByTestId('geo-unmatched')).toHaveTextContent('3 rows')
    expect(container.querySelector('[data-country="Cairo"]')).toBeNull()
  })

  it('paints them once a boundary set is attached', async () => {
    const { container } = render(
      <GeoChoroplethRenderer {...base} rows={GOV_ROWS}
        cfg={{ boundary_set_id: 7 } as never} />)
    await waitFor(() =>
      expect(container.querySelector('[data-country="Cairo"]')).toBeTruthy())
    expect(container.querySelector('[data-country="Cairo"]')!
      .getAttribute('data-value')).toBe('900')
    expect(screen.queryByTestId('geo-unmatched')).not.toBeInTheDocument()
  })

  it('draws the uploaded shapes INSTEAD of the world, not on top of it', async () => {
    // Layering would leave a governorate map as a speck on a globe. The set
    // replaces the backdrop.
    const { container } = render(
      <GeoChoroplethRenderer {...base} rows={GOV_ROWS}
        cfg={{ boundary_set_id: 7 } as never} />)
    await waitFor(() =>
      expect(container.querySelector('[data-country="Cairo"]')).toBeTruthy())
    expect(container.querySelectorAll('path').length).toBe(3)
    expect(container.querySelector('[data-country="France"]')).toBeNull()
  })

  it('says the boundaries are loading rather than reporting every row unmatched', async () => {
    // Otherwise the first frame blames the data for a request still in flight.
    let release: (v: unknown) => void = () => {}
    vi.mocked(boundarySetsApi.get).mockReturnValue(
      new Promise(res => { release = res }) as never)
    render(<GeoChoroplethRenderer {...base} rows={GOV_ROWS}
      cfg={{ boundary_set_id: 7 } as never} />)
    expect(await screen.findByTestId('geo-loading')).toBeInTheDocument()
    expect(screen.queryByTestId('geo-unmatched')).not.toBeInTheDocument()
    release({ id: 7, key_properties: ['name'], geometry: EGYPT })
  })

  it('falls back to countries and says so when the set cannot be fetched', async () => {
    // An empty set would report every row unmatched, which blames the data for
    // a failed request.
    vi.mocked(boundarySetsApi.get).mockRejectedValue(new Error('down'))
    render(<GeoChoroplethRenderer {...base} rows={GOV_ROWS}
      cfg={{ boundary_set_id: 7 } as never} />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be loaded/i)
  })

  it('fetches the set once however many maps use it', async () => {
    // Megabytes of polygons. Three choropleths on a page must not fetch three
    // times — and StrictMode double-mounts every effect in development.
    render(<>
      <GeoChoroplethRenderer {...base} rows={GOV_ROWS} cfg={{ boundary_set_id: 7 } as never} />
      <GeoChoroplethRenderer {...base} rows={GOV_ROWS} cfg={{ boundary_set_id: 7 } as never} />
    </>)
    await waitFor(() => expect(
      document.querySelectorAll('[data-country="Cairo"]').length).toBe(2))
    expect(boundarySetsApi.get).toHaveBeenCalledTimes(1)
  })

  it('names the boundary set in the unmatched footer, not "a country"', async () => {
    const { container } = render(
      <GeoChoroplethRenderer {...base}
        rows={[...GOV_ROWS, { name: 'Atlantis', value: 1 }]}
        cfg={{ boundary_set_id: 7 } as never} />)
    await waitFor(() =>
      expect(container.querySelector('[data-country="Cairo"]')).toBeTruthy())
    expect(screen.getByTestId('geo-unmatched'))
      .toHaveTextContent(/did not match a region in this boundary set/i)
  })
})

describe('maps take part in cross-filtering', () => {
  /**
   * Every chart type in this product filters the page when you click it. The
   * nine map widgets did not: `onClickPoint` was in their props and none of
   * them ever called it, so clicking a country did nothing while clicking the
   * bar beside it filtered everything. "Where?" is the question a map exists to
   * answer, and answering it could not narrow the page.
   */
  it('a choropleth region filters by the value the DATA carries', () => {
    // Not the matched feature's label: the rows say "US", the geometry says
    // "United States of America", and emitting the geometry's name would
    // produce `region = United States of America`, which matches no row.
    const onClickPoint = vi.fn()
    const { container } = render(<GeoChoroplethRenderer {...base}
      rows={[{ name: 'US', value: 5 }, { name: 'France', value: 3 }]}
      broadcasts onClickPoint={onClickPoint} />)
    fireEvent.click(container.querySelector('[data-country="United States of America"]')!)
    expect(onClickPoint).toHaveBeenCalledWith('US')
  })

  it('a region two rows merged into filters by BOTH of their names', () => {
    // "US" and "USA" paint one shape and sum. Filtering by one of them would
    // silently drop the other's rows from every widget on the page.
    const onClickPoint = vi.fn()
    const { container } = render(<GeoChoroplethRenderer {...base}
      rows={[{ name: 'US', value: 5 }, { name: 'USA', value: 2 }]}
      broadcasts onClickPoint={onClickPoint} />)
    fireEvent.click(container.querySelector('[data-country="United States of America"]')!)
    expect(onClickPoint).toHaveBeenCalledWith(['US', 'USA'])
  })

  it('a region with no data is not clickable', () => {
    const onClickPoint = vi.fn()
    const { container } = render(<GeoChoroplethRenderer {...base}
      rows={[{ name: 'France', value: 3 }]}
      broadcasts onClickPoint={onClickPoint} />)
    fireEvent.click(container.querySelector('[data-country="Germany"]')!)
    expect(onClickPoint).not.toHaveBeenCalled()
  })

  it('a page set to no interactions does not filter from a map either', () => {
    // `broadcasts` is the page's interaction mode. A map must respect it for
    // the same reason a bar chart does.
    const onClickPoint = vi.fn()
    const { container } = render(<GeoChoroplethRenderer {...base}
      rows={[{ name: 'France', value: 3 }]}
      broadcasts={false} onClickPoint={onClickPoint} />)
    fireEvent.click(container.querySelector('[data-country="France"]')!)
    expect(onClickPoint).not.toHaveBeenCalled()
  })

  it('the selected region is visibly selected', () => {
    // Without this the page filters and the map that filtered it looks
    // untouched, so nobody can tell which shape is driving the dashboard.
    const { container } = render(<GeoChoroplethRenderer {...base}
      rows={[{ name: 'France', value: 3 }, { name: 'US', value: 5 }]}
      broadcasts localSelected={'France'} onClickPoint={() => {}} />)
    const fr = container.querySelector('[data-country="France"]')!
    const us = container.querySelector('[data-country="United States of America"]')!
    expect(fr.getAttribute('data-selected')).toBe('true')
    expect(Number(fr.getAttribute('stroke-width')))
      .toBeGreaterThan(Number(us.getAttribute('stroke-width')))
  })

  it('a point map marker filters by its row name', () => {
    const onClickPoint = vi.fn()
    const { container } = render(<GeoPointsRenderer {...base}
      rows={[{ name: 'Paris', lat: 48.85, lon: 2.35, value: 4 }]}
      broadcasts onClickPoint={onClickPoint} />)
    fireEvent.click(container.querySelector('[data-marker="Paris"]')!)
    expect(onClickPoint).toHaveBeenCalledWith('Paris')
  })

  it('a bubble map marker filters too', () => {
    const onClickPoint = vi.fn()
    const { container } = render(<GeoBubblesRenderer {...base}
      rows={[{ name: 'Brazil', value: 9 }]}
      broadcasts onClickPoint={onClickPoint} />)
    fireEvent.click(container.querySelector('[data-marker="Brazil"]')!)
    expect(onClickPoint).toHaveBeenCalledWith('Brazil')
  })

  it('a marker on a non-interactive page does nothing', () => {
    const onClickPoint = vi.fn()
    const { container } = render(<GeoPointsRenderer {...base}
      rows={[{ name: 'Paris', lat: 48.85, lon: 2.35, value: 4 }]}
      broadcasts={false} onClickPoint={onClickPoint} />)
    fireEvent.click(container.querySelector('[data-marker="Paris"]')!)
    expect(onClickPoint).not.toHaveBeenCalled()
  })
})

describe('the rest of the map family', () => {
  it('a flow line filters by its route', () => {
    const onClickPoint = vi.fn()
    const { container } = render(<GeoLinesRenderer {...base}
      rows={[{ name: 'Paris → Berlin', lat: 48.85, lon: 2.35, lat2: 52.52, lon2: 13.4, value: 7 }]}
      broadcasts onClickPoint={onClickPoint} />)
    fireEvent.click(container.querySelector('[data-line="Paris → Berlin"]')!)
    expect(onClickPoint).toHaveBeenCalledWith('Paris → Berlin')
  })

  it('a line map draws into the tile’s measured size, not a fixed 16:9 box', () => {
    const { container } = render(<GeoLinesRenderer {...base}
      rows={[{ name: 'Paris → Berlin', lat: 48.85, lon: 2.35, lat2: 52.52, lon2: 13.4, value: 7 }]}
      plotW={720} plotH={180} />)
    expect(container.querySelector('svg')?.getAttribute('viewBox')).toBe('0 0 720 180')
  })

  it('pins the svg to the tile so a viewBox cannot widen it and clip the east edge', () => {
    const { container } = render(<GeoLinesRenderer {...base}
      rows={[{ name: 'Paris → Berlin', lat: 48.85, lon: 2.35, lat2: 52.52, lon2: 13.4, value: 7 }]} />)
    const svg = container.querySelector('svg') as SVGElement
    expect(svg.getAttribute('width')).toBe('100%')
    expect(svg.getAttribute('height')).toBe('100%')
    expect(svg.style.position).toBe('absolute')
    expect(svg.style.width).toBe('100%')
    expect(svg.style.maxWidth).toBe('100%')
  })

  it('a pie on the map filters by its location', () => {
    const onClickPoint = vi.fn()
    // This widget places pies by COUNTRY name, and reads them off `data.rows`.
    const { container } = render(<GeoPiesRenderer {...base} rows={[]}
      data={{ rows: [{ name: 'France', total: 8,
        slices: [{ label: 'A', value: 3 }, { label: 'B', value: 5 }] }] }}
      broadcasts onClickPoint={onClickPoint} />)
    fireEvent.click(container.querySelector('[data-pie="France"]')!)
    expect(onClickPoint).toHaveBeenCalledWith('France')
  })

  it('a network node on a map filters by the node', () => {
    const onClickPoint = vi.fn()
    const { container } = render(<GeoNetworkRenderer {...base} rows={[]}
      data={{ nodes: [{ id: 'Cairo', lat: 30.04, lon: 31.24, degree: 2 },
                      { id: 'Giza', lat: 30.01, lon: 31.21, degree: 1 }],
              links: [{ source: 'Cairo', target: 'Giza', value: 3 }] }}
      broadcasts onClickPoint={onClickPoint} />)
    fireEvent.click(container.querySelector('[data-geonode="Cairo"]')!)
    expect(onClickPoint).toHaveBeenCalledWith('Cairo')
  })

  it('a layered map filters from its region layer, by the row’s own name', () => {
    const onClickPoint = vi.fn()
    const { container } = render(<GeoLayersRenderer {...base} rows={[]}
      data={{ regions: [{ name: 'US', value: 4 }],
              points: [{ lat: 40.7, lon: -74, value: 2 }] }}
      broadcasts onClickPoint={onClickPoint} />)
    fireEvent.click(container.querySelector('[data-region="United States of America"]')!)
    expect(onClickPoint).toHaveBeenCalledWith('US')
  })

  it('a cluster does NOT pretend to filter', () => {
    /**
     * The honest limit, asserted so nobody wires it later without thinking.
     * `shape_geo_clusters` snaps points to a lat/lon grid and returns a COUNT
     * per cell — there is no dimension value behind a cluster, so a click has
     * nothing truthful to filter by. Better to stay inert than to filter by a
     * grid cell the data never names.
     */
    const onClickPoint = vi.fn()
    const { container } = render(<GeoClustersRenderer {...base}
      rows={[{ lat: 30.04, lon: 31.24, count: 12 }]}
      broadcasts onClickPoint={onClickPoint} />)
    fireEvent.click(container.querySelector('[data-cluster="12"]')!)
    expect(onClickPoint).not.toHaveBeenCalled()
  })
})

describe('selecting an area of a map', () => {
  /**
   * SAS calls this radius selection: draw a circle on the map, get the points
   * inside. It is the one selection gesture a map can offer that no other chart
   * can, because "the sites within 50km of here" is not a value in any column.
   *
   * The geometry is a pure function and tested as one; the drag that feeds it
   * is tested through stubbed element rects, because jsdom reports every
   * element as 0x0 and the screen-to-viewBox conversion divides by that.
   */
  it('keeps the markers inside the circle and drops the rest', () => {
    const inside = markersWithin(
      [{ name: 'A', x: 10, y: 10 }, { name: 'B', x: 12, y: 11 }, { name: 'C', x: 500, y: 300 }],
      { cx: 11, cy: 10, r: 5 })
    expect(inside).toEqual(['A', 'B'])
  })

  it('measures from the centre, not the bounding box', () => {
    // A corner point of the enclosing square is outside the circle. Using a box
    // would quietly select things the user drew a circle around and excluded.
    const inside = markersWithin([{ name: 'corner', x: 10, y: 10 }],
      { cx: 0, cy: 0, r: 12 })
    expect(inside).toEqual([])          // distance is 14.1, not 10
  })

  it('selects nothing for a zero-radius drag', () => {
    expect(markersWithin([{ name: 'A', x: 10, y: 10 }], { cx: 10, cy: 10, r: 0 }))
      .toEqual([])
  })

  it('shift-dragging a point map filters by everything inside', () => {
    const onClickPoint = vi.fn()
    const { container } = render(<GeoPointsRenderer {...base}
      rows={[{ name: 'Paris', lat: 48.85, lon: 2.35, value: 1 },
             { name: 'Berlin', lat: 52.52, lon: 13.4, value: 1 }]}
      broadcasts onClickPoint={onClickPoint} />)
    const svg = container.querySelector('svg')!
    // jsdom has no layout: without a rect the conversion from screen pixels to
    // viewBox units divides by zero and the gesture is (correctly) ignored.
    svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 960, height: 540,
      right: 960, bottom: 540, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect

    // A circle covering the whole map: both markers must come back, as one
    // multi-value selection rather than two clicks.
    fireEvent.mouseDown(svg, { clientX: 480, clientY: 270, shiftKey: true })
    fireEvent.mouseMove(svg, { clientX: 960, clientY: 540, shiftKey: true })
    fireEvent.mouseUp(svg, { clientX: 960, clientY: 540, shiftKey: true })

    expect(onClickPoint).toHaveBeenCalledTimes(1)
    const [payload] = onClickPoint.mock.calls[0]
    expect(new Set(payload as string[])).toEqual(new Set(['Paris', 'Berlin']))
  })

  it('an ordinary drag without shift does not select an area', () => {
    // Plain dragging is how a user scrolls or selects text; taking it over
    // would make the map feel broken everywhere else.
    const onClickPoint = vi.fn()
    const { container } = render(<GeoPointsRenderer {...base}
      rows={[{ name: 'Paris', lat: 48.85, lon: 2.35, value: 1 }]}
      broadcasts onClickPoint={onClickPoint} />)
    const svg = container.querySelector('svg')!
    svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 960, height: 540,
      right: 960, bottom: 540, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect
    fireEvent.mouseDown(svg, { clientX: 480, clientY: 270 })
    fireEvent.mouseMove(svg, { clientX: 900, clientY: 500 })
    fireEvent.mouseUp(svg, { clientX: 900, clientY: 500 })
    expect(onClickPoint).not.toHaveBeenCalled()
  })

  it('an area selection on a non-interactive page does nothing', () => {
    const onClickPoint = vi.fn()
    const { container } = render(<GeoPointsRenderer {...base}
      rows={[{ name: 'Paris', lat: 48.85, lon: 2.35, value: 1 }]}
      broadcasts={false} onClickPoint={onClickPoint} />)
    const svg = container.querySelector('svg')!
    svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 960, height: 540,
      right: 960, bottom: 540, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect
    fireEvent.mouseDown(svg, { clientX: 480, clientY: 270, shiftKey: true })
    fireEvent.mouseMove(svg, { clientX: 960, clientY: 540, shiftKey: true })
    fireEvent.mouseUp(svg, { clientX: 960, clientY: 540, shiftKey: true })
    expect(onClickPoint).not.toHaveBeenCalled()
  })

  it('an empty circle clears nothing rather than filtering to nothing', () => {
    // Selecting empty ocean must not emit an empty filter, which every widget
    // on the page would answer with "no rows".
    const onClickPoint = vi.fn()
    const { container } = render(<GeoPointsRenderer {...base}
      rows={[{ name: 'Paris', lat: 48.85, lon: 2.35, value: 1 }]}
      broadcasts onClickPoint={onClickPoint} />)
    const svg = container.querySelector('svg')!
    svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 960, height: 540,
      right: 960, bottom: 540, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect
    fireEvent.mouseDown(svg, { clientX: 5, clientY: 5, shiftKey: true })
    fireEvent.mouseMove(svg, { clientX: 12, clientY: 12, shiftKey: true })
    fireEvent.mouseUp(svg, { clientX: 12, clientY: 12, shiftKey: true })
    expect(onClickPoint).not.toHaveBeenCalled()
  })

  it('tells the reader the gesture exists', () => {
    const { container } = render(<GeoPointsRenderer {...base}
      rows={[{ name: 'Paris', lat: 48.85, lon: 2.35, value: 1 }]}
      broadcasts onClickPoint={() => {}} />)
    expect(container.textContent).toMatch(/shift.?drag/i)
  })
})

/**
 * Author-placed pins: annotations, not data.
 *
 * SAS lets an author drop a pin on a map — "our new depot", "the flood line" —
 * at a fixed coordinate that has nothing to do with the rows. The whole point
 * is that it is NOT a data point, and that distinction is the only thing here
 * that can go quietly wrong: a pin drawn as a marker would join cross-filtering
 * and a lasso selection, and the page would filter to a value no row holds.
 *
 * So the tests below are mostly about what a pin must NOT do.
 */
describe('map pins', () => {
  const pins = [{ lat: 48.85, lon: 2.35, label: 'New depot' }]

  it('draws a pin with its label', () => {
    const { container } = render(
      <GeoPointsRenderer {...base} cfg={{ pins }}
        rows={[{ lat: 48.9, lon: 2.3, name: 'Site A', value: 1 }]} />
    )
    const pin = container.querySelector('[data-pin="New depot"]')
    expect(pin).not.toBeNull()
    expect(screen.getByText('New depot')).toBeInTheDocument()
  })

  it('does not let a pin broadcast a filter', () => {
    // The failure this prevents: clicking an annotation filters every widget on
    // the page to a name no row contains, so they all answer "no rows" and the
    // reader has no idea why.
    const onClickPoint = vi.fn()
    const { container } = render(
      <GeoPointsRenderer {...base} broadcasts cfg={{ pins }} onClickPoint={onClickPoint}
        rows={[{ lat: 48.9, lon: 2.3, name: 'Site A', value: 1 }]} />
    )
    fireEvent.click(container.querySelector('[data-pin="New depot"]')!)
    expect(onClickPoint).not.toHaveBeenCalled()
  })

  it('keeps pins out of a radius selection', () => {
    // `markersWithin` is the lasso's membership test. A pin reaching it would
    // put its label into a multi-value filter alongside real markers.
    const inside = markersWithin(
      [{ name: 'Site A', x: 100, y: 100 }],
      { cx: 100, cy: 100, r: 50 })
    expect(inside).toEqual(['Site A'])
  })

  it('frames the map so a pin away from the data is still visible', () => {
    // The projection fits what is plotted. A pin outside that extent would
    // project off-canvas -- present in the DOM, invisible on screen, which is
    // the worst of both.
    const { container } = render(
      <GeoPointsRenderer {...base}
        cfg={{ pins: [{ lat: -33.87, lon: 151.21, label: 'Sydney office' }] }}
        rows={[{ lat: 48.9, lon: 2.3, name: 'Paris site', value: 1 }]} />
    )
    const pin = container.querySelector('[data-pin="Sydney office"]')!
    const x = Number(pin.getAttribute('data-x'))
    const y = Number(pin.getAttribute('data-y'))
    expect(x).toBeGreaterThanOrEqual(0)
    expect(x).toBeLessThanOrEqual(960)
    expect(y).toBeGreaterThanOrEqual(0)
    expect(y).toBeLessThanOrEqual(540)
  })

  it('ignores a pin with no usable coordinate', () => {
    // Pins are hand-typed, so a blank or half-filled one is normal. Projecting
    // NaN throws inside d3 and takes the whole map with it.
    const { container } = render(
      <GeoPointsRenderer {...base}
        cfg={{ pins: [{ lat: undefined, lon: 2.35, label: 'Half' },
                      { lat: 'x', lon: 'y', label: 'Typed' },
                      { lat: 48.85, lon: 2.35, label: 'Good' }] }}
        rows={[{ lat: 48.9, lon: 2.3, name: 'Site A', value: 1 }]} />
    )
    expect(container.querySelector('[data-pin="Good"]')).not.toBeNull()
    expect(container.querySelector('[data-pin="Half"]')).toBeNull()
    expect(container.querySelector('[data-pin="Typed"]')).toBeNull()
  })

  it('draws pins on a bubble map too', () => {
    const { container } = render(
      <GeoBubblesRenderer {...base} cfg={{ pins }}
        rows={[{ lat: 48.9, lon: 2.3, name: 'Site A', value: 5 }]} />
    )
    expect(container.querySelector('[data-pin="New depot"]')).not.toBeNull()
  })

  it('draws nothing extra when a widget has no pins', () => {
    const { container } = render(
      <GeoPointsRenderer {...base} rows={[{ lat: 48.9, lon: 2.3, name: 'Site A', value: 1 }]} />
    )
    expect(container.querySelector('[data-pin]')).toBeNull()
  })
})

/**
 * A column classified as geography should draw its own boundaries.
 *
 * `classifyGeography` in the builder writes `role: 'geography'` and a
 * `boundary_set_id` onto the COLUMN, in the dataset's `column_meta` — so the
 * classification travels with the data rather than with one widget. Nothing
 * read it: the renderer looked only at `config.boundary_set_id`, which is the
 * per-widget override. An author could classify a column, see the setting
 * saved, and get a world map.
 *
 * That is the mirror of this codebase's "check endpoints have callers" rule —
 * here the caller existed and the consumer did not.
 */
describe('geography classification drives the boundary set', () => {
  const EGYPT = {
    type: 'FeatureCollection',
    features: [{ type: 'Feature', properties: { name: 'Cairo' },
      geometry: { type: 'Polygon', coordinates: [[[31, 30], [32, 30], [32, 31], [31, 31], [31, 30]]] } }],
  }

  beforeEach(() => {
    // Call history too, not just the cache: these assertions are about WHICH
    // set was fetched, and a call left over from the previous test answers the
    // question with the wrong test's evidence.
    vi.clearAllMocks()
    _clearRegionSetCache()
    vi.mocked(boundarySetsApi.get).mockResolvedValue(
      { id: 9, name: 'Governorates', geometry: EGYPT, key_properties: ['name'] } as never)
  })

  it("uses the classified column's set when the widget names none", async () => {
    render(<GeoChoroplethRenderer {...base}
      cfg={{ dimension: 'governorate' }}
      geography={{ governorate: 9 }}
      rows={[{ name: 'Cairo', value: 5 }]} />)

    await waitFor(() => expect(boundarySetsApi.get).toHaveBeenCalledWith(9))
  })

  it("lets the widget's own choice win", async () => {
    // An explicit per-widget setting is a deliberate override of the dataset's
    // default, so it must beat the classification rather than race it.
    render(<GeoChoroplethRenderer {...base}
      cfg={{ dimension: 'governorate', boundary_set_id: 4 }}
      geography={{ governorate: 9 }}
      rows={[{ name: 'Cairo', value: 5 }]} />)

    await waitFor(() => expect(boundarySetsApi.get).toHaveBeenCalledWith(4))
    expect(boundarySetsApi.get).not.toHaveBeenCalledWith(9)
  })

  it('stays on countries for an unclassified column', async () => {
    render(<GeoChoroplethRenderer {...base}
      cfg={{ dimension: 'country' }}
      geography={{ governorate: 9 }}
      rows={[{ name: 'France', value: 5 }]} />)

    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument())
    expect(boundarySetsApi.get).not.toHaveBeenCalled()
  })
})
