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

## Ready-made looks, and more chart types in the suggestions (2026-10-12)

Asked, with four reference dashboards: offer in the suggestions panel the kinds of widget those dashboards use — and every widget type that can be added — and give dashboards a modern style like them.

### Looks
* **Six one-click looks** at the top of the dashboard style panel (`lib/dashboardLooks.ts`): Midnight (navy, green and blue charts), Deep space (near-black, outlined cards, blue and violet), Ember (near-black, one orange accent), Graphite (neutral dark), Clean (light, borderless, soft shadow), Outline (white, thin borders). A look is only a filled-in style: every control below it can still be changed, and the look in use is marked until one is.
* **A look sets the chart palette too**, as one undoable step. Three palettes were added for dark canvases (Emerald, Aurora, Amber).
* **A headline number's change is a tinted pill and its history line is filled** underneath — on every dashboard, not only the new looks.
* **Fixed on the way:** on a dark dashboard inside a light app the chart grid lines were drawn in the app's light rule colour — bright white lines across every chart. They now follow the look.
* Screenshots: `docs/templates/looks/`.

### Suggestions
The panel offered 6 chart types on the sample dashboard; it now offers 18. After the ideas the data argues for (unchanged, and still first), it adds one idea for each further widget type the data has the shape for (`suggest_variety.catalogue_suggestions`), each with the reason it fits in one sentence, each drawn on the reader's rows before it is offered:

| offered | when |
|---|---|
| one amount against another (bullet bar) | two numbers that add up, of one size, that move together |
| the same two back to back by a category; and over time | as above, plus a category / a date |
| progress bar | an averaged number whose every value lies between 0 and 1 |
| list of headline numbers | three or more numbers read the same way |
| dot plot | an averaged number and a category |
| two numbers by a category, two scales; and over time | two numbers and a category / a date |
| filled area over time; stepped line over time | a date covering 90 days or more, with a number that adds up / one that is averaged |
| ribbon (who leads, month by month) | a date, a category of 3–8 values, a number that adds up |
| waterfall | a number that adds up and a category |
| histogram; one number against another; correlation grid; parallel lines | one, two, three or more numbers |
| cross table; flow (sankey) | two categories |
| small multiples | a category and a second one of 2–6 values |
| ranked list; word cloud | a category of many values |

How many are added is an admin setting ("Suggestions panel: further chart types offered", default 12, 0 = none).

**Checked:** 3 tests of the looks (complete, readable, one click), 3 of the catalogue (every idea draws and names real columns; a shape the data lacks is not offered; the panel's own ideas stay first and unchanged). On screen: a dashboard built from the new suggestions, in four looks.

**Not done**
* **Radar and a per-category progress list** — two widgets in the reference pictures — do not exist as widget types yet; the nearest that do (dot plot, progress bar for one number) are offered instead.
* **Maps, hierarchies, funnels and schedules are not suggested this way**: whether they fit cannot be told from the columns alone (a place, a nesting, an order of stages, a start and an end).
* The new ideas' titles and reasons are English only; the takeaway sentence under each is translated as before.
* The looks do not restyle the app around the dashboard (side bar, top bar): only the dashboard's own area.
* A gradient or glow on cards, as in two of the pictures, is not a style setting.

### Gradient (same day, asked with a fifth picture)
* **A headline number with a history is laid out as in the picture**: the number at the start, its change as a pill at the end, and the history as a line across the whole width of the card with a fill that fades downwards. Each card's line takes its own colour from the dashboard's palette. A number without a history is centred as before.
* **Area charts fade towards the axis** instead of a flat tint, one gradient per series.
* Screenshots: `docs/templates/looks/kpi-gradient-*.png`. 1 more browser test.
* Seen on screen and left: in a narrow card a long number is cut with "…" because the pill shares its row.

## "Executive summary": a reference dashboard as a template (2026-10-12)

Asked, with a picture of an executive dashboard: can the platform make the same dashboard on other data?

* **A built-in template, "Executive summary"** (`builtin.BUILTIN["executive"]`), laid out as the picture: three headline numbers each with its change on the period before and on the year before; the main number over time beside them; its months with a forecast; what goes with a higher value of it (key influencers); a map; a ranked bar; quarters — and three more pages as tabs (Trends, Groups, Detail). Filters across the top: a from–to date range, a dropdown and buttons.
* **It asks for a number and a date; everything else is optional** (two more numbers, two ways to split, a place). A chart whose column is not mapped is left out and the rest move up, as with every template.
* **Its own look**: white cards on a pale page, one family of blues.
* **Bars can lie down** (`orientation: "horizontal"`, `BarChartRenderer`): each name on its own line, read whole. New for this; a single series only.
* **A narrow headline card no longer cuts its number**: the change drops under it.

**Checked:** made on two unrelated datasets (62,662 shipments; 14,269 car listings) — every chart on all four pages drew on both. Screenshots: `docs/templates/looks/executive-summary-template*.png`. The template passes the tests every built-in passes (valid, resolves, draws every chart on its sample, every word has its Arabic); 2 browser tests of horizontal bars.

**Not as the picture**
* **The map depends on the place names matching a known boundary set.** On the first dataset (governorates of one country) it did not draw the regions; on the second it drew the country as one shape. The template is right; the map data for sub-national regions is what is missing.
* **The forecast is drawn in the trend chart itself**, not as a separate "next six months" bar chart: the third box of the bottom row shows quarters instead.
* **Horizontal bars are set by the template; the chart settings panel has no switch for them yet.**
* The automatic mapping takes the first suitable number; in the gallery's "Use" dialog the person chooses which number is followed.

### Key influencers: options for how they are shown (same day)
The widget drew one way only: the model's line, the row counts, tabs, then a bar per influencer. Its settings now hold six display choices (the figures behind them are unchanged):

| option | choices | default |
|---|---|---|
| Drawn as | bars · bubbles (a line to a circle, longer and larger the further from usual) | bars |
| Show what goes with | higher and lower · a higher value · a lower value — and the reader can switch it on the chart | both |
| How many to show | 1 to 50 | all |
| Number shown | automatic · how far from usual (+23.5%) · times the usual (1.24×) · the group's own value | automatic |
| Decimal places | automatic · 0 to 3 | automatic |
| Show the model's own lines | on · off (only the influencers: no model line, row counts or tabs) | on |

The "Executive summary" template uses bubbles, "a higher value", the first six, and the model lines off — which is what the reference picture shows. 6 browser tests.

## "What goes together": association rules read by role (2026-10-12)

Asked, with a picture of five "association roles" widgets: can the platform make the same dashboard on other data?

* **Five new views of the rules widget** (`chartRenderers/RuleRoles.tsx`; setting "Show as" on a "what goes together" widget): a **network** coloured by role with an arrow where a link is one-way; a **roles matrix** (the row's value towards the column's: A, C, B or none); a **role summary** (for each value, how many others it points to, is pointed to by, or both); the **rules table** with each value tagged by its role in that rule, with support, confidence and lift; and a **chord diagram** (values as arcs of a ring, a ribbon per linked pair, thicker with more rules). All five are counted from the rules the server already mines — nothing new is computed on the data.
* **A built-in template, "What goes together"**, lays the five out as the picture. It asks for two columns of labels and takes up to four.
* **What "role" means here.** A value is an antecedent where rules start from it and a consequent where they conclude it. The miner reports most links in both directions (the lift is the same either way), which on a first try made every value "both" — true and useless. So a link counts as one-way when one direction's confidence is at least 1.2 times the other's, and as both ways when they are closer. The matrix says so under it.
* A long list is cut to the 10 most connected values (a setting, 2 to 30), and says "the 10 most connected of 15".

**Checked:** made on two unrelated datasets — every view drew on both; on the first, 2 values came out antecedent, 2 consequent, 6 both. 7 browser tests; the template passes the tests every built-in passes. Screenshot: `docs/templates/looks/what-goes-together-template.png`.

**Not as the picture**
* The network puts the values on a circle; the picture puts one chosen value in the middle with the others around it.
* The chord's ribbons are curved bands of one width each, not the tapered ribbons of a full chord diagram.
* The picture's "items" are things bought together (one row per basket and item). The widget does that too when given a group column and an item column, but the template maps columns of labels in ordinary rows; a basket version of the template is not made.
* The 1.2 threshold is fixed in the code, not a setting.

## One dashboard per analysis technique (2026-10-12)

Asked, with two pictures of "dashboard templates for data analysis techniques" (16 and 9 of them): can the platform make the same dashboards, to show insights and analytics?

**A new group in the gallery, "Analysis"**, with a template for each technique the platform already computes. Each is named for the question it answers, asks for the few columns it needs, and works on any table.

| picture | template | what it lays out |
|---|---|---|
| Descriptive | What is in the data | rows, average, lowest, highest; how a number is spread; rows by a column; the number within each group |
| Correlation | Which numbers move together | every pair of up to five numbers; the first against the others as point clouds; each row across them |
| Association rules | What goes together | the five role views (section above) |
| Clustering | Natural groups | the groups as a picture; what each is like; how well they hold apart |
| Classification | Which outcome a row will have | how well it predicts; right and wrong (confusion matrix); against a coin toss (ROC); what matters most; odds |
| Regression | What a number depends on | how well it is explained; actual against predicted; where it misses (residuals); what each factor adds |
| Time series, Predictive | A number through time | headline with history; months and a forecast; month of the year; day of the week |
| Anomaly, Outlier | What is out of the ordinary | months outside their usual range and where the level changed; spread within groups; distribution |
| Text | What a column of text says | cloud; ranked list; by group |
| Network | What is connected to what | network; most-linked ends; flow; grid |
| Diagnostic | Where a number comes from | contribution of each group (waterfall); the few that carry it; groups over time |
| Geospatial | Places (existing) | |
| Executive | Executive summary (section above) | |

**What had to be added for them**
* **Any view of a fitted model as a tile of its own** ("Show only" on a model widget; `model_tab`): a page can put the confusion matrix beside the ROC curve, or residuals beside actual-against-predicted, instead of behind tabs.
* **Two numbers as a cloud of points** (`points` on the number-against-number chart): a random sample across the whole range, drawn as dots. It drew a line through the 500 rows with the smallest x — on 62,662 rows, one sliver at the left edge.
* **An optional column inside a list** (`"$?c"`): the chart keeps the columns the dataset has instead of being left out whole.
* **Fixed on the way:** the network chart failed with a server error whenever some rows had one end of a link empty.

**Checked:** all ten made on two unrelated datasets (62,662 shipments; 14,269 car listings): every chart drew on both after the fixes. They pass the tests every built-in passes; 3 more tests (optional columns, the network fix, the point cloud). Screenshots of three: `docs/templates/looks/analysis-*.png`.

**No template, because the platform does not have the technique as a chart**
* **Survival analysis** (survival curves, median time) — not in the platform.
* **Dimensionality reduction** (PCA with explained variance) — the groups picture uses a two-dimensional projection, but there is no explained-variance chart.
* **Optimization / what-if** — the decision problems and simulations exist as analyses on the dataset's Analysis tab, not as dashboard charts.
* **Data quality** (completeness, validity, uniqueness as charts) — the checks exist on the dataset; there is no chart of them.
* **Classification metrics as four separate numbers** (accuracy, precision, recall, F1) and **a comparison of several models' ROC curves** — the page shows one model's fit text, matrix and curve; precision, recall and F1 are not computed.
* **Time-series decomposition** (trend, seasonal and residual as stacked panels) and a **seasonal radar** — month of the year and day of the week are bars instead.
* The pictures' top rows of filter dropdowns for the method itself (model type, number of clusters, threshold, minimum support) — those are settings of the widget, not page filters.
