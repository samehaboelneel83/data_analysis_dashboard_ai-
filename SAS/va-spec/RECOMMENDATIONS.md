# Recommendations — what to build, in what order, and what to leave behind

Drawn from sixteen hands-on sessions against SAS Visual Analytics. This is the judgement layer on top of `va-spec/`: the spec says what the product does, this says what you should do about it.

---

## 1. The three things that actually make the product work

Strip away 78 object types and the product rests on three ideas. Get these right and the rest is surface area.

**1. Typed roles with filtered pickers.** Every object declares a role schema; every picker offers only type-compatible columns; required roles are enforced. A user cannot put a date on a measure axis. This is why a novice can build a working chart in four clicks, and it is the single highest-leverage thing to copy.

> **But make role schemas data, not code.** Custom graph templates ship their own object type name and their own author-named roles (`Shared Category`, `Shared Measure`, `Line Grouping`). The 78-object catalogue is a shipped default set, not a closed universe. If you hardcode role sets per chart class you will have to rewrite the layer the first time someone wants a custom template.

**2. Auto-fill the required measure.** Drop a category, get a bar chart counting rows. The object renders *immediately*, and the user edits from something rather than assembling from nothing. Every empty-state in the product follows the same instinct — objects draw example data before they have any.

**3. Descriptive undo on everything.** "Undo: Change Benchmark Country Selector from Russian Federation to China." Users explore fearlessly because every step is named and reversible. **Then unify the grammar** — the product has seven different sentence patterns for one operation family and the worst one is `Change option "fitLineType"`. One pattern: verb, item, role, object, new value.

---

## 2. Build order

### P0 — the spine (nothing else works without it)
Data source → data items with a **label / physical-column split** → typed role schemas loaded as data → object instances → one query executor per data session → canvas layout → descriptive undo. Single-object reports end to end: bar, line, list table, crosstab.

### P1 — the loop that makes it a product
Filters (object, page, report), the three-layer filtering model, controls as first-class filter sources, cross-object actions, and **one merged, inspectable filter stack per object** shown identically to author and reader. Page and report prompt bars.

### P2 — the things users ask for on day two
Calculated items and an expression editor; display rules including banded ranges; ranks; totals and subtotals **recomputed from source rows at their own level**; export.

### P3 — the differentiators
Geography items with a live validation panel; the geo layer stack; forecasting with scenario analysis and goal seeking; the statistical object family with model headers and `Model comparison`.

### P4 — assistive, once the core is trustworthy
Suggestions, automatic chart selection, outlier insights, the report linter. **Do these last.** Every one of them in the subject product is actively misleading today, and an assistive feature that recommends nonsense costs more trust than it earns.

---

## 3. Patterns worth stealing outright

| Pattern | Where it appears | Why it matters |
|---|---|---|
| **Validate a mapping before committing it** | New Geography Item: `86% mapped`, *"1 of 1 unmapped values: England"*, live map preview | The single best interaction in the product. Apply it to every mapping step — geography, joins, custom categories, imports |
| **Disclose the population, always** | `Observations: 646K of 2.3M`, `Polylines: 72`, `Observations: 100 of 100` | Every object that drops, caps or truncates should say so in its header, in the same words |
| **Say when you invented something** | Path analysis: *"An artificial sequence order was generated for 6 paths that contains simultaneous events"* | Where the engine breaks a tie or fabricates ordering, tell the reader |
| **Colour the verdict** | Model comparison: winning model's bar in accent, loser's in grey | Make comparisons legible before a number is read |
| **Theme-aware basemaps** | Map service `Automatic` swaps to a High Contrast tileset under the high-contrast theme | Cheap, and the difference between an accessible map and an unusable one |
| **Classify sensitivity at the column and propagate it** | A PII badge on `City` inherited by the geography item derived from it | One classification, enforced down the derivation chain |
| **Split the reader's filter list by origin** | Viewer pane: `Permanent Filters` vs `Interactive Filters` | Readers can audit why they are seeing what they see |
| **Undo in the viewer** | *"Undo: Change Continent Selector from North America to Europe"* | Readers explore instead of rebuilding state by hand |
| **Self-documenting reports** | Overview page as table of contents; "View details about this page" opening a pop-up page | Needs no feature you won't already have |
| **Promote a model to the real workbench** | `Create pipeline → Add to new project` | Offer the seam on the object, not buried in a menu |

---

## 4. The seven failure patterns to design out

Seventy-six catalogued defects collapse into seven habits. Fix the habit, not the instance.

**1. Silent refusal.** A body drop the resolver can't place, a type-mismatched drop, a Hierarchy dialog whose OK does nothing, a pie "Other" of 101%, a forecast horizon of 0. Nothing happens and nothing is said. **Rule: every refusal states a reason, and every disabled control says which of its causes applies** — the subject has five distinct causes (no content, not saved, no permission, not in this deployment, nothing selected) behind one undifferentiated grey.

**2. Silent substitution.** Scatter becomes a heat map at 748K points; a layer switch discards an incompatible geography item; converting an object re-maps roles; `Frequency` is dropped from a correlation set. **Rule: never change what the user asked for without naming the change in the object.**

**3. Aggregation without semantics.** Everything defaults to Sum, including latitudes, years and identifiers. The suggestion engine's slot 1 is filled with the most *correlated* measure pair — which on any table with coordinates is a latitude pair, perfectly correlated and perfectly meaningless. **Rule: exclude coordinate, year, identifier and code columns from measure pools before any statistic is computed. Infer a safe default aggregation per column and warn before summing a non-additive one.**

**4. Undisclosed truncation.** 3,000-row caps behind a tiny ⓘ, 100-row word clouds, text objects that clip mid-sentence with no affordance, axis labels thinned to four of forty. **Rule: truncation is a first-class state with a visible explanation and a one-click alternative.**

**5. Inconsistent disclosure of the same fact.** The histogram states `Bin count (2-100)` in its label; the forecast horizon silently rejects 0 and 9999 with no range anywhere. Two objects fit the same two columns over populations differing by 1.7M rows without either saying so. **Rule: one disclosure vocabulary, applied everywhere.**

**6. Accessibility as an afterthought.** Canvas rendering with no data values in the DOM; suggestion cards as nameless `<canvas>`; selection state that vanishes when virtualised rows scroll away; two inconsistent naming rules for object accessible names; shortcuts disclosed only inside one pane. **Rule: every canvas object ships a real accessible representation, and the accessible name is generated by the same function that writes the title.**

**7. Non-determinism without recovery.** The suggestion engine returns a different set on every refresh — different columns *and* a different chart type for identical inputs — with no pinning, no history, and Refresh discarding what you had. **Rule: assistive output is reproducible and explainable, or it doesn't ship.**

---

## 5. Five decisions I'd make differently from the subject

1. **One chart-choosing resolver, not four.** The subject has a canvas auto-chart resolver, a Suggestions template rotation, a viewer "(recommended)" conversion ranking, and a multi-item drop resolver — and they disagree. Build one, call it from all four surfaces, and have it explain its choice.
2. **Addressable URLs.** The subject has a single route; no deep links, no browser history. Report, page, object and view mode should all be addressable — it costs little early and is near-impossible to retrofit.
3. **A reflow mode for the canvas.** Nothing in the subject ever stacks: at phone width the prompt strip scrolls sideways and the canvas keeps its absolute layout. Give authors absolute placement *and* a reflow mode, and let them choose per page.
4. **Merge the author's and reader's filter views.** The asymmetry — readers see the full filter stack, authors don't — is the strangest defect in the product. One model, two skins.
5. **Ship the statistics family early, not late.** The model objects are the subject's strongest work: a header stating event, fit statistic and population; sub-tabs for alternative views of one fit; `Model comparison` as a three-panel verdict. They are also where competitors are weakest.

---

## 6. Two things to explicitly not copy

- **The 78-object catalogue as a menu.** Users cannot choose between "Needle plot" and "Dot plot" from a list. Lead with the role assignment and let the resolver propose the form, with the catalogue as an override.
- **Assistive features that guess.** Suggestions, automatic charts and outlier insights are the subject's weakest surfaces precisely because they act without explaining. Either make them reproducible and accountable, or leave them out of v1 — a blank Suggestions pane costs nothing; a pane that confidently proposes summed latitudes costs credibility.

---

## 7. Where the evidence is thin

Treat these as unverified in the spec, not as gaps in the product: the Esri basemap catalogue (a consent gate I did not answer), five of six Machine Learning objects, `Create pipeline`'s output, export and sharing output, mid-drag visual feedback, custom geography provider authoring, and real device rendering. The bundle marks each one UNKNOWN rather than guessing, and that labelling is worth preserving as you build — it tells you which parts of the spec you can rely on and which you should re-check against the live product.
