import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import BoundarySetPicker from './BoundarySetPicker'
import { boundarySetsApi } from '../../services/api'
import { axeViolations } from '../../test/axe'

/**
 * Choosing the shapes a region map draws — and getting a new set in.
 *
 * The bundled atlas is countries and only countries, so a dataset keyed by
 * governorates, states or districts drew a bare world map with nothing on it.
 * Admin-1 for every country is tens of megabytes and cannot ship with the app,
 * so the shapes come from the customer's own file.
 *
 * The picker and the upload are one component on purpose. An author discovers
 * they need a boundary set at the moment their choropleth comes back blank;
 * sending them to an admin page they may not have rights to, and back again, is
 * how a feature ends up unused.
 */

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  boundarySetsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), remove: vi.fn(), packs: vi.fn(), installPack: vi.fn() },
}))

const EGYPT = {
  id: 7, name: 'Egypt governorates', feature_count: 27,
  key_properties: ['name', 'name_ar'],
  sample_names: ['Cairo', 'Giza', 'Alexandria', 'Qalyubia', 'Sharqia'],
  created_by: 1, created_at: null,
}

const geojson = (features: unknown[]) =>
  JSON.stringify({ type: 'FeatureCollection', features })

/** jsdom's File has no usable `.text()` in this version. */
function fileOf(name: string, contents: string): File {
  const f = new File([contents], name, { type: 'application/json' })
  Object.defineProperty(f, 'text', { value: () => Promise.resolve(contents) })
  return f
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(boundarySetsApi.list).mockResolvedValue([EGYPT] as never)
  vi.mocked(boundarySetsApi.create).mockResolvedValue({ ...EGYPT, id: 9 } as never)
  vi.mocked(boundarySetsApi.packs).mockResolvedValue([] as never)
})

const picker = (value = '', onChange = vi.fn()) => {
  render(<BoundarySetPicker value={value} onChange={onChange} />)
  return onChange
}

describe('choosing a set', () => {
  it('offers the built-in countries first', async () => {
    picker()
    const select = await screen.findByLabelText(/boundaries/i) as HTMLSelectElement
    expect(select.options[0].value).toBe('')
    expect(select.options[0].textContent).toMatch(/countries/i)
  })

  it('lists the org’s uploaded sets with their size', async () => {
    picker()
    expect(await screen.findByRole('option', { name: /Egypt governorates \(27\)/ }))
      .toBeInTheDocument()
  })

  it('reports the choice', async () => {
    const onChange = picker()
    const select = await screen.findByLabelText(/boundaries/i)
    // Wait for the OPTION, not just the select: the select renders at once with
    // only the built-in entry and the org's sets arrive a tick later, so
    // changing to '7' before then sets '' and the assertion fails about one run
    // in a hundred with a message that looks like a component bug.
    await screen.findByRole('option', { name: /Egypt governorates/ })
    fireEvent.change(select, { target: { value: '7' } })
    expect(onChange).toHaveBeenCalledWith('7')
  })

  it('shows what the chosen set matches on, and some of its names', async () => {
    /**
     * The question an author actually has is "will my column match?", and the
     * only alternative to answering it here is building the widget and reading
     * the answer off an empty map.
     */
    picker('7')
    expect(await screen.findByText(/matches on name, name_ar/i)).toBeInTheDocument()
    expect(screen.getByText(/Cairo, Giza/)).toBeInTheDocument()
  })

  it('survives a failure to list without losing the built-in option', async () => {
    vi.mocked(boundarySetsApi.list).mockRejectedValue(new Error('down'))
    picker()
    const select = await screen.findByLabelText(/boundaries/i) as HTMLSelectElement
    expect(select.options.length).toBe(1)
  })
})

describe('uploading a file', () => {
  const upload = async (file: File) => {
    const input = await screen.findByLabelText(/boundary file/i)
    fireEvent.change(input, { target: { files: [file] } })
  }

  it('posts a GeoJSON file and selects it', async () => {
    const onChange = picker()
    await upload(fileOf('Egypt governorates.geojson', geojson([{ type: 'Feature' }])))
    await waitFor(() => expect(boundarySetsApi.create).toHaveBeenCalled())
    const [name, geometry] = vi.mocked(boundarySetsApi.create).mock.calls[0]
    // The file name minus its extension: asking for a name before the file has
    // even been checked is a form nobody fills in.
    expect(name).toBe('Egypt governorates')
    expect((geometry as { type: string }).type).toBe('FeatureCollection')
    await waitFor(() => expect(onChange).toHaveBeenCalledWith('9'))
  })

  it('converts a single-layer TopoJSON in the browser', async () => {
    /**
     * `topojson-client` is already bundled for the world atlas, so the browser
     * converts for free. The alternative is a Python TopoJSON dependency and a
     * second validator to keep honest — the endpoint takes GeoJSON only.
     */
    const topology = JSON.stringify({
      type: 'Topology',
      objects: { regions: { type: 'GeometryCollection', geometries: [
        { type: 'Polygon', arcs: [[0]], properties: { name: 'Cairo' } }] } },
      arcs: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
    })
    picker()
    await upload(fileOf('regions.topojson', topology))
    await waitFor(() => expect(boundarySetsApi.create).toHaveBeenCalled())
    const [, geometry] = vi.mocked(boundarySetsApi.create).mock.calls[0]
    expect((geometry as { type: string }).type).toBe('FeatureCollection')
  })

  it('refuses a multi-layer TopoJSON rather than guessing a layer', async () => {
    // Guessing which layer somebody meant is how the wrong shapes get drawn.
    picker()
    await upload(fileOf('two.topojson', JSON.stringify({
      type: 'Topology', arcs: [],
      objects: { states: { type: 'GeometryCollection', geometries: [] },
                 counties: { type: 'GeometryCollection', geometries: [] } },
    })))
    expect(await screen.findByRole('alert')).toHaveTextContent(/2 layers/i)
    expect(boundarySetsApi.create).not.toHaveBeenCalled()
  })

  it('says plainly when the file is not JSON at all', async () => {
    picker()
    await upload(fileOf('boundaries.shp', 'PK binary rubbish'))
    expect(await screen.findByRole('alert')).toHaveTextContent(/not JSON/i)
  })

  it('surfaces the backend’s own refusal', async () => {
    /**
     * "Region 4 is a Point, not an area" tells the author what to fix.
     * "Upload failed" sends them to inspect a file they cannot read.
     */
    vi.mocked(boundarySetsApi.create).mockRejectedValue({
      response: { data: { detail: 'Region 4 is a Point, not an area.' } } })
    picker()
    await upload(fileOf('points.geojson', geojson([{ type: 'Feature' }])))
    expect(await screen.findByRole('alert')).toHaveTextContent(/not an area/i)
  })

  it('does not leave the button stuck after a failure', async () => {
    vi.mocked(boundarySetsApi.create).mockRejectedValue(new Error('nope'))
    picker()
    await upload(fileOf('x.geojson', geojson([{ type: 'Feature' }])))
    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: /upload boundaries/i })).toBeEnabled()
  })
})

/**
 * What the map is ACTUALLY drawing with.
 *
 * The widget's own `boundary_set_id` is an override of the dimension column's
 * geography classification. With no override the picker sat empty, which reads
 * as "countries" — while the map on screen drew the classified set. A control
 * that disagrees with the picture beside it is worse than no control: the
 * author changes something else to fix a problem that was never there.
 */
describe('an inherited classification', () => {
  it('is named when the widget has no set of its own', async () => {
    render(<BoundarySetPicker value="" onChange={vi.fn()} inheritedName="Governorates" />)
    expect(await screen.findByText(/governorates/i)).toBeInTheDocument()
    expect(screen.getByText(/from the column/i)).toBeInTheDocument()
  })

  it('says nothing when the widget has its own', () => {
    render(<BoundarySetPicker value="9" onChange={vi.fn()} inheritedName="Governorates" />)
    expect(screen.queryByText(/from the column/i)).not.toBeInTheDocument()
  })

  it('says nothing when there is no classification', () => {
    render(<BoundarySetPicker value="" onChange={vi.fn()} />)
    expect(screen.queryByText(/from the column/i)).not.toBeInTheDocument()
  })
})


describe('starter packs', () => {
  const PACKS = [
    { id: 'egypt-governorates', name: 'Egypt governorates', country: 'EG', level: 'admin-1', feature_count: 27,
      description: 'All 27', source: 'Natural Earth', license: 'Public domain', license_url: null },
    { id: 'us-states', name: 'US states', country: 'US', level: 'admin-1', feature_count: 51,
      description: '50 + DC', source: 'Natural Earth', license: 'Public domain', license_url: null },
  ]

  it('offers only the packs the org has not installed, and installing one selects it', async () => {
    vi.mocked(boundarySetsApi.packs).mockResolvedValue(PACKS as never)
    vi.mocked(boundarySetsApi.installPack).mockResolvedValue({ ...EGYPT, id: 12, name: 'US states' } as never)
    const onChange = picker()
    const us = await screen.findByRole('button', { name: /\+ US states \(51\)/ })
    // Egypt is already an org set (EGYPT above), so it is not offered again.
    expect(screen.queryByRole('button', { name: /\+ Egypt governorates/ })).not.toBeInTheDocument()
    fireEvent.click(us)
    await waitFor(() => expect(onChange).toHaveBeenCalledWith('12'))
    expect(boundarySetsApi.installPack).toHaveBeenCalledWith('us-states', false)
  })

  const EU = {
    id: 'eu-nuts1', name: 'EU NUTS-1 regions', country: null, level: 'NUTS-1', feature_count: 123,
    description: 'Major EU regions', source: 'Eurostat GISCO', license: 'Eurostat GISCO terms',
    license_url: 'https://ec.europa.eu/eurostat/web/gisco/geodata/administrative-units',
    attribution: '© EuroGeographics for the administrative boundaries',
    terms: 'Free for non-commercial use; credit EuroGeographics on every map.',
    requires_acceptance: true,
  }

  it('shows the terms of a pack that has them before installing anything', async () => {
    vi.mocked(boundarySetsApi.packs).mockResolvedValue([EU] as never)
    vi.mocked(boundarySetsApi.installPack).mockResolvedValue({ ...EGYPT, id: 14, name: EU.name } as never)
    const onChange = picker()
    fireEvent.click(await screen.findByRole('button', { name: /\+ EU NUTS-1 regions \(123\) · terms/ }))
    // One click opens the terms; it does not accept them.
    expect(boundarySetsApi.installPack).not.toHaveBeenCalled()
    const terms = screen.getByTestId('pack-terms')
    expect(terms).toHaveTextContent('Free for non-commercial use')
    expect(terms).toHaveTextContent('© EuroGeographics')
    expect(screen.getByRole('link', { name: /read the licence/ })).toHaveAttribute('href', EU.license_url)
    fireEvent.click(screen.getByRole('button', { name: 'I accept, install' }))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith('14'))
    expect(boundarySetsApi.installPack).toHaveBeenCalledWith('eu-nuts1', true)
  })

  it('installs nothing when the terms are cancelled', async () => {
    vi.mocked(boundarySetsApi.packs).mockResolvedValue([EU] as never)
    picker()
    fireEvent.click(await screen.findByRole('button', { name: /EU NUTS-1/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByTestId('pack-terms')).not.toBeInTheDocument()
    expect(boundarySetsApi.installPack).not.toHaveBeenCalled()
  })
})

describe('BoundarySetPicker accessibility', () => {
  it('has no structural accessibility violations, terms panel open', async () => {
    vi.mocked(boundarySetsApi.packs).mockResolvedValue([{
      id: 'eu-nuts1', name: 'EU NUTS-1 regions', country: null, level: 'NUTS-1', feature_count: 123,
      description: 'd', source: 'Eurostat', license: 'terms', license_url: 'https://example.invalid/l',
      attribution: '© EuroGeographics', terms: 'Credit the source.', requires_acceptance: true,
    }] as never)
    const { container } = render(<BoundarySetPicker value="" onChange={() => {}} />)
    fireEvent.click(await screen.findByRole('button', { name: /EU NUTS-1/ }))
    await screen.findByTestId('pack-terms')
    expect(await axeViolations(container)).toEqual([])
  })
})
