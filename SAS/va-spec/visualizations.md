# Visualization Inventory

> Part of the Visual Analytics reverse-engineering deliverable. Sibling files: `application-map.md`, `screens.md`, `activities.md`, `components.md`, `visualizations.md`, `data-model.md`, `interaction-model.md`, `design-system.md`, `implementation-spec.md`, `screenshots/`.
> **Evidence labels:** OBSERVED (seen in the running app) · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.

## G. Visualization Inventory

### G.1 Full role catalogue (78 objects; `*` = required)

**Tables**

| Object | Required | Optional |
|---|---|---|
| Crosstab | Measures* | Columns, Rows |
| List table | *(none — the only object with no required role)* | Columns, Hidden |

**Graphs (30)**

| Object | Required | Optional |
|---|---|---|
| Bar chart | Category*, Measure* | Group, Lattice columns, Lattice rows, Data tip values, Animation, Hidden |
| Box plot | Measures* | Category, Lattice columns, Lattice rows |
| Bubble change plot | X start*, X end*, Y start*, Y end*, Size start*, Size end*, Group* | — |
| Bubble plot | X axis*, Y axis*, Size* | Group, Color, Lattice ×2, Data tip values, Animation, Hidden |
| Butterfly chart | Category*, Measure (bar)*, Measure (bar 2)* | Data tip values, Hidden |
| Comparative time series | Time axis*, Measure (TS1)*, Measure (TS2)* | Data tip values, Hidden |
| Correlation matrix | Measures* | option: within one set (default) / between two sets |
| Dot plot | Category*, Measure* | Lattice ×2, Data tip values, Hidden |
| Dual axis bar | Category*, Measure (bar)*, Measure (bar 2)* | Lattice ×2, Data tip values, Animation, Hidden |
| Dual axis bar-line | Category*, Measure (bar)*, Measure (line)* | as above |
| Dual axis line | Category*, Measure (line)*, Measure (line 2)* | as above |
| Dual axis time series | Time axis*, Measure (line)*, Measure (line 2)* | Data tip values, Hidden |
| Gauge | Measure* | Target, Group, Data tip values, Hidden |
| Heat map | Axis Items*, Color* | — |
| Histogram | Measure*, Frequency* | — |
| Key value | Measure* | Lattice category, Data tip values, Hidden |
| Line chart | Category*, Measure* | Group, Lattice ×2, Data tip values, Animation, Hidden |
| Needle plot | X axis*, Y axis* | Group, Lattice ×2, Data tip values, Hidden |
| Numeric series plot | X axis*, Y axis* | Group, Label, Lattice ×2, Data tip values, Hidden |
| Parallel coordinates | Variables* | — |
| Pie chart | Category*, Measure* | Group, Lattice ×2, Data tip values, Animation, Hidden |
| Scatter plot | Measures* | Color, Lattice ×2, Data tip values, Data labels, Hidden |
| Schedule chart | Task*, Start*, Finish* | Group, Label, Lattice ×2, Data tip values, Hidden |
| Step plot | X axis*, Y axis* | Group, Label, Lattice ×2, Data tip values, Hidden |
| Targeted bar | Category*, Measure*, Target* | Lattice ×2, Data tip values, Animation, Hidden |
| Time series plot | Time axis*, Measure* | Group, Data tip values, Hidden |
| Treemap | Tile*, Size* | Color, Data tip values, Hidden |
| Vector plot | X axis*, Y axis*, X Origin*, Y Origin* | Color, Group, Lattice ×2, Data tip values, Hidden |
| Waterfall | Category*, Measure* | Lattice ×2, Data tip values, Hidden |
| Word cloud | Word*, Size* | Color, Data tip values, Hidden |

**Geo maps (10)** — roles are grouped per map layer. The ten library entries are **Geo bubble · cluster · contour · coordinate · line · line-coordinate · network · pie · region · region-coordinate**, while the object’s own *Change type* dialog offers **seven** layer types — the two extra entries (`line-coordinate`, `region-coordinate`) are **composites**, so a geo object carries a **layer stack**, not a single layer (OBSERVED, session 15; refines §G.2g).

| Object | Required | Optional |
|---|---|---|
| Geo bubble | Geography*, Size* | Color, Data tip values, Data label, Hidden, Animation |
| Geo cluster | Geography* | Size, Color, tips, label, Hidden |
| Geo contour | Geography*, Color* | — |
| Geo coordinate | Geography* | Size, Color, tips, label, Hidden, Animation |
| Geo line | Geography* | Width, Color, Pattern, tips, label, Hidden, Animation |
| Geo line-coordinate | Line layer Geography*, Scatter layer Geography* | per-layer extras |
| Geo network | Source*, Target* | Size, Color, Link width, Link color, Label, tips |
| Geo pie | Geography*, Measure*, Category* | Size, tips, label, Hidden, Animation |
| Geo region | Geography*, Color* | tips, label, Data values, Hidden, Animation |
| Geo region-coordinate | Region layer Geography*+Color*, Scatter layer Geography* | per-layer extras |

**Controls (5)** — Button bar / Drop-down list / List: Category* (+ Measure, Hidden). Slider: Measure or Date* (single). Text input: Category* (+ Measure, Hidden).

**Analytics (6)** — Automated explanation (Response*, Underlying factors*, +Time); Automated prediction (Response*, Underlying factors*); Forecasting (Time axis*, Measure*, +Underlying factors); Network analysis (Source*, Target* + 6 optional); Path analysis (Event*, Sequence order*, Transaction identifier*, Weight*); Text topics (Document collection*, +Document details).

**Statistics (8)** — optional roles differ per object, so do not apply a blanket list:

| Object | Required | Optional |
|---|---|---|
| Cluster | Variables* | *(none)* |
| Decision tree | Response*, Predictors* | Partition ID, Frequency, Weight, Node details |
| Generalized additive model | Response*, Spline effects* | Continuous effects, Classification effects, Interaction effects, Partition ID, Frequency, Weight, Offset |
| Generalized linear model | Response* + at-least-one-of Continuous*/Classification*/Interaction* effects | Partition ID, Group by, Frequency, Weight, Offset |
| Linear regression | Response* + at-least-one-of the three effect roles* | Partition ID, Group by, Frequency, Weight |
| Logistic regression | Response* + at-least-one-of the three effect roles* | Partition ID, Group by, Frequency, Weight, Offset |
| Model comparison | *(refuses on insert without two comparable models)* | — |
| Nonparametric logistic regression | Response*, Spline effects* | Continuous, Classification, Interaction effects, Partition ID, Frequency, Weight, Offset |

**Machine Learning (6)** — all require **Response* + Predictors***; optional roles differ:

| Object | Optional |
|---|---|
| Bayesian network | Partition ID |
| Factorization machine | *(none)* |
| Forest | Partition ID, Frequency, Weight |
| Gradient boosting | Partition ID, Frequency, Weight |
| Neural network | Partition ID, Weight |
| Support vector machine | Partition ID |

**Containers (5)** and **static Content (Image, Job content, Web content)** — "Roles are not supported for the selected object." **Data-driven content:** Variables*, Parameters. **Text:** Measures, Parameters (both optional).

**Objects With Data (1)** — a saved, pre-built component ("customized loyality template" in the test environment): inserts a whole laid-out container with its own bound data source. **Caution observed:** inserting it silently removed the report's unused existing data source, and undoing it left the report with no data at all. A rebuild should never mutate other data bindings when inserting a saved component.

*Group totals: 2 + 30 + 10 + 5 + 6 + 5 + 5 + 8 + 6 + 1 = **78** visible objects. The Show/Hide Objects dialog counts 79; the extra one was never located in the tree.*

### G.2 Per-visualization detail (the ones exercised with real data)

**Bar chart** — geometry: rectangles from a fixed baseline; horizontal by default with Y reversed so the first category sits at the top. Axes: measure axis auto-scales and relabels ("Sales (millions)"); category axis thins labels via "Fitting steps: Drop some". Legend: only with Group; 9-point placement, default Bottom. Tooltip: one row per assigned role plus Data tip values. Data labels and segment labels off by default. Colour: single accent when ungrouped, categorical palette by Group. Sort: descending by measure when the measure is Frequency; **reverts to alphabetical if the sorted measure is removed**. Filtering: own filters + incoming links. Zoom/pan: none; an optional **Overview axis** adds a brushable mini-chart. Selection: click toggles a mark; double-click triggers page links. Aggregation: per measure. Cap: **3,000 rows** with ⓘ. Empty: "No data matches the current filters."

**Crosstab** — nested row and column headers; borders on; alternating row background; condensed rows; fit columns to width. Totals and Subtotals off by default, placed **Before** (above) their group when enabled, scoped Rows/Columns/Both, per measure. **All totals and subtotals are recomputed from source rows at their own level, never from displayed cells.** Verified for **Average on both axes** (row subtotals and nested column subtotals each matched an independently computed source-level average). A distinct-count **grand total** was verified separately on a single-level rows-only crosstab (213 true distinct cities, versus 218 if the per-region counts were summed); distinct count in *nested column* subtotals was **not** tested. Cell visualizations (bar or heat map, left/right/replace) **are not drawn on total rows**. Column-header menu: sort, replace, remove, explain, aggregation, format, create calculation, cell visualization, indent, hide totals, row numbers, abbreviate.

**Pie chart** — donut by default (ring width 30%, start 90°, counterclockwise), centre total label. **Automatically buckets small members into a grey "Other" slice below 4%**; setting 0% draws every member with repeating colours; 101 is silently rejected.

**Word cloud** — caps at **100 rows** with ⓘ.

**Time series plot** — binning interval Automatic / Fixed count / **Use format** ✓; optional logarithmic scale and overview axis; no period-over-period options on the object itself.

**Forecasting** — confidence interval 95%, horizon 6 periods, shaded band after a divider; horizon 0 and 9999 are silently rejected.

**Logistic regression** — runs when any one starred effect role is filled; auto-picks an event level (chose a 10.38% class, neither majority nor rarest); fit statistic default KS (Youden) from a list of ~20, each with an inline definition; panels: Fit Summary, Residual Plot, Odds Ratio Plot, Confusion Matrix; **discloses dropped rows** ("Observations: 646K of 2.3M").

**Slider control** — range (default) or single value; horizontal or vertical; snaps to integers; **excludes missing values even at full range** unless "Missing values option" is on; its bounds are silently clamped when a cross-filter narrows the data.

### G.2b Roles and options exercised in session 7 (OBSERVED)

**Lattice columns / rows** — a multi-item role (checkbox picker + Apply). Turns the object into a panel grid, one panel per value, sharing the category axis; panel headers truncate without a tooltip; the lattice item is auto-added to Data tip values. **Applying a lattice silently re-sorts the chart from value order to alphabetical.**

**Reference lines** — Options → Reference Lines → + New reference line creates one instantly with a computed default value. Settings: Label, Value, Axis (fixed to the measure axis), Line style (pattern, width 1–6, colour). **Value accepts only a typed constant or a parameter** — there is no mean/median/percentile option. Lines are drawn in every lattice panel.

**Parameters** — created from the Data pane or inline from any control that accepts one. The dialog is context-sensitive: created from a reference line it **locks Type to Numeric and disables "Multiple values"**; created from the Data pane it offers Character / Numeric / Date / Datetime. A control writes to a parameter through **Actions → Parameter Links** (a slider exposes *range start* and *range end* separately). Verified loop: slider → parameter → reference line, updating live.

**Containers** — Stacking renders its children as a tab strip with ‹ › arrows (the mechanism behind a "same chart, different measure" switcher). **Objects must be dragged in; double-click appends to the page instead.** Containers cannot be action sources ("Actions cannot be created from the selected object").

**Geography items** — the prerequisite for all 10 geo maps. The creation dialog previews a map with a **match rate ("86% mapped")** and names the failures ("1 of 1 unmapped values: England"); the rendered map repeats the warning in an ⓘ ("No matches were found for supplied geography data items: England."). Once created, the item appears in the Geography picker and the map renders.

**Multiple measures and axis ranges (OBSERVED)** — a second measure produces side-by-side panels, each independently scaled. **X Axis Range**: *Different per cell* (default) / *Same within each column* / *Same for all cells*. A shared scale across measures of different magnitudes makes the smaller series invisible without warning.

**Custom sort (OBSERVED)** — defined on the data item, but applied only when the object sorts **by that category**. Listed values come first in the defined order; unlisted values fall back to alphabetical. The object's sort menu gives no indication that a custom order exists.

**Insights (OBSERVED)** — the toolbar's "Insights were found" opens an **Outliers** advisor naming the measures that may be skewed, with an "Analyze Objects for Impact" action. It is a data-quality advisor, not narrative insight.

**View source table (OBSERVED)** — raw row-level viewer with column-type icons, a row/column count, and an explicit banner when the table exceeds the in-memory threshold: "Some features are not available due to the large size of the table."

**Automatic chart selection (OBSERVED, session 9)** — dropping items on the canvas resolves to a type by classification alone:

| Items | Result |
|---|---|
| 1 category (any cardinality) | Bar chart |
| 1 measure | Histogram |
| 1 date | Time series plot |
| 1 category + 1 measure | Bar chart |
| 2, 3 or 4 measures | Scatter plot — **read from the undo entry; see the caution below** |

Cardinality is **not** considered: a 748K-distinct identifier column produced a bar chart truncated at the row cap.

> **Caution on the multi-measure rows (added session 13).** The undo entry for a multi-measure drop names **Scatter** even when the object built is something else — verified three times (2 measures → *Heat map*, 3 measures → *Heat map*, 4 measures → *Correlation matrix*), each confirmed from the object's own name in the Data Roles pane. If the original reading of this row came from the undo label rather than the object, "Scatter plot" is wrong here too (INFERRED — confidence Medium; the original trial was not repeated). The verified multi-item drop behaviour is in §G.2e.

**The vendor guide's "four measures → correlation matrix" example does reproduce — on the drop path (OBSERVED, session 13).** Four measures dragged together onto an empty canvas build a **Correlation matrix**. The earlier "did not reproduce" note applied to the single-item automatic-chart path and was stated too broadly; see §G.2e and §P.3.

**Display rules as banded ranges (OBSERVED on a production report, session 6)** — beyond single-operator conditions, a rule set can be a series of value bands, each with its own colour, rendered as a **miniature gauge inside the cell**:

| Band | Colour | Placement |
|---|---|---|
| −600,000 ≤ x < 0 | red | "Right of text, with Profit as x" |
| 0 ≤ x < 400,000 | yellow | same |
| 400,000 ≤ x ≤ 900,000 | green | same |

In the viewer, the Display Rules pane doubles as the **legend** for these bands. A negative value renders red within the same left-anchored track rather than extending left of a zero baseline.

### G.2c Analytic and custom objects, read from production reports (OBSERVED, session 10)

Eight favorited reports were opened read-only in the viewer and every object's roles were read from the side pane. These are the first observations of the analytics group with real data.

| Object | Roles as configured | Notes |
|---|---|---|
| **Geo network** | Source `from_loc` · Target `to_loc` · Size `MaxWind` · Color `Category` | A network drawn **on a map**: nodes are geographic points, links follow the Source→Target pair. Carries the map's own viewport controls |
| **Network analysis** (hierarchy form) | **Levels** `Type - DriveTrain - Make` (a hierarchy) · Color `Origin` | The role catalogue lists Source*/Target* as required. A **second form takes a hierarchy in a single `Levels` role** and derives the edges from it — the catalogue entry is incomplete |
| **Path analysis** | Event `Grouped Pages` · Sequence order `time` · Transaction identifier `id` · Weight `purchase` | Renders as a multi-column flow diagram. Has viewport controls |
| **Decision tree** | Response `Iris Species` · Predictors (4 measures) | See the in-object tab strip below |
| **Forecasting** | Time axis `Transaction Date` · Measure `Sales Rep Actual` · Underlying factors `Market Penetration`, `Order Marketing Cost` | **Two factors assigned, one used.** Only `Order Marketing Cost` appears as a panel, in the Reset menu and in the Bounds table — the model selects its own factors and the UI shows only those, without saying so (INFERRED — confidence Medium) |
| **Custom graph** (`Custom Bar Line Graph_solution`) | **Shared Category** `Transaction Month` · **Shared Measure** `Profit` · **Line Grouping** `Product Brand` | See below — the most structural finding in the bundle |

**Custom templates extend the role catalogue at runtime (OBSERVED).** A custom graph's object type *is the template's name*, and its roles are *author-named* — "Shared Category", "Shared Measure", "Line Grouping" appear in no built-in object. It rendered as a two-cell stack: an upper cell of two dotted series lines sharing one axis, a lower cell of bars, one shared category axis, independent value axes, one merged legend.

> **Consequence for the rebuild: role schemas must be data, loaded per object type, never hardcoded per chart class.** The 78-object catalogue in G.1 is a shipped default set, not a closed universe.

**Analytic objects nest their own tab strip (OBSERVED).** The decision tree renders a model header —

> **Decision Tree of Iris Species** · Event: **Virginica** · Fit: **False Positive Rate 0.020 ▾** · Observations: **100 of 100**

— above an in-object tab strip with ‹ › scroll arrows: **Decision Tree · Icicle · Variable Importance · Assessment**, each a different rendering of the same fitted model. No other object type nests tabs inside its frame. The `Observations: 100 of 100` line is the clearest row-count disclosure anywhere in the product (compare Strength 5).

**Forecasting is a what-if environment, available to readers (OBSERVED).** The object renders actual points, a model line and a **confidence band past a vertical forecast divider**, with each underlying factor in its own stacked panel below. Its top-right carries **What if ▾**:

| Mode | Surface |
|---|---|
| **Scenario analysis** | Modal: chart/table view toggle · **History cutoff** slider · **Adjust ▾** · **Reset ▾** · Undo/Redo · **Apply** (disabled until something changes). Editable points sit on the **factor** series |
| **Goal seeking** | The same, plus **Bounds ▾**. Editable points sit on the **target** series instead — you set the goal, it solves for the factor |

*Adjust* offers **Set all to constant value · Add value to all · Add percentage to all · Progressively add value**, with a numeric Value field. *Reset* offers **Factor: \<name\>** and **Reset all**. *Bounds* is a table **Factor | Lower Bound | Upper Bound**, both defaulting to **Unbounded**. Apply was never pressed.

**Viewport controls are not a map exclusive (OBSERVED — corrects session 6).** Path analysis exposes the same on-hover cluster (fit · pan · zoom in · zoom out) under its ⋮ and maximize. The rule is geometric, not type-specific: objects laid out in a **free 2-D space** (map, network, path) get viewport controls; objects on a **category/value grid** do not.

**Path analysis discloses fabricated ordering (OBSERVED).** A footer ⓘ reads *"An artificial sequence order was generated for 6 paths that contains simultaneous events."* The product tells the reader it invented ordering where the data had ties — the disclosure discipline the rest of the product lacks (compare defects 2, 3, 7, 8). The sentence is also ungrammatical.

**An object can be re-typed from the viewer, and one target is marked recommended (OBSERVED).** The viewer object menu carries **"Change \<type\> to ▸"**. For a treemap with a (1 category, 1 measure) signature the targets were: **Bar chart (recommended)**, Butterfly chart, Crosstab, Dot plot, Dual axis bar chart, Dual axis bar-line chart, Dual axis line chart, Gauge, Key value, Line chart, List table, Needle plot, Numeric series plot, Pie chart, Scatter plot, Step plot, Targeted bar chart, Waterfall chart, Word cloud — 19 targets, the current type excluded. The **"(recommended)"** marker is a third surface for the chart-choosing resolver found in session 9 (canvas auto-chart, Suggest pane, and now conversion ranking), reinforcing defect 35.

### G.2d The Suggestions engine, characterised (OBSERVED, session 11)

Ten batches were generated in a blank sandbox on `RETAILDEMO_2` (2.34M rows × 57 columns) — the initial load, seven Refreshes and three "Add more suggestions". Every batch had the same shape. **The pane is a fixed slot rotation with randomised column picks, not a ranked recommender.**

| Slot | Caption template | Object type produced | Frequency |
|---|---|---|---|
| **1** | `<varying category>, Country_Lat by State_Lat` (or the `_Long` pair) | a **two-measure comparison** — Butterfly, Dual axis bar, or Dual axis bar-line | **10 of 10** |
| **2** | `<category> by Frequency` / `<category>, Frequency by Category` | **Treemap** | **10 of 10** (filled by `Department` in 9 of 10) |
| **3** (and 4 in five-card batches) | free-form: `ChannelType by Cost`, `Age Bucket by Storeage`, `<x> of Frequency Percent` | varies (Word cloud observed) | varies |
| **last** | `<date column> by <varying measure>` | **Time series plot** | **10 of 10** |

Batch size is **4 or 5** and is never disclosed.

**Slot 1 is bound to the table's most strongly correlated measure pair (OBSERVED, sessions 11–12).** The pair is fixed per data source and only the category rotates:

| Data source | Slot-1 measure pair | Batches |
|---|---|---|
| `RETAILDEMO_2` | `Country_Lat` by `State_Lat` (occasionally the `_Long` pair) | 15 of 15 |
| `PRODUCTS` | `Cost` by `Retail Price` | 5 of 5 |

Column position is ruled out — in the Data pane's measure list `Country_Lat` is 9th and `State_Lat` 25th of 29, while `Cost` is 1st and `Retail Price` 5th of 9. What both pairs share is near-perfect correlation: a state's latitude tracks its country's, a product's cost tracks its retail price. **This confirms the vendor guide's "measure correlations" mechanism** (§P.3) and locates the real defect: correlation is computed **with no semantic veto**, so on any table carrying coordinates the coordinate pair wins slot 1 every time and the chart sums latitudes into "millions" (longitudes into negative millions). On `PRODUCTS`, where the most-correlated pair happens to be two currency columns, slot 1 produces a **genuinely sensible chart**. Defect 19's fix is therefore to **exclude latitude, longitude, year, identifier and code columns from the measure pool before correlation is computed**, not to re-rank afterwards.

**Slot 1's chart type is a random draw, not a decision (OBSERVED, session 12 — resolves a session-11 UNKNOWN).** Thirteen slot-1 insertions were sampled; **three categories each produced two different chart types from identical inputs**:

| Category | Cardinality | Types produced |
|---|---|---|
| `Department` | 6 | **Butterfly** *and* **Dual axis bar** |
| `Location` | 6 | **Butterfly** *and* **Dual axis bar** |
| `Open` | 1 | **Dual axis bar-line** *and* **Dual axis bar** |
| `ChannelType` | 3 | Dual axis bar |
| `Transaction Time of Day` | 3 | Dual axis bar-line |
| `Age Bucket` | 7 | Butterfly |
| `Country` | 7 | Butterfly |
| `Storechain` | 3 | Dual axis bar-line |
| `MDY` | 6 | Dual axis bar |

Same category, same measure pair, same caption, different object. The distribution across 13 samples — Butterfly 4, Dual axis bar 5, Dual axis bar-line 4 — is consistent with a **uniform random draw from the three two-measure comparison types**. The date-versus-nominal hypothesis is dead: `MDY`, `Location` and `Department` share a classification and all three types appear among them. **There is no encoding decision here to reverse-engineer, and none to copy.**

**The slot structure holds on a second, unrelated table (OBSERVED, session 12).** Adding `PRODUCTS` produced the same four slots with that table's columns: `<cat>, Cost by Retail Price` · `<cat> by Frequency` (filled by `Product Category` in 5 of 5) · free-form · `Date Order was Delivered by <measure>`. The structure is the engine, not an artefact of one dataset.

**Multi-source scoping (OBSERVED, session 12 — resolves a session-11 UNKNOWN).** With two sources loaded the combobox lists both, **auto-switches to the newly added one** and regenerates. No card in six batches mixed columns from two tables. The pane's source selector is **not independent**: changing the source in the **Data** pane switched the Suggestions pane too — one selection exposed in two places.

**Three independent blindnesses (each OBSERVED):**
- **Non-deterministic.** Seven Refreshes on unchanged inputs gave seven different column sets; Refresh discards the current list and there is no pinning or history, so a suggestion seen and not taken is gone (defect 53).
- **Selection-blind.** With `Brand Name` selected and confirmed `aria-selected="true"` in the Data pane, ten generated suggestions used it **zero times** (defect 52).
- **Report-blind.** After `Department by Frequency` was inserted as a treemap, three consecutive Refreshes offered it again (defect 51). **This directly contradicts the vendor guide**, which states that items already used are not reused in newly generated suggestions — see §P.3.

**Insertion (OBSERVED).** Double-click inserts into the current page — note this *works* here, unlike the object library where double-click appends instead (defect 27). Right-click offers *Add to current page*, *Add to new page* and *Delete*. An inserted card is **consumed** and a new card appears in its place; a **deleted** card is **not** replaced. Undo labels are descriptive throughout: `Undo: Add object Butterfly - Location 1`, `Undo: Add object Treemap - Department 1`, `Undo: Add object Word cloud - ChannelType 1`, `Undo: Add object Time - Date 1`, and for a new page `Undo: New page Page 2 with object types: Dual axis bar-line chart` (plural "types" for one object). **Delete produces no undo entry and no toast** (defect 50).

**What a suggestion fills.** Required roles plus data tips, and nothing else:

| Inserted object | Assigned | Left empty |
|---|---|---|
| Dual axis bar – MDY | Category `MDY` · Measure (bar) `Country_Lat` · Measure (bar 2) `State_Lat` · Data tips ×3 | Lattice rows/columns, Animation, Hidden |
| Butterfly – Location | Category `Location` · Measure (bar) `Country_Lat` · Measure (bar 2) `State_Lat` · Data tips ×3 | — |
| Treemap – Department | Tile `Department` · Size `Frequency` · Data tips ×2 | Color |
| Word cloud – ChannelType | Word `ChannelType` · Size `Year` · Data tips ×2 | Color |
| Time – Date | Time axis `Date` · Measure `StoreNum` · Data tips ×2 | Group |

**Naming is inconsistent with itself (OBSERVED).** The card says `Department by Frequency`; the object it creates is titled `Frequency of Department`. The card says `MDY, Country_Lat by State_Lat`; the object is titled `Country_Lat, State_Lat by MDY`. The operands swap and the preposition changes, so a user cannot match a suggestion to the object it produced (defect 54). A third caption form, `<x> of Frequency Percent`, appears for percent-of-total measures, and the trailing term is sometimes the literal word `Category` — which is **not a column in this table** but the Data pane's group heading, and the corresponding role in the inserted object was left empty (defect 55).

**Two rendering faults seen in the cards themselves:** `Transaction Date/Time by 12 week RFM Bucket` drew both axis titles and **no marks at all** (defect 56); `MDY, Country_Lat by State_Lat` rendered its date axis as **unordered clock times** (`12:09:00, 9:09:00, 10:09:00, 11:09:00, 8:09:00, 1:10:00`) from a column the Data pane classifies as a date.

**This is a fourth chart-choosing code path.** Session 9 found the canvas auto-chart resolver and the Suggest pane disagreeing; session 10 added the viewer's "(recommended)" conversion ranking; this session shows the Suggest pane is not a resolver at all but a template rotation. Defect 35 stands and widens.

### G.2e Multi-item drag-and-drop: the drop resolver (OBSERVED, session 13)

Selecting several data items and dragging them onto an **empty canvas** runs a different resolver from the single-item automatic chart. Measured on `PRODUCTS` (748K orders, 23 categories, 9 measures); the object identity was read from the Data Roles pane header each time, not from the undo entry.

| Dropped set | Object created | Role assignment |
|---|---|---|
| 1 category | **Bar chart** | Category; **Measure auto-filled with `Frequency`** |
| 1 category + 1 measure | **Bar chart** | Category, Measure |
| 1 category + 2 measures | **Bar chart** | Category; **both** measures in the Measure role |
| 1 **date** + 1 measure | **Time series plot** | Time axis, Measure |
| 2 categories | **List table** | Columns ×2 |
| 2 categories + 1 measure | **List table** | Columns ×3 — the measure enters as a plain column |
| 2 measures | **Heat map** | Axis items ×2; **Color auto-filled with `Frequency`** |
| 3 measures | **Heat map** | Axis items ×2; Color = the third measure |
| **4 measures** | **Correlation matrix** | `Show correlations: Within one set of measures`; Measures ×4 |
| 5 items including `Frequency` | **Correlation matrix** | **`Frequency` silently dropped**; the 4 real measures used |

**The rules:** two or more categories → List table, everything folded into `Columns`; exactly one category → Bar chart, or Time series plot if that category is a date, with all measures stacked into `Measure`; no category → Heat map for 2–3 measures and **Correlation matrix for 4 or more**. `Frequency`, the synthetic row-count measure, is excluded from a correlation set without comment.

**Scatter is substituted without disclosure, and the undo entry leaks the discarded choice.** Three drops whose object is not a scatter plot produced an undo entry naming one (`Add Scatter - Cost 1 …` for the 2-, 3- and 4-measure drops), while the 5-item drop was labelled `Add Correlation - Cost 1 …` correctly. Read as: the resolver picks **Scatter**, then substitutes a binned heat map (748K points will not plot) or a correlation matrix, and writes the undo entry from the **pre-substitution** decision. The substitution is never shown to the user (defect 59).

### G.2f Drop targets — a three-zone model (OBSERVED, session 13)

| Target | Behaviour | Undo grammar |
|---|---|---|
| **Empty canvas** | New object per §G.2e | `Add <name> with data items <list>` |
| **The gutter around an existing object** | New object, **split in that direction** — verified on the left and right gutters | `Add <name> with data items <list>` |
| **An object's body** | Assigns to a compatible role: **replaces** a filled single-item role, **appends** to a multi-item role | `Replace <old> from <object> with <new>` |
| **A named role slot** in the Data Roles pane | Assigns to that role, and **also appends the item to `Data tip values`** | `Assign <item> to <object>` |
| **A chip inside a multi-item role** | Reorders within the role | `Reorder items of <object> in <role> role` |

**There is no in-object "edge zone".** Drops 8px, 28px and 68px inside the object's right border all behaved as body drops; only a drop past the border, in the canvas gutter, created a split.

**The body-drop resolver ignores empty optional roles, silently.** On a bar chart with `Category` filled and `Group` empty, dragging a second category onto the **body** did nothing — no change, no undo entry, no message — while the same item dropped on the **`Group` slot** was accepted immediately (defect 58). A measure dropped on the `Category` slot was likewise refused in silence.

**Mid-drag feedback is UNKNOWN.** Rows carry `draggable="true"`, so the app uses HTML5 drag-and-drop; synthesised pointer events do not start a drag and a real one cannot be paused. Drop-target highlighting, insertion indicators and cursor states were not observed — every outcome above was read from the result and the undo entry.

### G.2g The geo-map family: one object, seven layers (OBSERVED, session 14)

Dropping a geography item alone on the canvas creates **`Geo coordinate - <item> 1`**. Its Options pane carries **Graph Frame → Change type**, and that dialog lists **seven layer types** — **Bubble · Scatter · Cluster · Contour · Line · Pie · Region**. Switching the layer **renames the object** (`Geo cluster - …`, `Geo region 1`, `Geo pie - …`), so what the object library presents as several geo objects is **one object with a layer property**. Undo: `Undo: Change type to Cluster for Geo coordinate - Geographic Item 1 1`.

| Layer | Roles (`*` = required) |
|---|---|
| **Scatter** (Geo coordinate) | Geography\*, Size, Color, Data tip values, Data label, Hidden, Animation |
| **Cluster** (Geo cluster) | as Scatter |
| **Bubble** (Geo bubble) | Geography\*, **Size\***, Color, Data tip values, Data label, Hidden, Animation |
| **Region** (Geo region) | **Geography\***, **Color\***, Data tip values, Data label, **Data values**, Hidden, Animation |
| **Pie** (Geo pie) | Geography\*, Size, **Measure**, **Category\***, Data tip values, Data label, Hidden, Animation |
| **Contour** (Geo contour) | Geography\*, **Color** — only two roles |
| **Line** (Geo line) | Geography\*, **Width**, Color, **Pattern**, Data tip values, Data label, Hidden, Animation |

**A geography item's source type decides which layers it can serve.** A **lat/long** item drives point layers (Scatter, Cluster, Bubble, Pie, Contour); a **name/code lookup** item drives point **and** region layers, because it carries both a centroid and a polygon; **Line** needs a path geography that neither produces. **The mismatch is handled by silent deletion** — switching a lat/long-backed map to **Region**, and a lookup-backed map to **Line**, both **cleared the Geography role entirely**, leaving a blank placeholder ("Color by Geography" with an *Assign data* button) and no message (defect 64). Compare defect 18, which silently *re-maps* roles; this one discards them.

**Verified rendering.** Geo coordinate: 213 city points on an OpenStreetMap basemap. Geo cluster: grey count bubbles (5, 61, 79, 33, 6, 2). Geo region: a working choropleth (*"Frequency of Geographic Item 2"*, countries on a 15K–1.2M ramp) with the required Color role **auto-filled with `Frequency`**. An **ⓘ on the rendered object** reads *"No matches were found for supplied geography data items: England."* — the unmapped value is disclosed on the object as well as in the creation dialog.

**Map background (Options → Geo Maps).** A **Map background** checkbox, a **Map service** field with a browse button, and a **Transparency** slider. The service browser is a filterable tree with a thumbnail and description per entry: **Automatic** — *"selects a background map automatically based on the report theme that is currently displayed. For example, the High Contrast map is selected when the high contrast theme is displayed"* — and **OpenStreetMap**, which expands to **Standard · Light · Dark · High Contrast**. **Esri ArcGIS Online** services sit behind a third-party terms dialog (Accept / Decline, stored under *Settings → Geographic Mapping*); that consent was deliberately not answered, so the Esri catalogue is **UNKNOWN**. The object also gains an **Enable zoom and pan** option that non-map objects lack — the setting behind the viewport control cluster recorded in session 10.

**A custom-map report that renders nothing (OBSERVED).** `150_305_Using a Custom Geo Map`, opened read-only with its required prompts satisfied, rendered an **empty page**. The viewer pane names an object (`Facility Locations`) while `role="application"` returns zero objects and the pane answers *"Select an object to see its roles."* A geography item whose provider is missing takes the whole object down silently (defect 65).

### G.2h Statistical objects and statistics-flavoured chart options (OBSERVED, session 15)

The Statistics and Machine Learning role tables in §G.1 were **re-verified item by item in a sandbox and match exactly**. What follows is what those tables do not say.

**An unconfigured statistical object renders a complete worked example.** Inserting *Nonparametric logistic regression* with no data draws:

> **Nonparametric Logistic Regression of Example Data** · Event: **(none selected)** · Fit: **KS (Youden) 0** · Observations: **0 of 0**

above a **four-panel grid** — **Fit Summary** (p-value bars) · **Iteration Plot** (Objective Function vs Step) · **Spline Plot** · **Confusion Matrix** — all on example data, with a central **Assign data** button. The author sees the model's panel layout and its header vocabulary before committing a single column. This is the "placeholder sample data" strength (Strength 9) at its most useful.

**Cluster, configured** (`Variables` = `Customer Age`, `Margin`) renders **two stacked panels** — a cluster-centroid strip plot keyed by **Cluster ID**, and a **parallel coordinates plot** of coloured polylines — under a header carrying **two** disclosures:

> **Cluster** · **Observations: 646K of 2.3M** · **Polylines: 72**

The dropped-row figure matches the logistic regression's exactly, so the drop is driven by missing values in the chosen measures and is reported consistently; `Polylines: 72` names its own truncation. Same discipline as the decision tree's `Observations: 100 of 100`.

**Model comparison takes no roles at all** — the pane answers *"Roles are not supported for the selected object."* — and states its precondition in a modal:

> **No Comparable Models** — "There are no models in the report which can be compared. To compare models, there must be at least two models which use the same **partition**, **response data item**, **event level**, and **group by** data items."

Four named, checkable conditions: excellent content, delivered as a **modal that blocks the properties pane and re-fires on every selection**, so the object cannot be inspected — only deleted (defect 69).

**The regressions' required markers overstate the requirement.** Four effect roles each carry `*` on Linear regression, GLM and Logistic regression, yet the object runs once **any one** is filled (defect 72).

#### Statistics-flavoured chart options

| Object → section | Settings |
|---|---|
| **Box plot → Box Plot** | Box direction · **Measure layout: Automatic \| Separate axes \| Shared axis** · **Outliers: Ignore \| Show \| Hide** (default **Hide**) · Hide outliers · Outlier bin outlines · Averages. Style adds a dedicated **Fill** and **Outlier Gradient** pair |
| **Histogram → Histogram** | Direction · Transparency · **Bin range: System-determined values \| Measure values** · Set a fixed bin count · **Bin count (2-100)** — the valid range is stated in the label |
| **Scatter plot → Fit Line** | **Type: None (default) \| Best fit \| Linear \| Quadratic \| Cubic \| PSpline** · Transparency · an ⓘ beside the label |

The box plot's three-way **Ignore / Show / Hide** is a real distinction most tools collapse into a checkbox — *ignore* excludes outliers from the statistics, *hide* computes but does not draw them — but the UI never explains which is which and **defaults to Hide**, so whiskers are computed from data the reader never sees (defect 70). The histogram's inline `(2-100)` is the right pattern and makes the forecast horizon's silent rejection of 0 and 9999 (defect 15) look worse by comparison (defect 73). A scatter plot ships with **no fit line** and the setting sits four sections down the Options pane (defect 74).

### G.2i Fitted models, Model comparison, and the last two charts (OBSERVED, session 16)

**A fitted model carries a live header and a handoff.** With `Response` = `ChannelType` and `Predictors` = `Customer Age`, `Margin`:

> **Decision Tree of ChannelType** · Event: **Store ▾** · Fit: **KS (Youden) 0.3872 ▾** · Observations: **2.3M of 2.3M** · **Create pipeline ▾**

`Event ▾` picks the modelled level, `Fit ▾` picks the statistic and shows its value inline, `Observations` gives rows used of rows available, and **`Create pipeline ▾` → Add to new project · Add to existing project** promotes the fitted model into a Model Studio pipeline project — the seam between the exploratory tool and the ML workbench, offered on the object itself. (Not clicked: it creates a project outside the report.) Panels: Decision tree → **Tree · Variable Importance · icicle · Confusion Matrix**; Forest → **Variable Importance · Error Plot (Misclassification Rate vs Number of Trees) · Confusion Matrix**. A long fit shows a **"Loading…" spinner over the greyed example-data placeholder**.

**Model comparison is configured by a dialog, not by roles.** Inserting it opens **Add Model Comparison**: `Data:` · `Response:` · `Event level:` shown as **fixed facts inherited from the candidate models**, then `Available models:` with **Select all** and a checkbox per model; **OK is disabled until one is ticked**. Output:

> **Model Comparison of ChannelType** · Event: **Store**

| Panel | Content |
|---|---|
| **Fit Statistic ⓘ** | one bar per model of the chosen statistic — Decision tree ≈ **0.39**, Forest ≈ **0.10** on KS (Youden). **The winner is drawn in the accent colour, the loser in grey** |
| **Confusion Matrix** | Observed × Predicted lattice **faceted by Model** |
| **Relative Importance Plot** | Variable × Model heat strip with a Relative Importance colour legend |

This is the most clearly designed object in the product — one question, three linked panels, a colour-coded verdict — and it is worth copying wholesale.

**Two objects, same columns, different populations (OBSERVED).** `Cluster` on `Customer Age` + `Margin` reported **646K of 2.3M**; `Decision tree` and `Forest` on the same two columns reported **2.3M of 2.3M**. The tree-based models tolerate missing predictor values where the cluster drops those rows — a defensible choice that is **never stated in the UI**, so two objects on one page silently describe different populations (defect 75).

**The last two statistics-flavoured graphs:**

| Object | Roles (`*` = required) |
|---|---|
| **Parallel coordinates plot** | **Variables\*** — a single role, the same shape as Cluster |
| **Vector plot** | **X axis\*, Y axis\*, X Origin\*, Y Origin\*** · Color, Group, Lattice columns, Lattice rows, Data tip values, Hidden |

The vector plot is the only object whose four asterisks are all **structurally necessary** (it draws an arrow from origin to endpoint) — a useful contrast with the regressions, whose four asterisks mean "any one of these" (defect 72).

### G.3 Capability boundaries (do not invent beyond these)
- No zoom or pan on standard charts; the Overview axis is the only navigational aid.
- No period-over-period comparison on any chart; time calculations exist **only** as Data-pane calculated items.
- No relative date filtering anywhere in the filter or control UI (Section H.6).
- No distinct-count aggregation in the aggregation menus.
- No `COALESCE`/`IFNULL`; missing values are handled by `Missing()`, `NotMissing()`, `IsSet()`, `NumMiss()`.
- No statistical reference lines (mean, median, percentile) — constants and parameters only.
