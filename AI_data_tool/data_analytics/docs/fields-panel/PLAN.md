# Dashboard "Fields" panel — evaluation and plan

Date: 2026-10-09 · Owner request: "Fields has duplicated logic features and can be more
helpful; test every feature as a user, then fix any error or wrong logic."

## How it was tested

As a user in Chrome (Claude in Chrome), on a scratch dashboard "Fields panel test
(Claude)" over the dataset *Cars 2015+* (12 columns: text, numbers, a year, a link):
clicked fields with and without a selected chart, every per-field button (⌖ Σ ⇄ ? ⌄),
the search box, reclassification, report filters, and read the Hierarchy section.

## What the panel holds today (top to bottom)

Datasets · hint · search · **Dimensions / Dates / Geography / Hierarchies / Measures /
Aggregated** (each field: tick box, field button, ⌖ Classify, Σ Calculations, ⇄ Reclassify,
? Explain, ⚠ Outliers, ⌄ Properties) · **Hierarchy** (folder tree: Dimensions / Measures /
Dates / Text, each field again with ✏ × ⇄, plus "Auto") · Calculated columns · Duplicate a
column · Custom functions · Report filters.

## Problems found

| # | What the user sees | Why (code) |
|---|---|---|
| P1 | `model_year` is listed under **Dimensions** but shows `#`, gets the measure buttons (⇄ "treat as category", ? "what moves model_year"), and a click draws a **histogram** of it | Two rules answer "is this a quantity?": `fieldGroupOf` knows a year/ID is not a quantity; `isNumericField` (icon, buttons, click, drop, auto chart) does not |
| P2 | Adding `price_egp` to "Count by make" **keeps counting** and keeps the title "Count by make" | `planFieldOnWidget` fills the measure but keeps the chart's `count` aggregation and the auto title |
| P3 | Dropping a measure with a category always **sums** it ("price by make" = sum of prices) | `chartForFields` hard-codes `aggregation: 'sum'`; the app's own `defaultSummary` (average for prices, ages, rates) is not used |
| P4 | Clicking `item_url` draws **"Count by item_url"** — 9,319 bars of height 1 | Auto-chart has no notion of a link or of a column whose every value is unique |
| P5 | Every field is listed **twice** (field list + Hierarchy folder tree), and the copies **disagree**: `model_year` is a measure in the tree; `item_url` (added later) is missing; ⇄ moves a field in the list but not in the tree; search filters the list but not the tree | The Hierarchy is a separately saved folder tree, regenerated only by "Auto" |
| P6 | Classification can be changed in **four** places (⌖, ⇄, ⌄ Properties, the tree's ⇄) | Features added over time, never merged |
| P7 | A report filter added in the panel is **invisible** on the canvas: the filter bar says "No selections", the toolbar Filter shows no count — the charts are silently filtered | Report filters (`common_filters`) are only listed at the bottom of the Fields tab |
| P8 | ⌖ "Classify" only offers **map geography** (it does not classify dimension/measure); it is offered on numbers reclassified as categories (km); its menu does not close with Escape | Label; condition on `isNumericField`; menu without a key handler |
| P9 | Σ offers **"% of total"** for a price | Quick calcs ignore whether a quantity can be added up |
| P10 | ⇄, ?, ⚠ are `<span role="button">`; Space does not activate them | Not real buttons |

## Plan

- [x] **F1 One rule for "is this a quantity?"** — `isNumericField` follows the same rule as
      the groups (years, IDs, codes are categories unless the author said "measure"), so the
      icon, the buttons, a click, a drop and the auto chart all agree with the list. (P1)
- [x] **F2 A measure joining a chart is summarised sensibly** — joining a counting chart
      switches it to the measure's default summary (average for prices/ages/rates, sum for
      amounts); an automatic title follows ("Average price_egp by make"). (P2)
- [x] **F3 Auto chart uses the default summary** — every measure placed by a click or a
      drop starts on `defaultSummary` (avg/sum/…), never a blind sum. (P3)
- [x] **F4 Links and unique columns become a list** — a link (http values / url-like name /
      `semantic_type: url`) or a column whose values are all different becomes a table, not
      a bar chart. (P4)
- [x] **F5 One list of fields** — the folder tree leaves the main view: folded into
      "Organize fields into folders" (closed by default) so nothing is lost, and it no longer
      competes with the list. The list's own "Hierarchies" group (real drill paths) stays
      and follows the search. (P5, part of P6)
- [x] **F6 One place to classify** — ⌄ Properties is the place; ⇄ stays as its one-click
      shortcut on number columns (a real button); ⌖ is renamed "Map region (geography)",
      shown only on text columns, and closes with Escape. (P6, P8, P10)
- [x] **F7 Report filters visible where the charts are** — active report filters show as
      chips in the canvas filter bar (removable there), and the panel's section moves to the
      top of the panel, under the datasets. (P7)
- [x] **F8 Quick calcs that make sense** — no "% of total" for a quantity that cannot be
      added up (price, age, rate…). (P9)
- [x] **F9 Re-test everything as a user in Chrome**, English and Arabic; frontend tests,
      type check, build.

## Found during the re-test (fixed too)
- Properties → Aggregation said **"Default (Sum)"** for every field, even a price that is
  averaged: it now names the real default ("Default (Average)").
- The category quick calc **"% of rows"** had no translation (English in Arabic): added.
- An auto chart of an averaged measure was titled "car_age_years by body_type", which reads
  as a total: titles now say "Average car_age_years by body_type" (also median, lowest,
  highest, distinct), English and Arabic.
- **mileage** was summed per group (the total of every car's odometer): a mileage /
  odometer reading is now averaged like an age — frontend and backend rules both.

## Log
- 2026-10-09: evaluation done, plan written; implementation started.
- 2026-10-10: F1–F8 implemented; F9 re-test passed. Details below.

## Results (F9)

Automated: type check clean; frontend **338 files / 4,248 tests pass** (new tests: year
column grouping, report filter chips in both bar styles + removal, "% of total" hidden for a
price, auto chart default summary + title, link → list, mileage averaged); production
build OK; backend semantic-guard + guided-setup tests **253 pass**.

As a user in Chrome (scratch dashboard over *Cars 2015+*, deleted afterwards):

| Check | Result |
|---|---|
| `model_year` under Dimensions with `Aa`, no histogram/measure buttons; ⇄ moves it to Measures and back | ✅ |
| Fresh "Count by make" + click `price_egp` → "Average price_egp by make", `avg` | ✅ |
| Click `item_url` → "List of item_url" table (was 9,319 bars) | ✅ |
| Tick `body_type` + `car_age_years` → Auto chart → `avg`; `mileage_km` → `avg` | ✅ |
| Report filter shows on the canvas ("Filters: condition equals (=) Used ×"), × removes it, charts re-query; panel section sits under Datasets | ✅ |
| View mode (Modern chips): the filter shows read-only, tooltip "Applies to every widget" | ✅ |
| Σ on price / mileage: no "% of total"; on `make`: "Distinct values", "% of rows" | ✅ |
| ⌄ Properties of price: "Default (Average)" | ✅ |
| Folder tree folded under "Organize fields into folders" (closed); search "price" shows only price | ✅ |
| ⌖ only on text columns, labelled "Map geography for …", Escape closes it; no `span role=button` left | ✅ |
| Arabic: all new strings translated, chips read correctly right-to-left, auto title "متوسط mileage_km حسب fuel_type" | ✅ |
| Console errors | none |

Note: a chart built before these fixes keeps what it was saved with (e.g. a "Count by make"
that already holds price with `count`): the fixes act when a chart is made or changed.
