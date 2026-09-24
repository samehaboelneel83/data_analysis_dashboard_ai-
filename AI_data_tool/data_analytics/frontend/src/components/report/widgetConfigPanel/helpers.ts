import type { WidgetType } from '../../../types/report'
import { ROLE_SPECS, configKeyFor } from '../../../types/report'

export const CUSTOM_SHAPE_WIDGET_TYPES = new Set<WidgetType>([
  'histogram', 'butterfly', 'dual_axis_bar', 'dual_axis_line', 'dual_axis_bar_line',
  'dual_axis_time_series', 'comparative_time_series', 'numeric_series', 'bubble',
  'bubble_change', 'correlation_matrix', 'heatmap', 'parallel_coordinates', 'box_plot',
  'waterfall', 'gauge', 'schedule', 'vector_plot', 'card', 'ribbon',
])

export const RUNNING_OPTIONS = [
  { value: '',    label: 'None' },
  { value: 'sum', label: 'Running Sum' },
  { value: 'avg', label: 'Running Average' },
]

// Display-only helper for the Appearance colour swatches: reads the CSS custom
// property's actual computed value off <html> so the swatch shows the widget's real
// untouched colour (WidgetRenderer.tsx falls back to var(--surface)/var(--border)
// when the config key is absent) rather than a hardcoded hex guess that would be
// wrong under the other theme. Never used to decide what gets saved -- see the
// "empty string is untouched" convention documented at the Appearance state block.
export function readCssVarColor(varName: string, fallback: string): string {
  if (typeof window === 'undefined' || typeof window.getComputedStyle !== 'function') return fallback
  const v = window.getComputedStyle(document.documentElement).getPropertyValue(varName).trim()
  return v || fallback // jsdom (tests) resolves custom properties from stylesheets to '' -- falls back here
}

export function seedRoleValues(cfg: Record<string, unknown>, wt: WidgetType): Record<string, string> {
  const values: Record<string, string> = {}
  for (const rf of (ROLE_SPECS[wt] ?? []).filter(rf => !rf.multi)) {
    values[rf.role] = (cfg[configKeyFor(rf.role)] as string) ?? ''
  }
  return values
}

export function seedMultiRoleValues(cfg: Record<string, unknown>, wt: WidgetType): Record<string, string[]> {
  const values: Record<string, string[]> = {}
  for (const rf of (ROLE_SPECS[wt] ?? []).filter(rf => rf.multi)) {
    values[rf.role] = Array.isArray(cfg[rf.role]) ? (cfg[rf.role] as string[]) : []
  }
  return values
}

export function widgetIcon(wt: string) {
  return ({ bar:'▬',line:'↗',pie:'◔',donut:'◯',scatter:'⁘',treemap:'⊞',step:'⊓',dot_plot:'⁚',needle:'↕',histogram:'▤',butterfly:'⋈',dual_axis_bar:'▥',dual_axis_line:'⤢',dual_axis_bar_line:'▧',dual_axis_time_series:'⟿',comparative_time_series:'⇄',numeric_series:'∿',bubble:'◉',bubble_change:'◎',correlation_matrix:'▦',heatmap:'▩',parallel_coordinates:'⫴',box_plot:'⊡',waterfall:'▨',gauge:'◐',schedule:'▭',vector_plot:'⇗',word_cloud:'☁',kpi:'◈',table:'☰',crosstab:'⊟',list:'≡',text:'T',button:'▶',image:'⛶',shape:'▭' } as any)[wt] ?? '◻'
}
