# RTL (Right-to-Left) Option for All Widgets

**Date:** 2026-06-30
**Status:** Approved

## Overview

Add a per-widget RTL toggle that lets report authors flip any widget to right-to-left layout. For chart widgets this means a true axis reversal (data reads right-to-left); for HTML-rendered widgets it means flipping text direction and flex layout via `dir="rtl"`.

## Scope

All 12 widget types: `bar`, `line`, `pie`, `donut`, `scatter`, `treemap`, `kpi`, `table`, `crosstab`, `list`, `text`, `button`.

## Config Storage

`rtl` is stored as a boolean inside the existing `widget.config` object (`Record<string, unknown>`). Default is `false` (absent = LTR). No schema migrations or type changes are required.

```json
{ "dimension": "country", "measure": "revenue", "rtl": true }
```

## UI — WidgetConfigPanel

A single checkbox labelled **"RTL (Right to Left)"** is added directly below the **Title** field in `WidgetConfigPanel.tsx`. It is visible for every widget type.

- State: `const [rtl, setRtl] = useState<boolean>(cfg.rtl ?? false)`
- Synced in the existing `useEffect` that resets state on widget change
- Included in every config branch of the emit `useEffect` (text, button, and the general branch)

## Rendering — WidgetRenderer

`cfg.rtl` is read in `WidgetBody` and applied per widget type:

### Chart widgets (Recharts)

| Widget | Change |
|---|---|
| `bar` | `XAxis reversed={rtl}` + `YAxis orientation={rtl ? 'right' : 'left'}` |
| `line` | Same as bar |
| `scatter` | `XAxis reversed={rtl}` + `YAxis orientation={rtl ? 'right' : 'left'}` |
| `pie` / `donut` | `dir="rtl"` on the `ResponsiveContainer` wrapper div — flips legend |
| `treemap` | `dir="rtl"` on the `ResponsiveContainer` wrapper div |

### HTML widgets

| Widget | Change |
|---|---|
| `kpi` | `dir={rtl ? 'rtl' : undefined}` on the outer container div |
| `table` / `crosstab` | `dir={rtl ? 'rtl' : undefined}` on the scroll container div |
| `list` | `dir={rtl ? 'rtl' : undefined}` on the scroll container div |
| `text` | `dir={rtl ? 'rtl' : undefined}` on the content div |
| `button` | `dir={rtl ? 'rtl' : undefined}` on the centering div |

The `dir` attribute propagates naturally through the DOM, reversing flex layout order, text alignment, and scroll direction for all descendant elements.

## Files Changed

| File | Change |
|---|---|
| `frontend/src/components/report/WidgetConfigPanel.tsx` | Add `rtl` state, sync, toggle UI, include in emitted config |
| `frontend/src/components/report/WidgetRenderer.tsx` | Read `cfg.rtl`, apply per-widget RTL logic in `WidgetBody` |

No backend changes. No new files.

## Out of Scope

- Page-level or report-level RTL (each widget is independent)
- Reversing column order in table/crosstab (column sequence stays; text direction flips)
- Tooltip RTL positioning (tooltips are positioned by Recharts automatically)
