# Geo & Mapping Implementation Plan (Phase A)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or
> direct execution with the same review discipline. Steps use checkbox syntax.

**Goal:** Close the choropleth / point / bubble slice of gap category 05 (0/0/15) with an
offline-first, SVG-based map family.

**Spec:** `docs/superpowers/specs/2026-08-22-gap-closure-roadmap.md` (Phase A), amended by
the spike ruling below.

**Ruling (spike, 2026-08-22):** d3-geo + topojson-client + world-atlas, **not MapLibre**,
overruling the roadmap's initial recommendation. Evidence: MapLibre is 19.4 MB unpacked
and WebGL-based — jsdom cannot execute WebGL, so every renderer test would be a mock;
d3-geo is 227 kB, renders SVG exactly like the app's existing hand-drawn renderers
(BoxPlot), is assertable under the existing test suite, and needs no tile server, so the
map works offline by construction. Cost: the "Map background providers" row stays No,
recorded honestly.

**Architecture:**
- **Backend stays almost empty.** Region-mode maps consume the *existing* `shape_series`
  output ({name, value} rows keyed by country) — `SHAPERS` gains three aliases. One new
  shaper, `shape_geo_points`, passes through lat/lon(/name/value) columns with the
  standard row cap. All existing filter/RLS/measure machinery applies unchanged.
- **Geometry and matching live in one frontend module** (`geo/worldGeometry.ts`):
  world-atlas 110m topojson → features, a name index with an alias table (US/USA/UK…),
  and centroids computed from the geometry itself via d3-geo — no hand-typed
  coordinate table to drift.
- **Three widget types** — `map_choropleth`, `map_points`, `map_bubbles` — two renderers
  (points and bubbles share one, radius fixed vs ∝ value). Both accept region mode
  (country column → centroid) and, for points/bubbles, lat/lon columns.
- The demo grows a Maps page covering all three (the 42→45 coverage test enforces this
  before anything else does).

## Global Constraints
- Unmatched country names must be *visible* (a listed count, not silently unpainted).
- The map chunk stays out of the initial bundle (charts/geo manualChunk).
- Every widget returns non-empty data through the real widget-data path in the demo.
- Suites at start: backend 864, frontend 479. tsc errors: 9 (pre-existing).

### Task 1: worldGeometry module + tests
- [x] features/nameIndex/centroid/aliases; deliberate-failure checks on matching
### Task 2: renderers + catalog/roles/SHAPERS + tests
- [x] GeoChoroplethRenderer, GeoPointMapRenderer; WidgetType 42→45
### Task 3: backend shape_geo_points + SHAPERS aliases + tests
### Task 4: demo Maps page + coverage to 45
### Task 5: drive in the app, fix, re-score gap doc
