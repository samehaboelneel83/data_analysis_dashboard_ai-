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
  // The page's answer in words (guided setup): a full-width band above the charts.
  if (wt === 'text') {
    // Tall enough for every line: the note under the answer (what the page is
    // limited to, or what the data does not hold) must never be cut off.
    const content = String((widget.config as { content?: string })?.content ?? '')
    const lines = content.split('\n').reduce((n, part) => n + Math.max(1, Math.ceil(part.length / 95)), 0)
    return { w: 12, h: lines <= 3 ? 2 : lines <= 7 ? 3 : 4 }
  }
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


/** `layout`, with no ragged right edge: the last chart of each row grows to
 *  the page's width (a number and one chart left a quarter of the row empty).
 *  A row of small number tiles only is left as it is. */
export function filledLayout(widgets: SuggestedWidget[]) {
  const slots = layout(widgets)
  let start = 0
  for (let i = 1; i <= slots.length; i++) {
    if (i < slots.length && slots[i].y === slots[start].y) continue
    const last = slots[i - 1]
    const type = widgets[i - 1].widget_type
    if (type !== 'kpi' && type !== 'gauge' && type !== 'card') last.w = 12 - last.x
    start = i
  }
  return slots
}

export interface DashboardPagePlan {
  datasetId: number
  /** The part of the data the person asked for: set once on the dashboard. */
  scope?: { column: string; op: string; value: unknown }[]
  proposal: DashboardSuggestion
  derived: { measures: MeasureDef[]; calculated_columns: CalcColumn[] }
}

/** Several proposals as the PAGES of one dashboard (guided setup, PLAN_V2 4e).
 *
 *  Someone who ticks three suggestions wants one dashboard to open, not three
 *  to find: each proposal becomes a page named after it, in the order given.
 *  With `reportId` the pages are added to that dashboard instead of making a
 *  new one. A page on a dataset other than the dashboard's own carries the
 *  dataset on each widget, as the builder does. Returns the dashboard id. */
export async function buildPages(pages: DashboardPagePlan[], name: string, description: string,
                                 reportId?: number | null): Promise<number> {
  if (!pages.length) throw new Error('nothing to build')
  // The fields a dataset lacks are created once, whatever number of its pages use them.
  const missing = new Map<number, Set<string>>()
  for (const p of pages) {
    const failed = await createDerivedFields(p.datasetId, p.derived)
    missing.set(p.datasetId, new Set([...(missing.get(p.datasetId) ?? []), ...failed]))
  }

  let primary: number
  let firstPageId: number | null = null
  let position = 0
  let extra: number[] = []
  let rid: number
  let scoped: string[] = []
  if (reportId) {
    const report = await reportsApi.get(reportId)
    rid = reportId
    scoped = ((report as { common_filters?: unknown[] }).common_filters ?? []).map(f => JSON.stringify(
      [(f as { column: string }).column, (f as { op: string }).op, (f as { value: unknown }).value]))
    primary = (report as { dataset_id?: number }).dataset_id ?? pages[0].datasetId
    position = (report as { pages?: unknown[] }).pages?.length ?? 0
    extra = ((report as { additional_dataset_ids?: number[] }).additional_dataset_ids ?? []).slice()
  } else {
    primary = pages[0].datasetId
    const report = await reportsApi.create({ name, description, dataset_id: primary } as never)
    rid = (report as { id: number }).id
    firstPageId = (report as { pages?: { id: number }[] }).pages?.[0]?.id ?? null
  }
  const others = [...new Set(pages.map(p => p.datasetId).filter(id => id !== primary && !extra.includes(id)))]
  if (others.length) await reportsApi.update(rid, { additional_dataset_ids: [...extra, ...others] })

  // The person's scope is ONE filter on the dashboard -- seen in its filter bar,
  // removed there in one click -- not a condition hidden in every chart.
  for (const f of pages.flatMap(p => p.scope ?? [])) {
    const mark = JSON.stringify([f.column, f.op, f.value])
    if (scoped.includes(mark)) continue
    scoped.push(mark)
    try { await reportsApi.addCommonFilter(rid, f) } catch { /* the charts still draw, unnarrowed */ }
  }

  for (const p of pages) {
    const title = p.proposal.title || name
    let pageId: number
    if (firstPageId != null) {
      pageId = firstPageId
      firstPageId = null
      await reportsApi.updatePage(rid, pageId, { name: title } as never)
    } else {
      const made = await reportsApi.addPage(rid, { name: title, position })
      pageId = (made as { id: number }).id
    }
    position += 1
    const usable = withoutFields(p.proposal, missing.get(p.datasetId) ?? new Set())
    const onPage = p.datasetId === primary ? usable : {
      ...usable,
      widgets: usable.widgets.map(w => w.widget_type === 'text' ? w
        : { ...w, config: { ...(w.config ?? {}), dataset_id: p.datasetId } }),
    }
    const slots = filledLayout(onPage.widgets)
    await fillPage(rid, pageId, { ...onPage, widgets: onPage.widgets.map((w, i) => ({ ...w, layout: slots[i] })) })
  }
  return rid
}
