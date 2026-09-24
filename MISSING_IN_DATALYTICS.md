# What Datalytics Is Missing vs SAS Visual Analytics

Gap list derived from `SAS_VA_FEATURE_COMPARISON.md`. Each entry says what SAS has (with the evidence source in the `SAS/` bundle), what Datalytics has today, and why it matters. Ordered by **impact on a real user**, not by size.

States: ❌ missing entirely · 🔶 partial · 🟡 mechanism exists, UX missing

---

## Tier 1 — Gaps a user hits in the first hour

### 1. ❌ Interactive undo/redo in the builder (descriptive, per-edit)
- **SAS:** every configuration change produces a named, reversible step — *"Undo: Change Benchmark Country Selector from Russian Federation to China"* — in the **editor and the viewer**. The spec calls it one of the three ideas the whole product rests on (`RECOMMENDATIONS.md §1`, `spec H.3`).
- **Datalytics:** version history with restore (report-level snapshots). No Ctrl+Z. Deleting a widget mid-thought means opening the history pane.
- **Why it matters:** undo is what makes users *explore fearlessly*. Version history protects the document; undo protects the train of thought. This is the single largest UX gap.
- **Note:** SAS has seven inconsistent undo grammars — copy the idea, not the mess. One grammar: *verb, item, role, object, new value*.

### 2. 🔶 Placeholder-first objects + auto-filled required measure
- **SAS:** an object dropped with no data renders synthetic sample data behind an "Assign data" button; dropping a single category auto-fills the measure with row count and **renders immediately** (`spec C.5, D.A3–A4`). The canvas is never blank.
- **Datalytics:** widgets are empty until configured; the drop-rules build charts only on a data-item drop.
- **Why it matters:** "edit from something" beats "assemble from nothing" — it's why a novice builds a working chart in four clicks.

### 3. 🔶 Truncation & population disclosure as a contract
- **SAS:** every model header states its population ("Observations: 646K of 2.3M"); caps exist but hide behind a tiny ⓘ — the spec's blueprint demands `rowsScanned`, `rowsReturned` and a `truncation{limit,total,reason}` object **on every result** (`PLATFORM_BLUEPRINT §4.2`).
- **Datalytics:** some disclosures exist; not systematic across shapers and widgets.
- **Why it matters:** two widgets on one page silently describing different populations is how dashboards lie. Cheap to add at the query-response layer; nearly impossible to retrofit later.

### 4. ❌ Reason codes on every refusal and disabled control
- **SAS (as defect):** five different causes behind one undifferentiated grey; silent rejections everywhere. The spec's fix — every refusal states a reason; batch authorization decisions return `not_saved` / `no_permission` / `no_content` / … (`RECOMMENDATIONS §4.1`, `BLUEPRINT §8`).
- **Datalytics:** better than SAS in places (named dropped fields, named dead interaction edges) but no uniform reason-code convention.
- **Why it matters:** this is the cheapest "professional feel" feature in the whole list.

## Tier 2 — Capability gaps (features SAS has, we don't)

### 5. ❌ Statistics/ML as canvas objects with diagnostic tabs
- **SAS:** 8 statistics + 6 ML **objects**: drop Logistic Regression on the page, assign Response + Predictors, the model runs and renders a header (event level, fit statistic, population) with sub-tabs — Fit Summary, Residual Plot, Odds Ratio, Confusion Matrix (`spec G.1, sessions 15–16`). The spec's judgement: *"the subject's strongest work… where competitors are weakest. Ship it early."*
- **Datalytics:** the same math (and more) lives in the analysis catalogue and panel — but as one-shot analysis results, not living, filterable, cross-filtering widgets on the report canvas.
- **Gap = presentation, not math.** Wrap existing `regression` / `glm_logistic` / `decision_tree` / `automated_prediction` into widget shapers with tabbed panels.

### 6. ❌ Model comparison object
- **SAS:** a three-panel verdict comparing two comparable models, winner's bar in accent color, loser in grey; refuses on insert if no two comparable models exist — with an explanatory dialog (`session 16`).
- **Datalytics:** `automated_prediction` picks a champion internally; there is no side-by-side comparison surface, and saved `prediction_models` can't be compared at all.

### 7. ❌ Geography item validation panel
- **SAS:** New Geography Item dialog shows **"86% mapped · 1 of 1 unmapped values: England"** plus a live map preview *before* you commit (`session 14 §2.4`). The recommendations call it *"the single best interaction in the product"* and say to apply it to every mapping step (joins, custom categories, imports).
- **Datalytics:** the matcher (name / ISO-2 / ISO-numeric, boundary sets) exists and is deliberately never-fuzzy — but match failures surface only as a blank map after the fact.

### 8. 🔶 Sub-national geography supply + geo layer stacking + contour
- **SAS:** provider-backed states/provinces/ZIPs; geo contour object; region+coordinate layer stacks on one map; theme-aware basemaps.
- **Datalytics:** bring-your-own boundary file (mechanism ✅, geometry ❌); no contour; no multi-layer map object; tile layer deferred pending the customer's tile server.
- **Why it matters:** found the hard way already — the hospital dashboard with 27 Egyptian governorates drew a blank world map.

### 9. ❌ Pop-up and Hidden page types (drill targets)
- **SAS:** a page can be Basic / Hidden / Pop-up; double-click a mark → modal pop-up page with its own export; "set prompt bar values of target page" per link (`spec D.A11–A12`).
- **Datalytics:** page navigation and drill-through exist, but every page is a tab; no modal drill target, no hidden utility pages.

### 10. ❌ Data source mapping (cross-source interactions)
- **SAS (documented):** map corresponding items across two sources so one click filters objects fed by both; formats must match, validated at mapping time.
- **Datalytics:** one dataset per widget; cross-filtering never crosses datasets. Increasingly visible as reports mix sources.

### 11. 🔶 First-class partitions (train/validation as a data item)
- **SAS:** New Partition dialog creates a persistent split column; every statistics/ML object takes a Partition ID role, so *all* models score on rows they never saw, consistently.
- **Datalytics:** `automated_prediction` splits internally; nothing shared or reusable across analyses.

### 12. 🔶 Universal lattice (small multiples) and missing chart affordances
- **SAS:** Lattice rows/columns are roles on ~20 graph types; plus **Overview axis** (brushable mini-chart), **Animation** role, **Data tip values** role.
- **Datalytics:** one SmallMultiplesRenderer; no overview axis; no animation; tooltip extras not a role.

### 13. ❌ Offline report package export
- **SAS:** export a self-contained snapshot (definition + data) that can be hosted/viewed elsewhere.
- **Datalytics:** none. Note we already have the perfect substrate: the platform runs air-gapped and the embed path exists — a static bundle renderer is achievable.

### 14. ❌ Mobile app / PWA
- **SAS:** browser + installable PWA + native app (documented).
- **Datalytics:** responsive web only, and the builder is desktop-shaped. The SAS spec's own advice: don't reflow the editor — build a **separate read-only mobile viewer**.

### 15. 🔶 Viewer-side analysis affordances
- **SAS:** in the *viewer*: "View insights" (per-object outlier analysis), object re-typing with a "(recommended)" ranking, forecast what-if scenario sliders (`session 10 §5`).
- **Datalytics:** Insights Hub and scenario analysis exist but live in authoring/analysis surfaces, not in the reader's hands.

### 16. ❌ Session crash recovery + multi-document interface
- **SAS:** unsaved editor state autosaved server-side; landing offers "Restore previous session". Multiple reports open with a switcher ("Opened reports (N)").
- **Datalytics:** unsaved builder work dies with the tab; one report at a time.

### 17. 🔶 Text analytics depth
- **SAS:** text topics + **sentiment**, 30+ languages.
- **Datalytics:** topics (NMF/TF-IDF), no sentiment, English stop words only — an Arabic-first platform with English-only stop lists is a visible inconsistency.

### 18. 🔶 Smaller specifics
- Per-intersection scoped expressions (ISINSCOPE-style measure overrides) — SAS has, we don't.
- AI value-group generation for custom categories.
- Report package/page-level PDF options (page setup, TOC, appendix).
- Evaluate Performance (report-level performance audit with findings).
- Geo bubble-change / vector-plot style rare charts — verify against the 67 before building.
- Batch authorization decisions endpoint (one call, fifty decisions, reasons attached).

## Tier 3 — Things SAS has that we should **not** copy

For completeness, from `RECOMMENDATIONS.md §6` — these are in the SAS bundle but are documented mistakes:

- The 78-object menu as the primary chooser (lead with roles + resolver instead — we already do).
- Assistive features that guess without explaining (our suggester already executes and labels its engine — keep that bar).
- One-route SPA with no deep links (we already have real routes).
- Canvas-only rendering with no accessible projection (we render DOM/SVG — keep it, and add ARIA summaries rather than moving to canvas wholesale).
- Silent substitution / silent refusal patterns (the seven failure habits — designed out, not in).
- Destroying manual links when switching action modes.

---

## Summary count

| Tier | Count | Theme |
|---|---|---|
| 1 | 4 | Trust & hand-feel: undo, placeholder-first, disclosure, reasons |
| 2 | 14 | Capabilities: model objects & comparison, geography UX+supply, pop-up pages, cross-source mapping, partitions, lattice/overview/animation, packages, mobile, viewer analysis, recovery/MDI, text depth, misc |
| 3 | — | Anti-goals (documented SAS defects) |

The pattern across Tier 1 is one sentence: **SAS earns trust by narrating itself — every act is named, reversible, and disclosed.** That habit, more than any single widget, is what the plan in `MASTER_PLAN.md` installs.
