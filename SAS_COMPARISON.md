# Datalytics vs SAS Visual Analytics

A capability comparison, read out of the two SAS Visual Analytics course
narrations (236 sections, ~3,150 lines) and checked against this platform's
running code.

---

## Read this before the tables

**The two sides were measured by different instruments, and that matters more
than any single row below.**

The SAS side comes from course narration: an authoritative account of what SAS
Visual Analytics *offers*. It is a feature list written by the people who built
it. It contains no defects, because a course never contains defects.

This side was measured by using the product. In the twenty-four hours before
this document, that turned up: an Interactions panel whose every setting was
discarded on reload; sixteen widget types offering text columns to fields that
require numbers; a report canvas laying tiles out at a stale 900px and wasting
several hundred pixels; an endpoint returning a data profile for datasets the
user is not allowed to open. Every one returned HTTP 200. Not one would have
appeared in a course narration of this platform either.

So: **a tick below means the capability exists and was checked. It does not mean
it is as good as SAS's.** And a SAS tick is taken on trust from the course.
Where we could verify a SAS limitation from the narration itself, it is noted.

### This document has been corrected, repeatedly

The first draft of these tables was written partly from memory of our own code.
Turning it into a roadmap meant re-reading that code properly, and **seven cells
were wrong — every one of them understating what we already had**, including one
labelled "the deepest gap" that had shipped months earlier.

They are corrected below and each correction says so. The lesson is worth more
than the corrections: the asymmetry described above cuts both ways. A course
narration is complete about its product because someone wrote it all down. A
memory of a codebase is not, and the errors it produces are not random — they run
in whichever direction the writer was not looking.

Since then the corrections have kept coming, and they no longer run in one
direction. Two ran the other way — a ✅ that was true of the builder and false
everywhere else (cross-filtering on nine map widgets; every interaction setting
on a shared link or an embed, §9). Both were found by driving the product, not
by reading it.

So read a ✅ here as: **the behaviour is executed by a test on every surface
that offers it, and the server half of it has been called on a running
server.** That is stronger than a feature list and weaker than a human having
clicked it in a browser. Where a cell rests on a browser-rendered detail that
only a person can confirm, it says so.

### Not everything called "SAS Visual Analytics" is one product

The courses freely mix the base product with separately licensed things. Course
2 says it plainly — *"With SAS Visual Statistics, you also have access to an
additional growth strategy"*, *"Recall that adding these advanced radius-based
geographic areas incurs an additional charge."* Comparing an entire platform
against SAS-base-plus-four-add-ons is not a fair comparison, so they are kept
apart:

| Tier | What it covers |
|---|---|
| **SAS VA base** | Everything compared below unless marked otherwise |
| **SAS Visual Statistics** | Decision-tree variable importance and assessment plots, custom model building, model comparison |
| **SAS Visual Forecasting** | Large-scale and hierarchical forecasting |
| **SAS Model Studio / Model Manager** | ML pipelines, model governance, scoring without score code |
| **Esri Premium** | Drive-time areas, demographics, advanced routing — *charged per use* |
| **Separate products** | SAS Studio (jobs), SAS Graph Builder (custom graph templates) |

### How to read the states

Four states, not a tick — the middle two are where the truth lives.

**✅ have** · **🟡 backend only** (works, no UI reaches it) · **🔶 partial** (real
but narrower than SAS) · **❌ no**

---

> **On this document's own reliability.** It has been corrected **fifteen
> times**. Fourteen went the same way — a capability marked ❌ or 🔶 that was
> already built — caught by re-reading the code or by driving the running
> product.
>
> The fifteenth went the other way, and is the more useful one. "Cross-filtering
> between objects ✅" was true of every chart and **false of all nine map
> widgets**: `onClickPoint` sat in their props and not one of them ever called
> it, so clicking a country did nothing while the bar chart beside it filtered
> the page. A ✅ that is true in general and false for a whole family is harder
> to catch than a ❌, because nothing about it looks wrong.
>
> The lesson is not that the comparison was careless. It is that **this codebase
> is consistently better than its own description**, and that the cheapest way to
> gain a cell here has repeatedly been to *check* rather than to build. Any
> remaining ❌ deserves the same treatment before it is used to justify work.

## 1. Data preparation

| Capability | SAS VA | Datalytics |
|---|---|---|
| Import files (CSV / Excel / SAS datasets) | ✅ | ✅ |
| Live connection to a database | ✅ CAS libraries | ✅ + DirectQuery mode |
| Calculated columns from an expression | ✅ Expression Editor | ✅ formula language + custom functions |
| **Aggregated measures** (expression over aggregates, with By-Group / For-All scope) | ✅ | ✅ `TOTAL()` = ForAll, `BYGROUP(expr,'col')` = named grain, `CALC(expr,"filter")` = filter context |
| Quick one-click calculations | ✅ | ✅ on widgets (percent of total, difference, percent change, rank) **and from the field list** — % of total, average, median, standard deviation, distinct count for a measure; distinct count and % of rows for a category. Each saves a MEASURE, so it evaluates at every widget's own grain rather than being frozen at definition time, and every generated expression is executed against the real engine by a test |
| Custom categories (bucket values into named groups) | ✅ intervals *and* distinct values | ✅ **Group & Bin** builder on the dataset — intervals *and* distinct values |
| Hierarchies, auto date hierarchies | ✅ | ✅ |
| Joins between sources | ✅ (course 2) | ✅ prep step + materialise |
| **Saved data views** (reusable, shareable, publishable, admin default) | ✅ | ✅ org-wide by construction (every view is visible to the whole organisation), and an admin can mark ONE as the **default applied to every dataset uploaded from then on** — match-by-name, skip-with-report, and it can never fail an upload: a view built on other columns lands what fits |
| **In-place source-table editing** (edit cells, bulk replace, trim, case, insert/delete rows) | ✅ | ✅ **cell editing in the Data grid**, plus find-and-replace, trim and case as prep steps. Deliberately different underneath: a typed correction becomes an `edit_cells` PREP STEP addressed by a key column's value, so the uploaded file is never rewritten, the correction is visible in the pipeline, removing it restores the original, and it survives a re-upload — none of which is true of SAS's row write. The cost is that a row with no usable key cannot be corrected this way, and inserting/deleting rows is not offered |
| Automatic outlier / related-measure / insight detection in the field list | ✅ | ✅ **inline on the field itself** — an ≈ marker carrying the correlations ("moves with target r=0.74, cost r=0.66") and an outlier count that opens the offending rows |
| **Data pane usability** (filter the items, distinct-value counts) | ✅ *"Country - 47", "Order ID - 748K"* | ✅ a filter box over the field list, and the distinct-value count beside every category — `analyze_categorical` had computed it as `n_unique` since the beginning and nothing showed it |
| **Aggregations offered on a data item** | ✅ *18, through to skewness, kurtosis and a one-sample t test* | ✅ **24** — the common twelve plus standard error, coefficient of variation, skewness, kurtosis, both sums of squares, the t statistic and its p-value. Each returns NOTHING where the group cannot support it (skewness of two points, a t statistic of one) rather than an artefact of the formula, and a test runs every aggregation the panel offers through the real engine — `_agg_series` falls back to SUM for a name it does not know, so an unimplemented one would return a plausible number and never raise |
| **Classify a data item as geography** | ✅ Category / Geography | ✅ a column is classified once, with its boundary set, and every map built from it inherits the shapes — rather than choosing the same set on each of six maps |
| **Page templates** (save a layout, reuse it) | ✅ with thumbnails, admin-curated | ✅ built-ins plus your own, named on save and deletable; **no thumbnail image and no admin curation** |

SAS's data layer is the more mature half of this comparison. Both of the items
that once stood out here — ~~custom categories~~ and ~~the source-table
editor~~ — are now built. The editor is the more interesting of the two,
because it is the one place this platform deliberately does NOT copy SAS: the
correction is a pipeline step rather than a write to the table, which keeps the
source reproducible and the change reviewable. That is a better answer for
governed data and a worse one for a row with no key, and both halves are said
out loud in the cell above.

**Correction.** An earlier draft of this document called the scoped aggregated
measure "the deepest gap" here. It is not a gap at all —
`backend/app/services/measure_eval.py` evaluates every measure at the requesting
widget's grain, and carries three context functions: `TOTAL(expr)` is SAS's
ForAll, `BYGROUP(expr,'col')` is a *named* grain override, and
`CALC(expr,"filter")` overrides the filter context. A crosstab re-evaluates one
measure at four grains in a single render. `SUM(sales) / TOTAL(SUM(sales))` is
the placeholder text in our own Measures panel.

What SAS still has that we do not is narrower: a **per-intersection scoped
expression** — one measure carrying a base expression plus overrides selected by
which data roles intersect. Power BI approximates it with `ISINSCOPE`; we have no
equivalent.

---

## 2. Objects and charts

| | SAS VA | Datalytics |
|---|---|---|
| Chart types | ~50 objects | **67 types**, 53 server-side shapers |
| Tables, crosstabs, cell visualisations, totals/subtotals | ✅ | ✅ |
| Bars, lines, time series, dual-axis, part-to-whole, distribution | ✅ | ✅ |
| Relationship: bubble, scatter, heat map, correlation matrix, parallel coordinates | ✅ | ✅ |
| Sankey / path, network with centrality metrics | ✅ | ✅ sankey, and a network carrying **degree, closeness, Brandes betweenness and reach** per node, plus communities and predicted links — any of the four can size the nodes |
| Containers (prompt, stacking, scrolling, **precision/overlap**) | ✅ | ✅ five modes — group, tabs, scrolling, collapsible and **precision**: free positioning over a background image, widgets may overlap, per-widget layer decides what sits in front |
| Object templates (save a styled object for reuse) | ✅ with or without data, publishable | ✅ widget templates |
| **Page templates** (start a page from a layout) | ✅ | ✅ built-in layouts (KPI overview, chart + detail, four-panel comparison, map + detail) and **your own**: any page — or a container subtree — saved and instantiated into any report. Widgets are stored with INDEX-based container references rather than ids, which is what keeps a templated container attached to its children wherever it lands. Data roles are deliberately left unbound: a template's value is the layout and the wiring, and guessed column names are wrong in the next report |
| **Duplicate Object** | ✅ | ✅ from the object's own menu — the whole config comes with it (roles, formatting, rules, filters, ranks, sorting) and the copy lands below the original, not on top of it. Distinct from a template, which is for reuse across DIFFERENT reports |
| **Chart appearance details** (axis titles per axis, legend titles, totals in a donut, display units) | ✅ | ✅ **left and right axis titled separately** on every dual-axis type; a **legend title** naming the field its entries belong to; a donut's **total in the hole** with its own caption; and **display units** (K/M/B, or a bare number under an axis titled "(millions)") wherever a number is formatted |
| **Objects over a page background** | ✅ | ✅ a page carries a background image and any object can drop its panel and border to sit on it |
| Custom visuals via an embedded page | ✅ | ✅ `custom_visual`, **two-way** — data posted in, selections posted back and applied through the same gate a chart click uses |
| **Circle packing plot** (nested circles for a hierarchy) | ✅ | ✅ a **sixth layout over the one hierarchy shaper** — the same numbers tree, sunburst, icicle, dendrogram and org chart draw, so the pictures differ and the totals cannot. Radius scales with √value, never value, and it joins the partition family that **refuses non-additive aggregations**: area is the encoding, so an average would draw children that visibly fail to fill their parent. Sibling areas are exact; across branches they are not, because children are scaled to fit — the same trade d3's pack makes, and each circle carries its real number |
| Custom graph templates (build a new chart type) | ✅ SAS Graph Builder | ✅ **Custom Graph** — the author decides what the combination IS: how many plot layers, which mark each draws (bar, line, area, points), which aggregation, which axis. The catalogue already had three FIXED combinations; this is the one where the shape is the author's. Saving it as an object template — which already existed — is what makes the result a reusable graph rather than one chart. Layers are keyed by POSITION, so the same column read two ways (total and average) is two series rather than one, and a layer whose column has gone is **named** instead of quietly missing. Not a separate application, which is the part of SAS's version left behind |
| Run server code and show its output in a tile | ✅ Job content object | ✅ **`script` tile** — Python over the widget's own secured frame (`df` in, `result` out), drawn as a table with `print()` output beneath it. Run in a **subprocess with a scrubbed environment** so the code never sees the server's credentials, with a timeout and a row cap. It is **not a sandbox** — the code runs as the server user — so **only an org admin may create or change one**; everyone else runs what an admin wrote, the trust model of a saved SQL view |

**This section is close to a wash and not where the interesting difference
lies.** Both catalogues cover the same ground, and with Custom Graph the
last structural difference — building a new chart TYPE rather than a new chart
— is closed too. What SAS still has is the separate authoring application;
what it buys over composing layers in the panel is not obvious.

---

## 3. Interactivity

| Capability | SAS VA | Datalytics |
|---|---|---|
| Cross-filtering between objects | ✅ | ✅ **including maps** — clicking a region, marker, flow line, map pie or map network node filters the page, by the value the DATA carries rather than the geometry's own name. Cluster and density maps deliberately do NOT: they return a point COUNT per grid cell, so there is no value behind a cluster to filter by |
| **A permanent strip naming what is filtering the page** | ✅ | ✅ on the builder, on a shared link and inside an embed. It renders even when nothing is filtering, saying "No selections" — returning nothing looked identical to a page that cannot be filtered at all, and after clicking a chart there was no fixed place to look. Each chip carries a NAMED remove button, so a filter can be cleared without hunting for the widget that set it |
| **Automatic page-level actions** (linked selection / one-way / two-way, no wiring) | ✅ | ✅ all four modes, set per page; `manual` is our default, automatic is SAS's. *Corrected: this was true in the BUILDER only — see §9* |
| Manual per-pair actions | ✅ | ✅ per-pair `actions` with filter/highlight |
| **Interaction settings survive a reload** | ✅ | ✅ *as of this week — they did not before; see §9* |
| Filters: basic, advanced, post-aggregate | ✅ | ✅ incl. HAVING-style post-aggregate |
| **Common filters** (one filter, shared across the whole report, edit once) | ✅ | ✅ `common_filters`, applied report-wide |
| Ranks (top/bottom N, with "All Other") | ✅ | ✅ |
| Multi-column and custom sort | ✅ | ✅ |
| Report / page prompts, cascading auto controls | ✅ | ✅ |
| **A control for a column a list cannot serve** | ✅ text input | ✅ `slicer_mode: text` — the reader types the value they already know. The point is not a smaller widget: the server returns **no values at all** for this mode, because on a column like Customer ID with hundreds of thousands of distinct values, building the list is the cost. An empty box clears the filter rather than filtering on `""`. `auto` never chooses it — a reader who can see their options should be given them |
| **Reach any object's settings without finding it on the canvas** | ✅ object selector on every pane | ✅ an object picker above the properties panel, listing every object on the page and the page itself. A widget inside a container, a small one, or one under another in a precision layout can be genuinely hard to click |
| Parameters (character, numeric, date, expression) | ✅ | ✅ |
| Display rules driving colour and icons | ✅ incl. map icons | ✅ |
| Drill-through, links between pages/reports, external URLs | ✅ | ✅ |
| Bookmarks | ✅ | ✅ bookmarks pane with capture/restore |

SAS's **automatic actions** are genuinely nicer than our default. Turning on
"one-way filter" for a page wires every object to every other object with no
per-pair configuration, and the viewer chooses the order by clicking. We ask the
author to define the pairs — which the dashboard suggester now does
automatically for charts that share a dimension, but only at creation time.

**Common filters exist on both sides** and even share the name — a
`common_filters` table here, applied report-wide. This row was initially written
as a gap and corrected on checking; it is a reminder that the fastest way to be
wrong about your own product is to answer from memory.

---

## 4. Statistics and AI

This is where the platforms diverge most, and not in the direction the object
catalogue suggests.

### Statistical analysis

| | SAS VA base | Datalytics |
|---|---|---|
| Forecasting (auto model selection) | ✅ ARIMA + 6 exponential-smoothing models | ✅ AutoETS + simple, `forecast_ets` / `forecast_simple` |
| **Forecast goal-seeking** ("when will this reach X?") | ✅ | ✅ **`forecast_goal`** — the period the projection crosses a target, with the soonest and latest its confidence interval allows, and the period it first got there when history already passed it |
| Underlying factors improving a forecast (scenario what-if) | ✅ | ✅ **`forecast_scenario`** — fits the measure on time plus the factors you name, then projects again with them moved. Each factor carries its own p-value, and a scenario leaving the observed range is named an extrapolation |
| Decision tree | ✅ *Visual Statistics* | ✅ **`decision_tree`** — shallow and readable, scored on rows it never saw, with the training score beside it so the gap is visible; categorical splits read as membership ("product is not X"), and columns it could not use are named |
| Text topics + sentiment (30+ languages) | ✅ | 🔶 **topics ✅** (`text_topics` — NMF over TF-IDF, with the comments behind each cluster); **sentiment ❌** and **English stop words only**. Other languages produce topics but their everyday words dominate unless a stop list is supplied |
| Clustering / segmentation | *Visual Statistics* | ✅ `segment` (KMeans, auto-k) |
| Anomaly detection | 🔶 outlier flags in the Data pane | ✅ `anomaly_iqr`, `anomaly_iforest`, `anomaly_ecod` |
| Association rules | ❌ | ✅ `association_rules` |
| Key influencers | 🔶 automated explanation ranks factors | ✅ `key_influencers` |
| **Hypothesis testing** (t-test / ANOVA / chi-square) | — not in either course | ✅ `compare_groups`, `test_independence`, `pairwise_comparisons` |
| **Regression** (linear, logistic, mixed models) | — not in either course | ✅ `regression`, `glm_logistic`, `mixed_model` |
| **Survival analysis** | — not in either course | ✅ `survival` |
| Correlation testing | 🔶 correlation matrix, Pearson only | ✅ `correlation_test` |

**19 analyses in the catalogue, 13 runnable through one dispatch route**
(verified live against `GET /analysis/registry` and
`POST /datasets/{id}/analysis/run`), with 68 passing tests behind the
inferential ones alone. Thirteen because the six forecast and anomaly entries
describe widget configuration rather than dispatcher parameters; they run as
widgets, and the catalogue reports them honestly as not generically runnable
rather than offering a button that 400s.

This is the counter-intuitive result of the whole comparison, and it needs
stating carefully. **The words "t-test", "ANOVA" and "analysis of variance" do
not appear once in either course** — 3,150 lines covering the base product end to
end. Every time the courses reach the edge of the automatic objects they route
the reader elsewhere: *"For more control over the model selection process, you
can instead use SAS Visual Statistics"*, *"create a model (if your site has
Visual Statistics available)"*.

That is evidence of what the courses teach, not proof of what the product
contains. Read at its strongest it says: **classical inferential statistics is
not part of the SAS Visual Analytics story, and it is part of ours.** What SAS VA
base offers instead is a small set of *automatic* analyses needing no
statistical knowledge at all — a different and entirely defensible choice, and
arguably the better one for its audience.

### AI

Both platforms have AI. They are not the same AI, and neither subsumes the
other.

| | SAS VA | Datalytics |
|---|---|---|
| Drag fields → best chart chosen automatically | ✅ automatic chart | ✅ **one field or several** — ctrl-click to gather fields, drag, and one chart is built from all of them: category + measure → bar, date + measure → line, two measures → numeric plot, two categories → crosstab, two categories + measure → heatmap, category + two measures → dual-axis, date + category + measure → a bar over time split by the category. A date always wins the axis, the drop ORDER never changes the answer, and any field the rule could not place is named rather than silently dropped |
| A pane that proposes charts | ✅ Suggest pane | ✅ Suggest tab + dataset-level suggestions |
| **Automated explanation** — ranks what drives a variable, in prose and plots | ✅ | ✅ `services/explain.py` — ranks factors on one 0–1 scale (\|r\| for numeric, √η² for categorical), `relative = score/top_score` as SAS does, **plus a relationship plot**, and now **a generated sentence** through the same guarded path the pin cards use: the digit guard discards any line stating a number the evidence does not contain, and the sentence is labelled as generated. It is an ADDITION to the answer — with no model reachable the factors still return, which is the normal case in an air-gapped install rather than the edge. A second ranking exists in `key_influencers` |
| **Automated prediction** — runs several models, picks a champion | ✅ | ✅ **`automated_prediction`** — tree, forest and a linear/logistic model on ONE shared split, plus a "just guess" baseline that decides whether the winner earned its name |
| **Keeping the champion, and scoring new rows with it** | ✅ | ✅ *as of this week* — `prediction_models` stores the winner refit on the whole frame, and scoring answers rows whose outcome is not yet known. Two things it does that are easy to get wrong: the **training column order travels with the model**, so a frame missing a category is reindexed rather than silently shifting every feature after it; and a value the model never saw is **reported**, because it encodes as "none of the above" and would otherwise come back as a confident-looking answer. A saved model also carries the influence of every column it was trained on, so a reader **denied one of them is refused the model entirely** — dropping the column at score time would change nothing |
| **Ask a question in natural language, get SQL and a chart** | ❌ — SAS's "natural language" is a GENERATED EXPLANATION of a result (path analysis, text topics); there is nowhere to type a question | ✅ NL→SQL agent with an explicit graph. Hardened against live traffic this week, and every item here was a defect found by tracing real turns rather than by reading the code: a message that asks nothing about the data (“hi”, “thanks”) is answered without querying; “what IS this data” is answered from the CATALOG — every table in scope and what each holds — with the query beside it, not instead of it; a request the data cannot settle is **asked back with clickable options built from real column names** (“Chart symbol_code by id”), never guessed; and a request to CREATE something is refused with where to do it rather than narrated as done |
| **Describe your job, get whole dashboards built for it** | ❌ | ✅ persona-driven, every widget executed before it is offered |
| **A statistics-only path with no model involved** | ✅ (all of SAS's is statistical) | ✅ empty goal → insights engine, ~4s, deterministic |
| Chat assistant that edits the dashboard | ❌ | ✅ page copilot |

SAS's AI is **statistical and automatic**: it computes what matters and shows
it, reproducibly, with no model in the loop. Ours is **language-driven**: it
takes a sentence about who you are and builds for that.

The one piece of SAS's that has no equivalent here is **automated prediction** —
running logistic regression, gradient boosting and a decision tree, picking a
champion on accuracy, then handing the user a live input form. We fit
`regression`, `glm_logistic`, `mixed_model` and `survival` and return their
coefficients, but **no fitted model is ever persisted**: every endpoint refits
from the frame and discards the fit. A champion-and-score path needs model
persistence first, which we do not have.

A caveat about our own side — and it is now a smaller one than when this was
written. At the time, `explain_response` and `goal_seek` were not in the
analysis registry at all, so they were invisible to the registry endpoint, to
the generic statistics panel and to the agent: capability we could not find is
capability a user did not have.

Both are registered now, the registry dispatches by name, one screen runs
everything the catalogue calls runnable, and the assistant invokes analyses
instead of only describing them.

The vocabulary problem this paragraph used to end on — *"explain" means four
different things in this codebase* — turned out to be a defect, not a tidiness
complaint, and was found by driving the product. Asked to **"explain this
chart"** about rows already on screen, the agent reached the `explain` INTENT,
which means the SAS-shaped key-influencers analysis, and answered *"the
response needs at least two distinct numeric values"* — about a column nobody
had named. The four meanings are still four, but they no longer collide: a
message about a result that already exists is resolved to a `describe` kind
before classification, and answered as prose about those rows. Worth recording
because it is the same lesson as the rest of this document, pointing the other
way: **a naming muddle the code review noticed and filed as cosmetic was
mispronouncing itself to users the whole time.**

---

## 5. Geography

| | SAS VA | Datalytics |
|---|---|---|
| Map objects | ✅ 10 geo types | ✅ 9 map types |
| Base map tiles | ✅ OpenStreetMap + Esri ArcGIS Online | 🔶 built-in world geometry, no tile service. **Deferred deliberately, not overlooked** — the customer runs their own tile server, so this is a *configurable tile URL* pointed at an internal host, not a public CDN. That matters: the offline-CDN guard in this codebase exists precisely to stop the maps depending on a third party, and an internal server does not breach it. Waiting on that server being reachable, because a tile layer verified only against a mock is a tile layer that has never drawn a tile |
| Coordinate, bubble, cluster, density, region, network, line, pie maps | ✅ | ✅ |
| **Region maps below country level** (states, provinces, ZIP codes) | ✅ predefined roles for countries, subdivisions, US states, US ZIPs | 🔶 **bring your own boundary file** — nothing sub-national is bundled, because admin-1 for every country is tens of megabytes |
| **A geography ROLE on the column, not the widget** | ✅ | ✅ classify a column once and every map drawn from it uses those boundaries — on the builder, a shared link and an embed, since the classification is published as a derived field rather than left in the dataset the reader never sees. Dropping a classified column onto the canvas makes a **map** rather than a bar of counts, which is what the role is for. A widget may still override it, and the panel says when it is inheriting instead of showing an empty picker beside governorates. Deleting a boundary set clears the classifications that pointed at it |
| Custom boundaries from a geographic data provider | ✅ Esri feature service or CAS table | ✅ *upload GeoJSON/TopoJSON; matching keys detected from the file* |
| Pins, radius selection, routes | ✅ | 🔶 **radius selection ✅** — shift-drag a circle on a point or bubble map and everything inside becomes one multi-value filter, which is the one selection a map can make that no other chart can. **Pins ✅** — author-placed annotations on the coordinate maps, stored on the widget so they travel to a shared link and an embed. A pin is deliberately **not data**: it never broadcasts a filter and the lasso cannot catch it, because filtering the page to a label no row holds would answer every other widget with "no rows" and explain nothing. The editor warns which pins will not be drawn, since the renderer must drop a non-finite coordinate. **Routes ❌** (Esri, out of scope) |
| Drive-time / walk-time areas, demographics | ✅ *Esri Premium, charged* | ❌ |
| Custom icons on map markers via display rules | ✅ | ✅ *interval bands carry an icon; point and bubble maps draw it* |
| **Maps frame the data they draw** | ✅ | ✅ *as of this week — every map used to fit the whole world; see §9* |
| **Country columns keyed by ISO code** | ✅ | ✅ *name, ISO alpha-2, or ISO numeric* |

Geography is SAS's clearest structural lead, and the sub-national gap is the one
that bites in practice: a dataset keyed by Egyptian governorates, US states or
UK counties cannot be drawn as a region map here. It was found the hard way —
a hospital dashboard whose choropleth of 27 governorates matched nothing and
drew a blank world map.

Most of that gap is now a **supply** problem rather than a capability one. A
map widget can be pointed at an uploaded boundary set — GeoJSON or TopoJSON,
converted in the browser, validated and stored per org — and a choropleth then
draws those shapes *instead of* the world, framed on them. The naming property
is detected from the file rather than configured, so `name`, `NAME_1`,
`shapeName` and `ADM1_EN` all work, and a file carrying both `name` and
`name_ar` matches data in either language.

What is still missing is the geometry itself. Admin-1 boundaries for every
country are tens of megabytes, so none ship with the app: **real Egyptian
governorate polygons are something the customer supplies.** That is why the row
above is 🔶 and not ✅. SAS's advantage here is now the Esri relationship — a
provider with the data already loaded — not the software.

One narrower version of that has since been closed. A `country_code` column
matched nothing at all: the bundled atlas carries the ISO 3166-1 numeric code
as each feature's `id` on 236 of its 241 geometries, and the matcher read only
`properties.name`. It now matches a name, an ISO alpha-2 code or the numeric
code. Alpha-2 is DERIVED at load from the runtime's own locale data rather than
from a hand-typed table — a mistyped row would paint real data onto the wrong
country, which is exactly what the matcher's never-fuzzy rule exists to
prevent. Alpha-3 is still unmatched, for the same reason: nothing available
offline maps it, and inventing the table is the risk just described.

---

## 6. Sharing, distribution and delivery

| | SAS VA | Datalytics |
|---|---|---|
| Share a link, view-only access | ✅ | ✅ |
| Export PDF (report / page / object) | ✅ with page setup, TOC, appendix | ✅ |
| Export data (Excel / CSV / TSV), structure preserved | ✅ | ✅ CSV / Excel |
| Export an object as an image | ✅ | ✅ `lib/widgetImage.ts`, per widget |
| **Offline report package** (snapshot of data + queries, hostable) | ✅ | ❌ |
| Scheduled distribution by email | ✅ recurring, PDF attached | ✅ subscriptions + delivery |
| Post to a chat channel | ✅ Microsoft Teams | ✅ an https webhook counts as a recipient — Teams and Slack both take `{"text": …}` |
| **Alerts on a condition** | ✅ on a display rule | ✅ `AlertsPanel` on the dataset, over an evaluator that has been running all along — rising-edge firing (one email per crossing, not one per tick) and the creator's own RLS. *Corrected: this said "running, but unreachable"* |
| Embed in another app | ✅ SDK | ✅ embed router + share tokens |
| Mobile app / PWA / Microsoft 365 add-in | ✅ all three | ❌ responsive web only |
| Report localisation (translate report text per locale) | ✅ | ✅ translations pane |

Alerts are the honest black mark on our side, and a stranger one than "not
built". The backend is complete **and already running**: `refresh_scheduler.py`
calls `check_alert` on every tick, the condition is validated by the same sandbox
widgets use, row-level security resolves as the alert's creator, and firing is
rising-edge so a true condition emails once rather than every tick. Three
endpoints exist. **Nothing in the frontend calls them.**

So this is not a feature that was never built — it is one that runs in
production and that no user can reach. A different kind of failure, and a
cheaper one to fix.

One design difference worth noting: SAS's alerts watch a **display rule on a
report object**; ours watch a **data condition** on the dataset
(`SUM(revenue) < 100000`). Ours is arguably the better place for it.

---

## 7. Governance and security

| | SAS VA | Datalytics |
|---|---|---|
| Row-level security | ✅ CAS-enforced | ✅ rules on datasets and on sources |
| Column-level security | 🔶 hide data items — *the course says the Hidden role "is not intended for column-level security purposes"* | ✅ real column rules, pinned by tests at 7 endpoints |
| Roles and capabilities | ✅ viewer capabilities per report | ✅ org-scoped roles, per-dataset capabilities |
| Audit log | ✅ Environment Manager | ✅ |
| Version history / restore | 🔶 autosave and save-conflict resolution | ✅ report snapshots with restore |
| Data lineage | ❌ | ✅ |
| Multi-user save-conflict handling | ✅ overwrite / Save As / autosave recovery | ✅ revision counter with a stale-write warning |
| **Report review pane** (performance + accessibility audit with severities) | ✅ | ✅ review pane |
| **Review of the interaction graph itself** | ❌ | ✅ the review walks the wiring a reader depends on and names every edge that can never fire: an action on a widget **set not to receive**; per-pair actions on a page whose **automatic mode ignores them** (the two are mutually exclusive, and the mode wins); a page where **nothing will react at all**; and, defensively, an action pointing at a **deleted** widget or one **across a page boundary** — neither of which the builder can now produce, but the API, the copilot and a restored snapshot can. None of these throws, logs or looks wrong in the builder: the author clicks the one path they wired, it works, and the rest is dead for every reader |

Column security is a genuine win here and worth stating precisely: SAS's guidance
is to *hide* data items, and the course explicitly warns that hiding is not a
security control. Ours removes denied columns from the frame before any shaper
sees them.

---

## 8. Platform

| | SAS VA | Datalytics |
|---|---|---|
| Engine | CAS — distributed, multi-threaded, in-memory | pandas + DuckDB pushdown, Valkey cache |
| Scale | Designed for very large data; per-object row thresholds (list table default 40,000) | Import-mode row cap; DirectQuery pushdown for large sources |
| Deployment | SAS Viya (licensed) | Self-hostable, containerised |
| Cost | Commercial licence, plus add-ons and Esri credits | — |

CAS is a different class of engine and the honest position is that we have not
tested at a scale where the comparison would be meaningful. What can be said is
that SAS's thresholds are real and visible in the product: a list table shows
40,000 rows by default and silently truncates beyond that, with a per-object
override.

---

## 9. What a course narration cannot tell you

Every capability above is written the way SAS's courses write theirs — as
something the product offers. Here is what that style of writing hides, taken
from this platform in the twenty-four hours before this document:

| Found | Would a feature list have shown it? |
|---|---|
| The Interactions panel saved **nothing** — direction, receive mode, per-pair actions all lost on reload | No. "Cross-filtering: ✅" was true the entire time |
| 16 widget types offered text columns to fields needing numbers; a text target is silently dropped, text coordinates return `rows: [], dropped: 120000` — all HTTP 200 | No |
| The canvas laid tiles out at a stale 900px, wasting several hundred pixels on a wide screen | No |
| A monthly chart drew December before January, because a time axis sorted by value | No |
| Five renderers drew a legend entry named `value2` — the internal data key, shown to users | No |
| Every map fitted itself to the whole world, whatever it plotted | No |
| A dashboard endpoint returned a data profile — including sample values — for datasets the user cannot open | No |
| Every interaction setting worked in the builder and **died on publication**: a shared link and an embed mounted the filter context with no widgets and no page mode, so a widget the author deliberately isolated broadcast anyway (the fallback is `broadcasts ?? true`), and a page authored as linked/one-way/two-way behaved as none of them | No. Both rows above read ✅, and both were true — of the one surface an author tests on. The reader of a shared link is the person the report exists for |
| Deleting a widget left every per-pair action aimed at it **dangling** — nothing pruned the edges, so each survived as a permanent no-op. Two more dead-edge shapes need no deletion at all: an action on a widget set not to receive, and per-pair actions on a page later switched to an automatic mode, which ignores them | No. Each is dropped by a different branch of one function and none of them errors. Deletion now prunes on the server, where the copilot and the API delete too; the review pane names the rest. It is in §7 because SAS's own review pane does not |

All are fixed and pinned by tests. They are listed because they are the reason
the caveat at the top of this document exists: **the SAS column has not been
through this, and its ticks should be read as generously or as sceptically as
you would read ours before it was.**

The last row is worth reading twice, because it is a different KIND of error
from the others. Nothing was missing: the modes were implemented, tested and
honoured at every gate. They were only ever wired on the surface an author
works on. A feature matrix cannot see that distinction — and neither can a
test suite that only renders the builder — which is why the verification rule
for this platform is to drive the surface a stranger actually receives.

---

## 10. Where this platform should go next

Ordered by what the comparison actually found, not by what sounds impressive.

Writing this list is what exposed the seven corrections above: four of the items
originally on it were **already built**. That reordered everything, because the
biggest single lever turned out not to be construction.

1. ~~**Make what exists reachable.**~~ **Shipped.** The registry dispatches by
   name (a lazily-resolved handler string, so the heavy ML imports stay off the
   app-import path); `explain_response` and `goal_seek` are registered, the
   second extracted out of a router function so anything can call it; one
   endpoint runs any catalogued analysis over the same row- and column-secured
   frame the widgets read; the panel is catalogue-driven and offers 13 analyses
   instead of 8; and the assistant routes "is that difference real?" to a t-test
   rather than a `GROUP BY`, falling back to SQL whenever it cannot serve the
   question. **SAS has no equivalent of an assistant that can invoke its whole
   analytic catalogue** — and it was built almost entirely from parts we already
   owned.
2. ~~**Give alerts a UI.**~~ **Shipped.** A pane on the dataset — list, create,
   delete — and the two security holes that had to close before pointing a UI
   at those endpoints: they gated on org membership rather than dataset read
   (datasets are per-user, and an alert emails its condition on a schedule), and
   `delete_alert` never checked that the alert belonged to the dataset in the
   path, so the path segment was decorative. It says out loud that it fires on
   the RISING edge, because a condition that is already true sends nothing and
   silence reads as a broken feature.
3. **Sub-national geography.** ~~Region maps at state / province / district
   level.~~ **Half shipped.** The mechanism exists: boundary sets are stored per
   org, a choropleth can be pointed at one, and the matcher generalised from
   countries to any region set without countries becoming a special case. What
   is NOT shipped is bundled admin-1 geometry — tens of megabytes per country —
   so a customer supplies the file. The deeper half of the original plan, a
   column-level geography role replacing the five unconnected heuristics, is
   deliberately deferred: the widget-level pick is what closes the matrix cell,
   and the role touches three closed vocabularies and two `column_meta`
   whitelists.
4. ~~**Custom categories**~~ — **the builder already existed.** `Group & Bin`
   has been mounted on the dataset's Data tab all along, compiling to an
   ordinary calculated column (`SWITCH` for named groups, nested `IF` for
   intervals). This entry was the EIGHTH cell in this document to understate
   what ships.
   Its numeric half, however, had never worked: bin edges were read from
   `DatasetColumn.stats`, a declared field **nothing in the application ever
   writes** — `stats={}` is passed literally at all three creation sites, and 0
   of 506 columns in the dev database carry any. Min and max both fell back to
   0, so every attempt answered "Pick at least two bin edges". The panel's own
   tests passed because their fixture supplied a `stats` object the application
   never produces. The range is now fetched through the widget path, so
   row-level and column security apply to it like any other number.
5. ~~**Wire goal-seek to the forecast.**~~ **Shipped, and only that half.**
   `forecast_goal` answers "when will this reach X?" along the projection:
   the expected period, the soonest and latest the band allows, and — the case
   the demo data is full of — the period history already reached it, rather than
   an unhelpful "not within the horizon". The answer is computed by the SHAPER,
   so the caption cannot disagree with the chart above it, and it is registered
   in the catalogue so the panel and the assistant get it for free.
   **Scenario analysis over underlying factors has since shipped too**, as a
   genuinely different model rather than an extension of the first: AutoETS
   accepts no exogenous regressors, so `forecast_scenario` fits
   `measure ~ time + factors` by OLS and projects again with the factors moved.
   It asks for the adjustment directly instead of forecasting each factor,
   because that would hide a second forecast nobody asked for inside the
   answer. Every factor carries its own p-value, and a scenario that leaves the
   observed range is named an extrapolation rather than answered with a
   confident number.

**Two smaller ones shipped alongside.** `CALC()` — filter-context measures, the
one the capability audit called the modelling gap — was implemented, tested and
callable, and appeared nowhere in the frontend palette; it is one entry now.
And display-rule icons reach map markers: the rule engine has emitted a band
icon per row for months and the point map read neither it nor the rule colour,
so "flag the sites that missed target" worked on every chart type except the one
where location is the point.

**One item is smaller on paper than in practice.** A multi-field drop ("SAS
handles a multi-field drop; extend to 2-3 fields") is not the cheap cell it
looks like: HTML5 drag carries one item, so it needs a multi-select model in the
field list before any of the charting rules matter. The rule for *assigning* a
field to an existing widget already exists and already fills the next empty
role; what is missing is the gesture, not the logic.

6. ~~**Two-way custom visuals**~~ **Shipped.** An embedded page posts
   `{type:"datalytics:select", value}` back and the report applies it through the
   same gate a chart click uses. The frame is sandboxed to an opaque origin, so
   the sender is identified by window IDENTITY rather than origin; and the page
   sends a value while the report supplies the column, so a custom visual has
   exactly the power of a click and no more. Contract documented in the README.
7. **Expose `CALC()`** in the measures palette — implemented, tested, and absent
   from the UI.
8. Precision container, decision tree, text topics — all three are now built;
   what is left of that line is sentiment and non-English stop words.

---

## Summary

| Area | Verdict |
|---|---|
| Data preparation | **Level** — what is left is row insert/delete (*scoped measures, custom categories, cell editing and an admin-default data view: we have all four; cell editing is a prep step rather than a row write*) |
| Objects and charts | **Level** — 67 types vs ~50, same ground covered; what SAS still has is Graph Builder (building a new chart TYPE) |
| Interactivity | **Level** — we have all four automatic page modes; only the default differs |
| Statistical analysis | **Datalytics ahead** — classical inference (hypothesis tests, regression, survival) is absent from both SAS courses |
| Automatic / assisted analysis | **Level** — `automated_prediction` fits several candidates on one split and names the champion *with the dumb baseline beside it*; explain, goal-seek and scenario what-if are all in the catalogue now, reachable from the panel and the assistant. SAS still scores new rows against a saved model; nothing here persists one |
| Language-driven AI | **Datalytics ahead** — NL→SQL, persona-driven dashboard generation, page copilot |
| Geography | **SAS well ahead** — sub-national regions, tiles, routing, Esri |
| Sharing and delivery | **SAS ahead** — offline packages, mobile, M365 (*chat channels and image export: we have them*) |
| Governance and security | **Datalytics ahead** — real column security, lineage, version history |
| Engine and scale | **SAS ahead**, and untested on our side |

The short version: **what SAS still has to itself is maps and delivery** —
sub-national geography beyond an uploaded boundary set, Esri routing and
demographics, offline packages, and native mobile. This platform is stronger
where the work is *statistics*, *asking questions in words*, and *governance*.
Data preparation, which this document called SAS's clearest lead for most of its
life, is now level. Which side matters more depends entirely on who is doing the
asking.
