# Activity Inventory and User Journeys

> Part of the Visual Analytics reverse-engineering deliverable. Sibling files: `application-map.md`, `screens.md`, `activities.md`, `components.md`, `visualizations.md`, `data-model.md`, `interaction-model.md`, `design-system.md`, `implementation-spec.md`, `screenshots/`.
> **Evidence labels:** OBSERVED (seen in the running app) · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.

## D. Activity Inventory

Each activity: purpose · entry · preconditions · inputs · steps · result · alternates · validation · errors · dependencies. All OBSERVED unless marked.

### A1 — Create a report
- **Purpose:** start a new authoring document.
- **Entry:** Landing → "New report"; or editor ⋮ → New.
- **Preconditions:** authenticated session.
- **Inputs:** none.
- **Steps:** 1) Click New report. 2) Editor opens with an untitled report ("Report N", N increments per session) and one empty page.
- **Result:** unsaved report; Save enabled but Export/Share/Copy link/Evaluate Performance greyed until saved.
- **Alternates:** open an existing report; restore a recovered session.
- **Validation / errors:** none.
- **Dependencies:** none.

### A2 — Add a data source
- **Purpose:** bind a table to the report.
- **Entry:** Data pane → Add data, or a "Recently Used Data" link, or any role picker when no source exists.
- **Preconditions:** a report is open.
- **Inputs:** table selection.
- **Steps:** 1) Open Choose Data. 2) Filter by Available (default) / Favorites / Recent, or search. 3) Select a table (checkbox). 4) Add.
- **Result:** Data pane lists columns grouped **Category / Measure**, each category showing its distinct count; the system adds **Frequency** (measure) and **Frequency Percent** (aggregated measure); sensitive-data shields and outlier dots appear.
- **Alternates:** Import data (upload); New data from join; New data from aggregation.
- **Validation / errors:** "You must select an item." if a table is only previewed. Search is slow and briefly shows "Results: 0".
- **Dependencies:** A1.

### A3 — Add a visualization object
- **Purpose:** put a visual on the page.
- **Entry:** Objects pane (double-click or drag); Data pane item → "Add to current page"/"Add to new page"; **a multi-item drag from the Data pane** (select with Ctrl/Cmd+click or Shift+click, then drag — the resolver and its decision table are in `visualizations.md` §G.2e); Suggestions pane card; page template.
- **Preconditions:** a page exists. A data source is **not** required.
- **Inputs:** object type.
- **Steps:** 1) Double-click object. 2) Object appears with placeholder sample data + "Assign data".
- **Result:** object named `<Type> N`; after roles are filled the name becomes `<Type> - <first role item> N`; title follows data ("Frequency of Region").
- **Alternates:** "Change <type> to ▸" converts an existing object (43 targets offered, none greyed).
- **Validation / errors:** Model comparison refuses on insert with an explanatory dialog.
- **Dependencies:** A1. Real rendering needs A2.

### A4 — Assign data to roles
- **Purpose:** bind columns to the object's visual channels.
- **Entry:** object "Assign data" button, or right rail → Data Roles.
- **Preconditions:** A2 + A3.
- **Inputs:** column per role.
- **Steps:** 1) Open Data Roles. 2) Click "+ Add" on a role. 3) Pick from a **type-filtered** list. 4) Repeat.
- **Result:** object queries and renders. Assigning only a category **auto-fills the required measure with Frequency**. Adding a real measure afterwards *sometimes* silently replaces Frequency and sometimes keeps it alongside — both were observed, so the rule is **UNKNOWN**; a rebuild should make the replacement explicit.
- **Alternates:** drag a data item onto the object; role item right-click → Remove / Move to / Aggregation / Format.
- **Validation:** single-item roles grey out "+ Add" after one item; multi-item roles use checkboxes. Pickers exclude incompatible types (Time axis = dates only; Measure roles = measures only).
- **Errors:** Geography role shows "No data items available for role." with no remedy offered.
- **Dependencies:** A2, A3.

### A5 — Change a measure's aggregation
- **Purpose:** switch Sum to Average, Min, etc.
- **Entry:** Data pane item right-click → Aggregation ▸ (global default), or Data Roles item right-click, or column-header menu (object-level override).
- **Inputs:** one of 20 aggregations (Default (Sum) ✓, Sum, Average, Std dev, Std error, Variance, Count, Number missing, Minimum, Q1, Median, Q3, Maximum, Skewness, Kurtosis, CV, Uncorrected SS, Corrected SS, t statistic, p-value).
- **Result:** every dependent object, filter header and display rule follows the new aggregation.
- **Constraint:** **no distinct count** in this menu — only via the `Distinct()` function in a calculated item.
- **Dependencies:** A2.

### A6 — Create a calculated item
- **Purpose:** derive a new column or aggregated measure.
- **Entry:** Data pane → + New data item → Calculated item.
- **Inputs:** Name*, expression.
- **Steps:** 1) Name it. 2) Build an expression from Operators / Functions / Data / New parameter (double-click inserts a skeleton). 3) Optionally add a **Scope** (aggregated items only). 4) OK.
- **Result:** item appears under Measure or Aggregated Measure; format auto-detected; **it is not added to any object automatically**.
- **Validation:** live error count "(n)", red squiggles, messages for syntax, type mismatch, aggregated-vs-row mixing and literal division by zero. OK greyed until valid.
- **Errors:** Results preview unavailable for aggregated measures; preview keeps the **last valid** result while text is invalid.
- **Dependencies:** A2.

### A7 — Filter an object
- **Purpose:** restrict the rows an object sees.
- **Entry:** right rail → Filters → + New filter.
- **Inputs:** a column, then values/range.
- **Steps:** 1) Pick item (Advanced filter, object's own items, common filters, then all items). 2) Adjust checkboxes / range slider / histogram. 3) Optionally open ⋮ for condition type, missing-value handling, invert, sort, promote to common filter.
- **Result:** object re-queries; other objects untouched unless linked.
- **Defaults:** **Include missing values ✓**; condition "Is between (inclusive)" for numerics; detail (not aggregated) values; continuous for numerics, discrete for categories.
- **Alternates:** "Filter aggregated values" retargets the filter at the aggregate (header renames to "Sales (Average)"); Advanced edit writes the expression form.
- **Errors:** an inverted full selection yields "No data matches the current filters." with no warning.
- **Dependencies:** A4.

### A8 — Rank (Top/Bottom N)
- **Purpose:** show only the leading or trailing members.
- **Entry:** right rail → Ranks → + New rank.
- **Inputs:** category, subset type, count, rank-by measure, ties, All Other.
- **Defaults:** Top count, **10**, rank-by = the object's measure, Ties ☐, All Other ☐.
- **Result:** applies immediately.
- **Observed quirks:** ranked bars are drawn **alphabetically, not in rank order**; **count 0 is accepted** and the chart silently keeps the previous result; Ties caps at **count + 100 tied rows** with a notice. Tie-breaking when Ties is off appeared to follow descending member name (**INFERRED — confidence: Medium**, from two samples).
- **Dependencies:** A4.

### A9 — Add a prompt (control)
- **Purpose:** let a reader filter interactively.
- **Entry:** drop a category on the **report control strip** (filters all pages), the **page control strip** (filters the page), or the page body (filters nothing until linked).
- **Inputs:** a category (or measure/date for Slider).
- **Steps:** 1) Place the control. 2) Configure Options (Required, Initial value, multi-select, search, missing-values option). 3) For a body control, open Actions and tick target objects.
- **Result:** report/page controls filter automatically and **cascade into each other**; body controls need explicit links.
- **Types:** Drop-down list, Button bar, List, Slider, Text input. "Change to" converts between Drop-down, Button bar, Text input and Slider (List is not offered).
- **Validation:** Text input matches **exactly and case-sensitively** despite offering prefix suggestions; Slider **excludes missing values even at full range** unless its "Missing values option" is enabled.
- **Dependencies:** A2 + at least one target object.

### A10 — Link objects (cross-filtering)
- **Purpose:** make one object drive others.
- **Entry:** right rail → Actions.
- **Two mechanisms:** (a) **Automatic actions on all objects** — page-wide mode: One-way filters ✓ / Two-way filters / Linked selection; (b) **Object Links** — per-target checkbox, each link typed Filter (default) or Linked selection.
- **Result:** selecting a mark filters or highlights targets; a breadcrumb bar shows removable chips when enabled.
- **Destructive side effect:** enabling automatic actions **deletes existing manual object links** (toast + Undo); disabling does not restore them. Page links survive.
- **Quirks:** Two-way mode makes a List control filter itself down to the chosen value; clicking the "All Other" bar **clears** the filter instead of filtering to the excluded members; linked filtering drops empty categories rather than showing zeros.
- **Dependencies:** ≥2 objects on a page.

### A11 — Drill to another page (page link)
- **Purpose:** detail-on-demand.
- **Entry:** Actions → Page Links → tick a target page.
- **Preconditions:** ≥2 pages.
- **Result:** in **view mode**, a **double-click** on a mark opens the target; a single click only selects. A Pop-up page opens as a modal; a Basic page switches tabs.
- **Options:** per-link ⋮ → "Set prompt bar values of target page" ☐.
- **Dependencies:** A12.

### A12 — Manage pages
- **Entry:** page tab "+", page tab ⋮, or Outline pane.
- **Actions:** Rename, Page type (Basic ✓ / Hidden / Pop-up), Limit visibility to users, Delete, Duplicate, Export as PDF, Copy link, Copy embeddable markup, Collapse/Expand controls, Save as page template, Manage page templates.
- **Constraints:** **Hidden and Pop-up are greyed when only one page exists**; Delete greyed likewise; export/link/template items greyed on an unsaved report. Both Hidden and Pop-up undo as "Hide page".
- **Dependencies:** A1.

### A13 — Apply a page template
- **Entry:** empty page → Select a template; or page ⋮ → Manage page templates.
- **Steps:** 1) Open dialog (list ✓ / grid toggle, filter). 2) **Double-click** a template.
- **Result:** inserts a laid-out section of placeholder objects; a dashboard template also turns on the filter breadcrumb. Undo label "Add section with template".
- **Validation:** single click highlights only → "You must select a template."
- **Dependencies:** A1.

### A14 — Style an object / report
- **Entry:** right rail → Options.
- **Inputs:** theme (Dark / Light ✓ / High Contrast / custom), font (38 families), fill and line palettes, **dedicated Missing colour**, **Other colour**, padding, borders, axis settings, legend placement (9-point), data skins, abbreviation scale and precision.
- **Result:** applied live.
- **Quirk:** crosstab display-rule text defaults to a different font from the report font.
- **Dependencies:** A3.

### A15 — Add a display rule (conditional formatting)
- **Entry:** right rail → Display Rules → + New rule.
- **Inputs:** target item, operator (=, <>, ≤x≤, <, <=, > ✓, >=, Missing, NotMissing), value (constant **or another measure**), style.
- **Result:** colours marks/cells; in view mode the Display Rules pane doubles as the legend.
- **Quirks:** **a rule with no colour is accepted and does nothing**; rules test the **displayed aggregated value**; with no intersections chosen a crosstab rule also colours subtotal rows.
- **Dependencies:** A4.

### A16 — Switch to view mode / consume
- **Entry:** pencil toggle or ⋮ → View report.
- **Result:** rails hidden; only Basic pages get tabs; selections made in edit mode carry over; AI assistant icon disappears; ⋮ gains Play report and Edit playback.
- **Side pane tabs:** Data Settings (read-only roles), Display Rules (legend + Alert subscriptions), Filters (**Permanent** and **Interactive**, showing real logic such as `BetweenInclusive(x, MIN, MAX) OR Missing(x)`), Ranks (plain sentence), Comments.
- **Errors:** Comments refuse until the report is saved.
- **Dependencies:** A1.

### A17 — Save / close
- **Entry:** Save button, ⋮ → Save / Save as / Close.
- **Result:** closing an unsaved report raises a three-way confirmation (Save / Don't save / Cancel).
- **Gated by save:** Export, Share, Copy link, Copy embeddable markup, Distribute, Localize, Comments, Evaluate Performance, page Export/Copy link/Save as template, About this report.
- **Dependencies:** A1.

### A18 — Review report quality
- **Entry:** rail → Report Review.
- **Result:** findings by severity (High / Medium / Low counters) with per-finding quick fixes ("Remove the data source …"); filter by Accessibility / Performance; sort by severity; export as PDF.
- **Gate:** Evaluate Performance requires a saved report.
- **Dependencies:** A1.

### A19 — Use auto-suggestions
- **Entry:** rail → Suggestions. Requires a data source; both controls are disabled until one is loaded, and the empty pane shows **no text** (defect 48).
- **Steps:** pick a data source in the pane's combobox → a batch of **4 or 5** cards generates automatically → **Refresh** replaces the batch, **Add more suggestions** appends another → insert by **double-click**, drag, or right-click ▸ *Add to current page* / *Add to new page*; dismiss with right-click ▸ *Delete*.
- **Result:** an object with its required roles and data tips filled, its optional grouping/colour role empty, and a descriptive undo entry. The inserted card leaves the list and is replaced; a deleted card is not replaced and **cannot be undone** (defect 50).
- **Validation:** none. Cards that render nothing are still offered (defect 56).
- **Risk:** the engine is a fixed slot rotation with randomised columns (`visualizations.md` §G.2d) — statistically meaningless suggestions are structural, not occasional. It also ignores the Data pane selection and the report's existing content (defects 51, 52).
- **Dependencies:** A2.

### A20 — Ask the AI assistant
- **Entry:** banner icon (edit mode only).
- **Result:** side panel with starter chips, prompt box with attachment, AI disclaimer. First open shows an English-only notice with "Don't show this message again".
- **Dependencies:** A1. Effect of prompts: **UNKNOWN** (never sent).

---

## E. User Journeys

**J1 — First report, end to end (OBSERVED)**
```
Landing → New report → Data pane → Add data / Recently Used → choose table
  → Objects pane → double-click object (renders placeholder sample)
  → Assign data → role "+ Add" → pick column (measure auto-fills as Frequency)
  → Options → title, style, axes        → Filters → + New filter
  → Ranks → Top N                        → Actions → link objects
  → page tabs "+" → second page → page type Pop-up → Page Links
  → pencil toggle → view mode → verify → Save
```

**J2 — Analyse without authoring (OBSERVED):** `Landing → open report → view mode → controls/prompts → click marks → breadcrumb chips → double-click to drill into pop-up → side pane Filters to read the logic`.

**J3 — Prepare data inside a report (OBSERVED):** `Data pane → + New data item → Calculated item → expression editor → (Scope) → OK → item appears in Data pane → drag to object`. Variants: Custom category (with AI group generation), Hierarchy, Date hierarchy (instant, no dialog), Geography item, Parameter, Partition, New aggregated data (instant, creates a second source), New data from join (timed out in testing).

**J4 — Model a target (OBSERVED):** `Objects → Statistics/ML object → Response + Predictors → model runs immediately → read Fit Summary / Residual / Odds Ratio / Confusion Matrix → (Create pipeline, not exercised)`. Models disclose dropped rows ("Observations: 646K of 2.3M").

**J5 — Build an interactive dashboard (OBSERVED):** `New page → Select a template (Dashboard) → placeholders → assign data to each → add report/page controls → Actions → Automatic actions on all objects → choose mode → verify breadcrumb`.

**J6 — Recover an interrupted session (OBSERVED):** `Landing shows "Recovery available for previous session" → Restore previous session`. Unsaved editor state is persisted server-side (see Section N/K: `POST /files/files` then `PATCH`). **INFERRED — confidence: High.**
