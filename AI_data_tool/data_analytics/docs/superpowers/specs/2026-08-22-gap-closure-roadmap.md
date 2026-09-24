# Gap-Closure Roadmap

**Baseline:** 132 Yes / 26 Partial / 118 No of 276 rows — **47.8%** — as of 2026-08-22,
verified against the code (all file references, symbols and config keys checked; category
04 verified empirically by the demo content).

**Goal of this document:** the cheapest defensible route from 47.8% to ~75%, ordered by
*user-visible value per unit of engineering risk* — not by row count. A row that unlocks
adoption (export, maps) outranks three rows of editor chrome.

## How the plan is optimized

Three observations drive the ordering:

1. **Rows cluster around shared infrastructure.** Category 05's fifteen rows share one
   map renderer. Category 11's scheduling rows share one job runner (which already
   exists for dataset refresh). Category 08's four parameter rows share one parameter
   store. Build the shared piece once and the rows fall in groups — so phases below are
   *infrastructure-first*, and their row counts are the consequence.
2. **Some rows are cheap because the code is already there.** The refresh scheduler, the
   display-rules engine, the RLS layer and the export resolver are extension points that
   phases 1–3 lean on. Nothing below requires a rewrite of anything.
3. **Two clusters are deliberately last or never.** Category 06's ML rows need a
   modelling stack (scipy → statsmodels → sklearn) — a dependency-policy decision that
   should be made once, explicitly, not smuggled in. And a handful of rows are
   platform-shaped (native mobile app, marketplace, gateway management) where the honest
   answer is "not this product, or not yet".

Every phase ends the way the last three did: suites green, the app driven by hand,
the gap document re-scored against the code. That discipline caught seven defects a
green suite missed this week; it is part of the plan, not overhead.

---

## Phase A — Geo & mapping (cat 05: 0/0/15 → ~11 Yes)

**The single highest-value block remaining.** Both competitors score near-full here; it
is the most-cited reason a BI tool gets rejected on sight, and it is self-contained: one
library, one shaper family, one renderer family. No changes to the calculation engine,
the security model, or any existing widget.

- **Library ruling needed up front:** MapLibre GL (BSD, no token, vector tiles) over
  Leaflet (simpler, raster). Recommend **MapLibre** — the isochrone/route rows are
  unreachable either way, but vector styling covers choropleth + point + bubble + line
  in one renderer.
- **Offline-first tiles:** a bundled world/countries GeoJSON (choropleth needs no tile
  server at all) plus an optional tile-provider URL in settings. A map that breaks
  without internet is a demo liability.
- Shaper: one `shape_geo` handling `{region|lat/lon} × measure` → rows keyed by ISO
  code or coordinates. Name/code lookup via a bundled country/region table (row:
  "Geographic name / code lookup roles").
- Widgets: `map_choropleth`, `map_points`, `map_bubbles` (+ clusters via supercluster),
  layered to give "Multi-layer maps". The demo gains a fifth page exercising them —
  which keeps the 42→45 coverage test honest.

**Closes:** choropleth, point, bubble, cluster, line-layer, multi-layer, lat/lon
columns, name/code lookup, map backgrounds (~9–11 rows). **Leaves:** isochrones,
demographics, custom shape import (needs a shapefile pipeline), pie map.
**Estimate:** the largest single phase; comparable to phase 3 of the formatting work.

## Phase B — Export & distribution, part 2 (cat 11: 1/2/18 → ~8 Yes)

The document's own #1 ranked gap. Split in two because the halves need different
infrastructure:

**B1 — Rendering out (no new services):**
- **Export visual as an image** — client-side SVG→PNG serialisation of the widget's
  chart; no server component. Cheap, high demand.
- **Print layout + PDF** — a print stylesheet route (`/reports/:id/print`) that lays
  pages out linearly, plus server-side PDF via headless Chromium (Playwright is already
  in the dev stack). PDF resolves through the same widget-data path as the export
  endpoint — same RLS argument as CSV/Excel, already proven there.
- **Copy link at report/page level + URL parameter presets** — routes already encode
  report id; add page + filter state to the query string, parse on load. Two rows,
  mostly frontend.
- Complete **CSV → Yes** (add TSV + whole-dataset export, the two things that keep it
  Partial).

**B2 — Scheduled delivery (one new service):**
- The **refresh scheduler already runs jobs on an interval with an advisory lock** —
  extend it, don't duplicate it: a `report_schedules` table (report, cron-ish interval,
  format, recipients) drained by the same loop.
- **Email via SMTP settings** (env-configured); a delivery is "render the PDF from B1,
  attach, send". Teams delivery is the same payload to a webhook URL — nearly free once
  email works.
- **Data-condition alerts** hang off the existing display-rules engine: an alert is an
  expression rule evaluated on schedule, firing the same delivery path. This is exactly
  how SAS models it. **In-app notifications** ride the same events table.

**Closes:** ~10–12 rows across B1+B2. **Leaves:** PowerPoint, offline package,
guest access (a security decision), comments, workspaces, lineage.
**Estimate:** B1 ≈ half a phase; B2 ≈ half, dominated by delivery plumbing.

## Phase C — Parameters & prompts (cat 08: 14/5/13 → ~20 Yes)

One design closes seven rows: a **report-level parameter store** — named, typed
(numeric / character / date / expression) values, settable from slicer-like controls,
referenced as `@param` in filters and calculated expressions.

- The expression sandbox already blocks `@`-resolution in pandas eval — parameters get
  substituted *before* evaluation, preserving that boundary. This is the one subtle
  security spot; it is contained in one function.
- **Report-level prompts** = parameters surfaced at report open; **cascading prompts** =
  a prompt whose option list is filtered by an earlier prompt's value; **set prompt
  values instead of filtering** = a button action writing a parameter. All the same store.
- Alongside: **custom sort order** and **multi-column sort** (shaper-level, small),
  **post-aggregate filters** (a HAVING step after grouping — the measures engine
  already computes at the right grain), **rank top/bottom N → Yes** (bottom-N plus
  ties handling is what keeps it Partial).

**Closes:** ~8–10 rows. **Estimate:** one phase; the parameter store is the only
design-heavy piece.

## Phase D — Layout containers (cat 09: 6/0/10 → ~12 Yes)

All ten No rows are one feature family. Order of build:

1. **Standard container** — a widget that owns child widgets and lays them out; the
   grid packer from the demo work already does the geometry.
2. **Stacking container (tabs)** on the same parent-child model; **scrolling container**
   is a CSS overflow mode of the standard one; **prompt container** is the standard one
   with a collapse header — the `CollapsibleSide`/`ExpandableGroup` pattern already
   shipped twice.
3. **Object/page templates**: serialise a container or page subtree to JSON, reinsert
   with new ids — which is also **import pages from another report** (same serialise/
   rehydrate path, cross-report).
4. **Per-user page visibility**: a `visible_to_roles` list on the page, enforced
   server-side where pages are listed (it is an RLS-adjacent check, not a client hide).

**Closes:** ~8 rows. **Estimate:** one phase; the container model is the design risk —
worth a spec before implementation.

## Phase E — Small-rows sweep (many categories, ~12 rows, cheapest per row)

Rows that are one-to-three days each and need no new infrastructure. Batch them the way
the SDD phases batched same-shape work:

| Row | Why it's cheap |
|---|---|
| 07 Per-object data-limit override | config key + one shaper read; pattern exists |
| 07 Periodic auto-reload | `setInterval` on the widget fetch, opt-in config |
| 07 Custom/imported theme | THEMES is data; add a JSON import/save per report |
| 07 Grid lines & wall background → Yes | the remaining sub-options in axisOptions |
| 04 Bar with target line → Yes | reference-line support exists; wire the `target` role |
| 04 Gauge → Yes | the remaining sub-options (thresholds already shipped as bands) |
| 04 Dynamic text bound to a measure | text block + `{measure}` interpolation through the export resolver |
| 04 Sparkline in a table | a cell format type; the bar cell-format pattern exists |
| 02 Duplicate a data item | copy a calculated column / dataset row; CRUD only |
| 12 Audit log | append-only table on the existing auth'd mutation paths |
| 12 Granular export disablement | a per-report flag the export endpoint checks |
| 13 Heading styles for screen readers | `role="heading"` + `aria-level` on widget titles |

**Closes:** ~12 rows across six categories. **Estimate:** one phase, low risk,
high row-yield — good interleaving work between the bigger phases.

## Phase F — Advanced analytics, gated (cat 06: 2/0/18 → up to ~10 Yes)

**Blocked on one explicit decision: adopt scipy + statsmodels (and optionally sklearn)
as dependencies.** Everything here is downstream of it; nothing elsewhere is.

If yes, in value order: **forecasting** (statsmodels ETS/ARIMA on the existing
time-series shaper) with **confidence bands** (two rows, and the most-asked-for
analytics feature); **what-if** on the forecast inputs; `PvalT` (closes the last
statistics Partial); **Sankey** (a renderer + a source-target shaper — no ML at all,
could even move to phase E); **decision tree / clustering visuals** (sklearn) after.

**Leaves honestly No:** NL Q&A, smart narratives, goal-seeking, topic modelling —
LLM-or-research-grade features that deserve their own initiative if ever.

## Deliberately not planned

Composite models (query planner), native mobile app (PWA is the answer), visual
marketplace / code-driven visuals (plugin sandbox — a security surface that dwarfs its
value today), gateway management & deployment pipelines (platform operations), NL Q&A
and narratives (see F), isochrones/demographics (paid geo services).
These rows stay No with reasons recorded, and the percentage they cost is the price of
honesty — the document exists to direct work, not to flatter it.

## Projected arithmetic

| After | Yes rows (±) | ≈ % |
|---|---|---|
| today | 132 | 47.8% |
| A (geo) | +10 | 51.4% |
| B (export 2) | +11 | 55.4% |
| C (parameters) | +9 | 58.7% |
| D (containers) | +8 | 61.6% |
| E (sweep) | +12 | 65.9% |
| F (analytics, if adopted) | +8 | ~68.8% |

Remaining ~30 gap rows after F are the deliberately-not-planned set plus long-tail
Partials. **~69% against SAS VA + Power BI combined** is a defensible ceiling for a
product this size; pushing past it means the plugin sandbox and the ML suite.

## Recommended execution order

**A → B1 → E → C → B2 → D → F.** Geo first for maximum visible value; B1 early because
image/PDF export is the top adoption blocker after geo; E interleaved as relief work;
C before B2 because parameters make scheduled reports far more useful (a schedule that
can set parameters covers most real distribution needs); D when the container spec is
written; F when the dependency ruling lands.

Each phase: spec → plan → SDD execution with per-task review → whole-branch review →
fix wave → drive it in the app → re-score the gap document. As run four times now.
