/**
 * Build a suggested dashboard with the same calls a person makes by hand.
 *
 * Moved out of SuggestDashboardsDialog so the guided setup's Dashboard step
 * (docs/guided-setup/PLAN.md, 4b) builds exactly what the dialog builds: the
 * same sizes, the same packed layout, the same relations wired after every
 * widget exists, and the same "leave out what could not be created" rule.
 */
import {
  calcColumnsApi, measuresApi, reportsApi,
  type CalcColumn, type DashboardSuggestion, type MeasureDef, type SuggestedWidget,
} from '../services/api'

/** How much room a widget needs, by kind.
 *
 * Sized rather than slotted into a fixed grid. Ten hand-built dashboards in this
 * repository laid their top row out at h=2 — the height a single number wants —
 * and every chart and multi-value card in that row was clipped: axis labels
 * collided, and a three-figure card scrolled, showing its middle value and a
 * sliver of the one above. A generated page must not ship that.
 */
export function sizeFor(widget: SuggestedWidget): { w: number; h: number } {
  const wt = widget.widget_type
  if (wt === 'kpi' || wt === 'gauge') return { w: 3, h: 2 }
  // A filter control: the server puts these first, in one band.
  if (wt === 'slicer') return { w: 4, h: 3 }
  if (wt === 'card') {
    const measures = (widget.config?.measures as unknown[])?.length ?? 1
    return { w: 3, h: Math.max(3, 2 + measures) }
  }
  if (wt === 'table' || wt === 'crosstab' || wt === 'matrix' || wt === 'list')
    return { w: 12, h: 5 }
  if (wt === 'correlation_matrix' || wt === 'parallel_coordinates'
      || wt === 'sankey' || wt === 'network' || wt === 'org'
      || wt.startsWith('map_')) return { w: 12, h: 5 }
  return { w: 6, h: 4 }
}

/** Lay the widgets out left to right, wrapping at 12 columns. Small tiles
 *  naturally gather at the top because that is the order a proposal arrives in
 *  — headline numbers first — and nothing is ever placed shorter than it needs. */
export function layout(widgets: SuggestedWidget[]) {
  const out: { x: number; y: number; w: number; h: number }[] = []
  let x = 0, y = 0, rowHeight = 0
  for (const widget of widgets) {
    const { w, h } = sizeFor(widget)
    if (x + w > 12) { x = 0; y += rowHeight; rowHeight = 0 }
    out.push({ x, y, w, h })
    x += w
    rowHeight = Math.max(rowHeight, h)
  }
  return out
}


export function withoutFields(p: DashboardSuggestion, missing: Set<string>): DashboardSuggestion {
  if (missing.size === 0) return p
  const names = (w: SuggestedWidget) => JSON.stringify(w.config ?? {})
  const keep = p.widgets.filter(w => ![...missing].some(n => names(w).includes(`"${n}"`)))
  // Relations index the widgets: drop any that pointed at a removed one.
  const index = new Map(p.widgets.map((w, i) => [i, keep.indexOf(w)]))
  const relations = (p.relations ?? [])
    .map(r => ({ ...r, from: index.get(r.from) ?? -1, to: index.get(r.to) ?? -1 }))
    .filter(r => r.from >= 0 && r.to >= 0)
  return { ...p, widgets: keep, relations }
}


/** Build one proposal with the same calls the person could make by hand. The
 *  server proposes and never creates; composing it here keeps that true. */
export async function fillPage(reportId: number, pageId: number, proposal: DashboardSuggestion) {
    // The panel lays each section out on the server; the quick designer's
    // proposals are sized here.
    const slots = proposal.widgets.every(w => w.layout)
      ? proposal.widgets.map(w => w.layout!)
      : layout(proposal.widgets)
    // Saved as a packed page: a page with no mode is re-flowed by the
    // builder's default recipe on first open, which squeezed a four-figure
    // card into a two-row tile on the HR panel's first dashboard.
    await reportsApi.updatePage(reportId, pageId, { layout_mode: 'packed' } as never)
    // Sequential: widget order is id order everywhere else in this app, and
    // firing them together would leave the tiles in whatever order the server
    // happened to finish.
    const createdIds: number[] = []
    for (let i = 0; i < proposal.widgets.length; i++) {
      const widget = proposal.widgets[i]
      const made = await reportsApi.addWidget(
        reportId, pageId as number,
        { widget_type: widget.widget_type, title: widget.title,
          config: widget.config, layout: slots[i] } as never)
      createdIds.push((made as { id: number })?.id)
    }

    // SECOND PASS, and it has to be: a relation is stored as an action against
    // a real widget id, and those ids do not exist until every widget above
    // has been created. Writing the proposal's own indices here would point
    // each action at whatever widget happens to hold that id — a different
    // chart, quite possibly on someone else's dashboard.
    const bySource = new Map<number, { targetId: number; mode: 'filter' | 'highlight' }[]>()
    for (const rel of proposal.relations ?? []) {
      const from = createdIds[rel.from]
      const to = createdIds[rel.to]
      if (!from || !to) continue
      bySource.set(from, [...(bySource.get(from) ?? []), { targetId: to, mode: rel.mode }])
    }
    const configs = proposal.widgets.map(w => ({ ...(w.config ?? {}) }) as Record<string, unknown>)
    for (const [widgetId, actions] of bySource) {
      const index = createdIds.indexOf(widgetId)
      configs[index] = { ...configs[index], interaction: { broadcasts: true, receives: true, actions } }
      await reportsApi.updateWidget(reportId, pageId as number, widgetId, {
        config: configs[index],
      } as never)
    }
    return { ids: createdIds, configs }
}


/** The fields the proposals draw that the dataset lacks (a rate of totals,
 *  a duration) are created first, with the same calls the field editor
 *  makes. Returns the names that could NOT be created -- the person may
 *  not edit this dataset -- so the widgets that need them are left out
 *  rather than shown broken. */
export async function createDerivedFields(
  datasetId: number,
  derived: { measures: MeasureDef[]; calculated_columns: CalcColumn[] },
): Promise<Set<string>> {
  const failed = new Set<string>()
  for (const col of derived.calculated_columns) {
    try { await calcColumnsApi.save(datasetId, col) } catch { failed.add(col.name) }
  }
  for (const m of derived.measures) {
    try { await measuresApi.save(datasetId, m) } catch { failed.add(m.name) }
  }
  return failed
}

/** One proposal as a new dashboard on `datasetId`; returns the dashboard id. */
export async function buildDashboard(datasetId: number, proposal: DashboardSuggestion,
                                     derived: { measures: MeasureDef[]; calculated_columns: CalcColumn[] },
                                     name: string, description: string): Promise<number> {
  const missing = await createDerivedFields(datasetId, derived)
  const report = await reportsApi.create({ name, description, dataset_id: datasetId } as never)
  const reportId = (report as { id: number }).id
  const pageId = (report as { pages?: { id: number }[] }).pages?.[0]?.id as number
  await fillPage(reportId, pageId, withoutFields(proposal, missing))
  return reportId
}
