# Dashboard templates — what was built (2026-10-11)

A dashboard stored as a **reusable specification**: pages, layouts, widget settings, metric definitions, filters and style, with the columns taken out and replaced by named **slots** ("a number", "a date", "a category"). Using a template on a dataset is: map each slot to a column, check the mapping, resolve the specification into real pages.

```
Gallery ──► Mapping and validation ──► Resolve ──► Dashboard
categories   columns -> slots, from      pages, widgets,   the person's own:
previews     what each column IS         measures, style   move, resize, replace,
search       (type + stored class)       filter controls   duplicate, remove
favourites   checked before anything     click-to-filter   -- the template is
             is made                                        untouched
```

## The specification (`datalytics.dashboard-template/1`)

`backend/app/services/dashboard_templates/spec.py`

* **slots** — `{id, label, kind, required, many?, number?, max_distinct?, same_unit?}`; kinds: measure · category · date · stage · geography · flag · detail.
* **metrics** — `{id, label, expression}` with `{slot}` in the expression; created on the dataset as defined measures (the same checks and the same version history as a measure saved by hand).
* **pages** — widgets with `layout` on the 12-column grid; a config value `"$slot"` is the mapped column, `"$m:metric"` is a metric; `{slot}` in a title is the column's label. `relations` are click-to-filter links by position.
* **filters** — slots that become a row of filter controls above every page (a date range, a dropdown).
* **style** — see below.

A widget that refers to a slot nobody mapped is **left out and named**; nothing is guessed. Only the slots a template marks required must be filled.

## The pieces

| | |
|---|---|
| `builtin.py` | Ten templates of the platform, one per kind: overview, scorecard, trends and seasons, stages and conversion, target against actual, activity monitor, groups compared, places, spread and outliers, rows explorer. **Named for what they show, never for a line of business** — the owner's rule; what the boxes are called comes from the columns a person maps. |
| `mapping.py` | Columns described from their type and stored classification (never their name against a word list); `suggest` fills each slot with its best free column; `validate` says what a mapping would give; `fit` scores a template for a dataset — half the share of charts it can draw, half how surely the columns are what the slots mean (an ordered column for a stage, a target in the same unit as what it is measured against). |
| `resolve.py` | Specification + mapping → pages, widgets, measures, filters, style. Pure: the same result is shown before creating and written when creating. A measure the dataset already defines the same way is used, not defined twice. |
| `capture.py` | An existing dashboard → specification. Columns become slots, defined measures become metrics; filters and colour rules on particular **values** are removed and counted (they mean nothing on other data); ids become positions. |
| `sample.py` | Each template drawn on **its own sample rows**, made from its slots (placeholder values: "Group A", "Stage 2") — a real preview with no dataset chosen and nobody's data in it. Saved templates get one too. |

## API (`/api/v1/templates`)

`GET ""` (with `dataset_id`: ranked by fit) · `GET /{ref}` · `GET /{ref}/preview` · `POST /{ref}/match` · `POST /{ref}/use` · `POST ""` (from a dashboard, or a copy of a template) · `PUT /{id}` · `GET /{id}/versions` · `POST /{id}/versions/{vid}/restore` · `DELETE /{id}` · `PUT /{ref}/favorite`. A ref is `builtin:<key>` or `t:<id>`.

* **Permissions.** A saved template is personal (its author only) or shared with the organisation. Its author or an organisation administrator may change or delete it; built-in ones are read-only (take a copy). A column a reader's role may not see is not there to be mapped. Defining measures needs data-level access to the dataset; without it the charts that need a measure are left out, and the dialog says so.
* **Versions.** Whatever changes a template's content (taking a dashboard again, a new style) keeps the version before it (30 kept); restoring makes a new version.
* Tables: `dashboard_templates`, `dashboard_template_versions`, `template_favorites`; column `reports.style` (revision 0066).

## Dashboard style (fonts, borders, and the rest)

`reports.style`, edited in the builder under **Page properties → Dashboard style**, applied wherever a dashboard is drawn (builder, viewer, shared link, embed, print) and carried by templates, versions and releases.

Light or dark · font family (system, sans, serif, monospace, rounded, condensed, Arabic) · text size · title size, weight, position and colour · text colour · headline number size · accent · page and card background · border type (none, solid, dashed, dotted, double), width and colour · corner radius · shadow.

A widget's own appearance settings still win. Fonts are named font stacks: a family that is not installed on the reader's machine falls back to the next in its stack — no font files are shipped or downloaded.

## In the product

* **Templates** in the left navigation: the gallery — tabs (All, Built-in, Organisation, Mine, Favourites), kinds, search, "Match to a dataset" (ranks and marks the best match; a template that does not fit says what is missing), preview, use, copy, edit details, versions, delete.
* **Use template**: dataset, the suggested mapping (changeable), a live check after every change — how many charts, which are left out and why, which measures will be defined, which filter controls.
* **Builder → Templates tab**: "Save as template" and a link to the gallery.

## How it answers the six requirements

1. **Widget compatibility** — a slot's kind decides which columns may fill it; an identifier, a text or a date is never offered as a number to total.
2. **Global filters** — date range and category controls above every page; click-to-filter links between charts.
3. **Performance** — nothing here reads rows: mapping uses columns and stored classification, charts are drawn by the existing server-side aggregation with its cache and limits; ranked bars carry a limit.
4. **Customisation** — what is made is an ordinary dashboard; the template is never touched by it.
5. **Save and reuse** — personal or organisational, with permissions and versions.
6. **AI assistance** — the recommendation is computed from the dataset's columns, with no model: it cannot invent a column or change a metric's definition. **No model is used anywhere in this feature.**

## Checked

* 46 tests of the rules (every built-in template resolves into widgets the engine accepts and draws every chart on its sample), 12 through the real routes, 12 in the browser tests; the whole browser suite passes.
* **Live, on the 62,662-row table:** all ten built-in templates made a dashboard and every chart drew; a dashboard was saved as a template, used on another dataset, updated (version 2), restored (version 3), starred and deleted.
* **In the browser:** the gallery, the sample preview (real charts in the template's own style) and the mapping dialog were opened; the style editor changed a border and the cards redrew.

## Second round (2026-10-11): the first "Not done" list, worked through

* **What a built-in template writes is in the reader's language.** Chart titles, page names, measure names and (in the sample preview) column labels are written in Arabic for an Arabic reader (`words.py`, 100 entries; a test requires an Arabic for every English and the same slots in both). A saved template says what its author wrote.
* **More than one dataset.** A dashboard's additional datasets are carried: their columns become slots *of that dataset*, and using the template asks for a dataset for each (optional — without one, its charts are left out and nothing of it is required). Measures are defined on the dataset their columns belong to; a dataset of another organisation cannot be given.
* **No holes where charts were left out.** In a row that lost a chart the ones that stayed share its width in the proportions they had; a row that lost every chart closes (`resolve.reflow`).
* **An optional setting** (`"$?slot"`): a headline number keeps its figure and loses only its history when no date is mapped. Before, the whole number was left out.
* **Buttons and drill-through** are carried by the page's name and wired to the new dashboard's own pages when it is made; a drill-through page keeps the column it opens for, as a slot. A link to a page that was left out goes with it.
* **Fonts are shipped.** Six open-licence families (Inter, Merriweather, JetBrains Mono, Nunito, Roboto Condensed, Noto Kufi Arabic — SIL OFL, `@fontsource` packages, added to `package.json`) are served by the app itself and fetched only when a dashboard uses one. Seen loaded in the browser.
* **Seen in Arabic and on a phone** (375 px wide): the gallery is in Arabic, wraps without sideways scrolling, and the cards are full width. The preview was unreadable on a phone (twelve columns in 327 px) — it now stacks the charts full width in reading order.

Checked: 59 tests of the rules and 14 through the routes (73), 13 browser tests; live, an Arabic reader's dashboard from "Performance overview" with only two columns mapped came out with Arabic titles and a full-width layout.

## Third round (2026-10-11): the second "Not done" list

* **The desktop was looked at.** Full-size screenshots (1440 × 900, the installed Chrome driven headless) of the gallery, three previews and the mapping dialog, in English and in Arabic. Two things were wrong and are fixed: a template's thumbnail did not fill its card and a dark template's sat in a white box; and a preview's titles read "Total The number to follow" (now "Total the number to follow"). Arabic mirrors correctly: navigation on the right, the grid from the right, dialogs right-aligned. (My first Arabic screenshots were laid out left-to-right because my script set the language without the direction the app stores beside it — an error of the script, not of the app.)
* **The image rebuild was run.** `docker compose build frontend` finished without error and the new image holds the six font packages. The running container was not replaced.
* **A measure over two datasets cannot exist.** A defined measure belongs to one dataset and is evaluated on that dataset's rows, so no dashboard can hold one; the case arises only in a specification written by hand, where it is refused by name. Nothing to carry.
* **The gallery and additional datasets.** A template's charts that read another dataset are counted apart — "3 more charts read another dataset (costs), chosen when you use it" — and no longer lower its fit or appear as missing.
* **Re-flow fills what is left.** After sharing a row's width and closing empty rows, a chart takes the empty room beside it, and the room under it when another chart is below (never more than twice its height, never over another chart).

Still seen and not changed, because they are the chart renderers' own and not the templates': a long title runs under a card's menu button; on the cumulative-share chart the right axis's label sits over its tick numbers in a narrow card; the "Reference" label can touch the last bar's value.

## Not done

* Built-in templates are by kind of analysis; none named for a line of business ships (the platform's own rule).
* Re-flow rearranges; it does not choose other chart kinds or re-design a page.
* Anyone may share their own template with the organisation; there is no approval step.
* The builder's style editor and a dashboard made from a template were measured in the browser, not screenshotted at full size.
* Not measured on a dataset with hundreds of columns.
