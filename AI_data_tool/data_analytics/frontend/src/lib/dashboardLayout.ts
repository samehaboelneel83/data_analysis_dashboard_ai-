/** Packed / free 12-column dashboard layout: recipes, compact, swap, min sizes. */

export const COLS = 12

export type GridLayout = { x: number; y: number; w: number; h: number }
export type LayoutItem = { id: number; widget_type: string; layout: GridLayout }
export type RecipeId =
  | 'executive'
  | 'kpi_board'
  | 'two_by_two'
  | 'split'
  | 'spotlight'
  | 'comparison'
  | 'detail'
  | 'three_up'
export type LayoutMode = 'packed' | 'free'

export const DEFAULT_RECIPE: RecipeId = 'executive'
export const DEFAULT_MODE: LayoutMode = 'packed'

export const RECIPES: { id: RecipeId; label: string; hint: string }[] = [
  { id: 'executive', label: 'Executive', hint: 'KPIs on top, hero chart, table below' },
  { id: 'kpi_board', label: 'KPI board', hint: 'Dense KPIs, then one full-width trend' },
  { id: 'two_by_two', label: '2 × 2', hint: 'Equal tiles, wrapping two-across' },
  { id: 'split', label: 'Split', hint: 'Two equal columns' },
  { id: 'spotlight', label: 'Spotlight', hint: 'One large hero, others in a row under it' },
  { id: 'comparison', label: 'Comparison', hint: 'KPI strip and two charts side by side' },
  { id: 'detail', label: 'Detail', hint: 'Table first, charts underneath' },
  { id: 'three_up', label: 'Three-up', hint: 'Three equal columns of charts' },
]

const KPI_TYPES = new Set(['kpi', 'card', 'gauge', 'needle'])
const WIDE_TYPES = new Set([
  'table', 'crosstab', 'matrix', 'list',
  'map_choropleth', 'map_points', 'map_bubbles', 'map_lines', 'map_clusters',
  'map_pie', 'map_layers', 'map_density', 'map_network',
  'network', 'sankey', 'decomposition', 'small_multiples',
])
const CHROME_TYPES = new Set(['text', 'button', 'slicer', 'image', 'shape', 'web_content'])

export type WidgetFamily = 'kpi' | 'chart' | 'wide' | 'chrome'

export function widgetFamily(type: string): WidgetFamily {
  if (KPI_TYPES.has(type)) return 'kpi'
  if (WIDE_TYPES.has(type)) return 'wide'
  if (CHROME_TYPES.has(type)) return 'chrome'
  return 'chart'
}

export function minSize(type: string): { w: number; h: number } {
  const fam = widgetFamily(type)
  if (fam === 'kpi') return { w: 3, h: 2 }
  if (fam === 'chrome') return { w: 2, h: 2 }
  if (fam === 'wide') return type.startsWith('map') || type === 'network' ? { w: 6, h: 5 } : { w: 6, h: 4 }
  return { w: 4, h: 4 }
}

export function overlaps(a: GridLayout, b: GridLayout): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
}

function overlapArea(a: GridLayout, b: GridLayout): number {
  const x = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x))
  const y = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y))
  return x * y
}

export function clampLayout(type: string, layout: GridLayout): GridLayout {
  const min = minSize(type)
  const w = Math.min(COLS, Math.max(min.w, layout.w))
  const h = Math.max(min.h, layout.h)
  const x = Math.max(0, Math.min(COLS - w, layout.x))
  const y = Math.max(0, layout.y)
  return { x, y, w, h }
}

function cloneItems(items: LayoutItem[]): LayoutItem[] {
  return items.map(i => ({ id: i.id, widget_type: i.widget_type, layout: { ...i.layout } }))
}

function byReadingOrder(items: LayoutItem[]): LayoutItem[] {
  return [...items].sort((a, b) => a.layout.y - b.layout.y || a.layout.x - b.layout.x || a.id - b.id)
}

function toMap(items: LayoutItem[]): Record<number, GridLayout> {
  return Object.fromEntries(items.map(i => [i.id, i.layout]))
}

/** Gravity-up compact: keep x, close vertical holes, no overlap. */
export function compact(items: LayoutItem[]): Record<number, GridLayout> {
  const sorted = byReadingOrder(items).map(i => ({
    ...i,
    layout: clampLayout(i.widget_type, i.layout),
  }))
  const placed: LayoutItem[] = []
  for (const item of sorted) {
    let y = 0
    let guard = 0
    while (guard++ < 400) {
      const trial = { ...item.layout, y }
      const hit = placed.find(p => overlaps(trial, p.layout))
      if (!hit) {
        placed.push({ ...item, layout: trial })
        break
      }
      y = hit.layout.y + hit.layout.h
    }
  }
  return toMap(placed)
}

function placeRow(
  layouts: Record<number, GridLayout>,
  ids: number[],
  types: Record<number, string>,
  y: number,
  columns: number,
  rowH: number,
): number {
  if (!ids.length) return y
  let i = 0
  let yCur = y
  while (i < ids.length) {
    const remaining = ids.length - i
    let cols = Math.max(1, Math.min(columns, remaining))
    while (cols > 1) {
      const slice = ids.slice(i, i + cols)
      const need = Math.max(...slice.map(id => minSize(types[id]).w))
      if (Math.floor(COLS / cols) >= need) break
      cols -= 1
    }
    const baseW = Math.floor(COLS / cols)
    let rowHUsed = rowH
    for (let j = 0; j < cols; j++) {
      const id = ids[i + j]
      const min = minSize(types[id])
      rowHUsed = Math.max(rowHUsed, min.h)
    }
    for (let j = 0; j < cols; j++) {
      const id = ids[i + j]
      const min = minSize(types[id])
      const x = j * baseW
      const w = j === cols - 1 ? COLS - x : baseW
      layouts[id] = clampLayout(types[id], { x, y: yCur, w: Math.max(w, min.w), h: rowHUsed })
    }
    yCur += rowHUsed
    i += cols
  }
  return yCur
}

function placeHeroAndSide(
  layouts: Record<number, GridLayout>,
  charts: number[],
  types: Record<number, string>,
  y: number,
): { y: number; rest: number[] } {
  if (!charts.length) return { y, rest: [] }
  const hero = charts[0]
  if (charts.length === 1) {
    layouts[hero] = clampLayout(types[hero], { x: 0, y, w: 12, h: 6 })
    return { y: y + layouts[hero].h, rest: [] }
  }
  const side = charts[1]
  layouts[hero] = clampLayout(types[hero], { x: 0, y, w: 8, h: 6 })
  layouts[side] = clampLayout(types[side], { x: 8, y, w: 4, h: 6 })
  const rowH = Math.max(layouts[hero].h, layouts[side].h)
  layouts[hero].h = rowH
  layouts[side].h = rowH
  return { y: y + rowH, rest: charts.slice(2) }
}

function partition(items: LayoutItem[]) {
  const ordered = byReadingOrder(items)
  const kpis: LayoutItem[] = []
  const chrome: LayoutItem[] = []
  const charts: LayoutItem[] = []
  const wides: LayoutItem[] = []
  for (const it of ordered) {
    const fam = widgetFamily(it.widget_type)
    if (fam === 'kpi') kpis.push(it)
    else if (fam === 'chrome') chrome.push(it)
    else if (fam === 'wide') wides.push(it)
    else charts.push(it)
  }
  return { kpis, chrome, charts, wides }
}

export function applyRecipe(items: LayoutItem[], recipe: RecipeId): Record<number, GridLayout> {
  const layouts: Record<number, GridLayout> = {}
  const types = Object.fromEntries(items.map(i => [i.id, i.widget_type])) as Record<number, string>
  const { kpis, chrome, charts, wides } = partition(items)
  const kpiIds = [...kpis, ...chrome].map(i => i.id)
  const chartIds = charts.map(i => i.id)
  const wideIds = wides.map(i => i.id)
  const restAll = [...chartIds, ...wideIds]

  let y = 0
  y = placeRow(layouts, kpiIds, types, y, 4, 2)

  if (recipe === 'executive') {
    const placed = placeHeroAndSide(layouts, chartIds, types, y)
    y = placeRow(layouts, placed.rest, types, placed.y, 2, 5)
    y = placeRow(layouts, wideIds, types, y, 1, 5)
  } else if (recipe === 'kpi_board') {
    if (chartIds.length) {
      layouts[chartIds[0]] = clampLayout(types[chartIds[0]], { x: 0, y, w: 12, h: 5 })
      y += layouts[chartIds[0]].h
      y = placeRow(layouts, chartIds.slice(1), types, y, 2, 5)
    }
    y = placeRow(layouts, wideIds, types, y, 1, 5)
  } else if (recipe === 'two_by_two') {
    y = placeRow(layouts, restAll, types, y, 2, 5)
  } else if (recipe === 'split') {
    const left: number[] = []
    const right: number[] = []
    restAll.forEach((id, i) => (i % 2 === 0 ? left : right).push(id))
    let yL = y
    let yR = y
    for (const id of left) {
      const h = Math.max(5, minSize(types[id]).h)
      layouts[id] = clampLayout(types[id], { x: 0, y: yL, w: 6, h })
      yL += layouts[id].h
    }
    for (const id of right) {
      const h = Math.max(5, minSize(types[id]).h)
      layouts[id] = clampLayout(types[id], { x: 6, y: yR, w: 6, h })
      yR += layouts[id].h
    }
    y = Math.max(yL, yR)
  } else if (recipe === 'spotlight') {
    if (chartIds.length) {
      layouts[chartIds[0]] = clampLayout(types[chartIds[0]], { x: 0, y, w: 12, h: 7 })
      y += layouts[chartIds[0]].h
      y = placeRow(layouts, [...chartIds.slice(1), ...wideIds], types, y, 4, 4)
    } else {
      y = placeRow(layouts, wideIds, types, y, 1, 5)
    }
  } else if (recipe === 'comparison') {
    if (chartIds.length === 1) {
      layouts[chartIds[0]] = clampLayout(types[chartIds[0]], { x: 0, y, w: 12, h: 6 })
      y += layouts[chartIds[0]].h
    } else if (chartIds.length >= 2) {
      layouts[chartIds[0]] = clampLayout(types[chartIds[0]], { x: 0, y, w: 6, h: 6 })
      layouts[chartIds[1]] = clampLayout(types[chartIds[1]], { x: 6, y, w: 6, h: 6 })
      y += 6
      y = placeRow(layouts, chartIds.slice(2), types, y, 2, 5)
    }
    y = placeRow(layouts, wideIds, types, y, 1, 5)
  } else if (recipe === 'detail') {
    y = placeRow(layouts, wideIds, types, y, 1, 5)
    const placed = placeHeroAndSide(layouts, chartIds, types, y)
    y = placeRow(layouts, placed.rest, types, placed.y, 2, 5)
  } else if (recipe === 'three_up') {
    y = placeRow(layouts, restAll, types, y, 3, 5)
  }

  const placedItems = items.map(i => ({
    ...i,
    layout: layouts[i.id] ?? clampLayout(i.widget_type, i.layout),
  }))
  return compact(placedItems)
}

const SWAP_OVERLAP = 0.35

export function dropPacked(
  items: LayoutItem[],
  movingId: number,
  dest: { x: number; y: number },
): Record<number, GridLayout> {
  const next = cloneItems(items)
  const moving = next.find(i => i.id === movingId)
  if (!moving) return toMap(next)
  const proposed = clampLayout(moving.widget_type, { ...moving.layout, x: dest.x, y: dest.y })
  let swapWith: LayoutItem | undefined
  let best = 0
  for (const other of next) {
    if (other.id === movingId) continue
    const area = overlapArea(proposed, other.layout)
    const denom = Math.min(proposed.w * proposed.h, other.layout.w * other.layout.h)
    if (denom > 0 && area / denom >= SWAP_OVERLAP && area > best) {
      best = area
      swapWith = other
    }
  }
  if (swapWith) {
    const from = { x: moving.layout.x, y: moving.layout.y }
    moving.layout = clampLayout(moving.widget_type, { ...moving.layout, x: swapWith.layout.x, y: swapWith.layout.y })
    swapWith.layout = clampLayout(swapWith.widget_type, { ...swapWith.layout, x: from.x, y: from.y })
  } else {
    moving.layout = proposed
  }
  return compact(next)
}

function pushOverlapsDown(items: LayoutItem[], resizedId: number): void {
  const resized = items.find(i => i.id === resizedId)
  if (!resized) return
  for (let n = 0; n < items.length * 4; n++) {
    let moved = false
    for (const other of items) {
      if (other.id === resizedId) continue
      if (overlaps(resized.layout, other.layout)) {
        other.layout.y = resized.layout.y + resized.layout.h
        moved = true
      }
    }
    if (!moved) break
  }
}

export function resizePacked(
  items: LayoutItem[],
  id: number,
  w: number,
  h: number,
): Record<number, GridLayout> {
  const next = cloneItems(items)
  const target = next.find(i => i.id === id)
  if (!target) return toMap(next)
  target.layout = clampLayout(target.widget_type, { ...target.layout, w, h })
  pushOverlapsDown(next, id)
  return compact(next)
}

function nearestFree(want: GridLayout, others: GridLayout[]): GridLayout {
  const fits = (trial: GridLayout) => !others.some(o => overlaps(trial, o))
  if (fits(want)) return want
  for (let dy = 0; dy <= 80; dy++) {
    for (const dx of [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6]) {
      const trial = clampLayout('bar', { ...want, x: want.x + dx, y: want.y + dy })
      // clampLayout('bar') may bump min size — use want's w/h already clamped
      const placed = { ...want, x: trial.x, y: Math.max(0, want.y + dy) }
      placed.x = Math.max(0, Math.min(COLS - placed.w, want.x + dx))
      if (fits(placed)) return placed
    }
  }
  return { ...want, y: others.reduce((m, o) => Math.max(m, o.y + o.h), 0) }
}

export function dropFree(
  items: LayoutItem[],
  movingId: number,
  dest: { x: number; y: number },
): Record<number, GridLayout> {
  const next = cloneItems(items)
  const moving = next.find(i => i.id === movingId)
  if (!moving) return toMap(next)
  const want = clampLayout(moving.widget_type, { ...moving.layout, x: dest.x, y: dest.y })
  const others = next.filter(i => i.id !== movingId).map(i => i.layout)
  moving.layout = nearestFree(want, others)
  return toMap(next)
}

export function resizeFree(
  items: LayoutItem[],
  id: number,
  w: number,
  h: number,
): Record<number, GridLayout> {
  const next = cloneItems(items)
  const target = next.find(i => i.id === id)
  if (!target) return toMap(next)
  target.layout = clampLayout(target.widget_type, { ...target.layout, w, h })
  for (let n = 0; n < next.length * 4; n++) {
    let moved = false
    for (const other of next) {
      if (other.id === id) continue
      if (overlaps(target.layout, other.layout)) {
        other.layout.y = target.layout.y + target.layout.h
        moved = true
      }
    }
    if (!moved) break
  }
  return toMap(next)
}

export function needsAutoPack(mode: string | null | undefined): boolean {
  return mode == null || mode === ''
}

export function isRecipeId(value: string | null | undefined): value is RecipeId {
  return !!value && RECIPES.some(r => r.id === value)
}

export function toLayoutItems(
  widgets: { id: number; widget_type: string; layout: GridLayout }[],
): LayoutItem[] {
  return widgets.map(w => ({ id: w.id, widget_type: w.widget_type, layout: { ...w.layout } }))
}

export function itemsOverlap(items: LayoutItem[]): boolean {
  for (let i = 0; i < items.length; i++) {
    for (let j = i + 1; j < items.length; j++) {
      if (overlaps(items[i].layout, items[j].layout)) return true
    }
  }
  return false
}

export function layoutChanged(a: GridLayout, b: GridLayout): boolean {
  return a.x !== b.x || a.y !== b.y || a.w !== b.w || a.h !== b.h
}

export function isPackedMode(mode: string | null | undefined): boolean {
  return mode !== 'free'
}
