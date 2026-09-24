# Visual Analytics Tool — reverse-engineering deliverable

A complete implementation specification for building a new analytics product with similar functionality, workflows, information architecture, interaction patterns and visual language — **without copying proprietary source code, brand assets, wordmarks, icons or product naming.**

**Subject:** SAS Visual Analytics, "Explore and Visualize" module (SAS Viya for Learners deployment).
**Method:** nineteen live observation sessions driving the running application through a browser, plus one cross-check against vendor training material. No vendor source code was read. Fourteen sessions worked in blank, never-saved sandbox reports on a 2.34M-row sample table. Two sessions (6 and 10) observed **saved, production, multi-page reports read-only in View mode** — nine reports in all, covering parameters, forecasting, network, path and decision-tree objects and a custom graph template. Nothing was saved, modified, exported, shared, copied, commented on or deleted in any session, and no confirmation dialog was ever accepted.
**Observed:** 22–23 Sep 2026.

## Files

| File | Contents |
|---|---|
| `application-map.md` | What the product does · complete sitemap · routing model (observed and proposed) |
| `screens.md` | Every significant screen, pane, dialog, and the empty/loading/error/confirmation state catalogue |
| `activities.md` | 20 user activities (entry, preconditions, inputs, steps, result, alternates, validation, errors, dependencies) and 6 end-to-end journeys |
| `components.md` | Reusable UI component inventory with variants, states, inputs, outputs and interactions |
| `visualizations.md` | All 78 object types with required and optional roles, per-chart detail, and capability boundaries |
| `data-model.md` | Observed and inferred entities, attributes, relationships, lifecycles; state machines |
| `interaction-model.md` | Pointer semantics, selection, undo, progressive disclosure, the three-layer filtering model, keyboard |
| `design-system.md` | Typography, colour, layout and component tokens measured from live computed styles; responsive behaviour |
| `implementation-spec.md` | **Start here to build.** Architecture, state, data model, visualization config, routing, components, interactions, responsive, design system, P0–P4 priorities, patterns to copy, 84 defects to fix, acceptance criteria, vendor-documentation cross-check, and the UNKNOWN list |
| `UI_UX_SPECIFICATION.md` | **The design deliverable.** A build-ready UI/UX spec: principles, information architecture, layout system, the full token set, a component library with anatomy/variants/states/a11y, interaction patterns, the nine-state catalogue, microcopy rules, accessibility, responsive and theming, and a definition of done |
| `PLATFORM_BLUEPRINT.md` | **Read this third.** The full-stack engineering design: data plane, semantic layer, query protocol, document service, dual-path rendering, client architecture, platform services, security, and a five-phase build plan |
| `observed-architecture.md` | The runtime and network evidence behind the blueprint — payload budget, the WASM rendering engine, service topology, the query protocol and the autosave mechanism |
| `RECOMMENDATIONS.md` | **Read this second.** The judgement layer: the three ideas the product rests on, a P0–P4 build order, patterns worth copying, the seven failure habits behind all 76 defects, and what not to copy |
| `screenshots/` | 32 catalogued capture states across nine areas, **30 with images**, each with route, precondition, the exact action that reproduces it and a cross-reference. `captures.json` indexes them; `import-captures.py` files a timed capture run into the right folders automatically; `CAPTURE_STATUS.md` records why the crawl itself cannot write images |

## Change log

| Date | Change |
|---|---|
| 22 Sep 2026 | Sessions 1–5: object library, right panes, data preparation, interactivity. Initial ten-file split. |
| 23 Sep 2026 | Session 6 folded in (first saved production report, read-only): viewer side pane (`screens.md` §C.3b), drill-down (`interaction-model.md` §H.2b), viewer undo (§H.3), asymmetric filter disclosure (§H.6, defect 11 narrowed), banded display rules (`visualizations.md` §G.2b), Stacking Container component (`components.md`), patterns 11–13 and defects 36–38, UNKNOWN list refreshed. |
| 23 Sep 2026 | Sessions 7–9 folded in: exhaustive option sweeps, automatic-chart decision table (defects 34–35). |
| 23 Sep 2026 | **Session 19** (closing the UNKNOWN register): three more ML objects fitted and all six role schemas re-verified; **Create pipeline fully resolved** — it creates a real Model Studio project and a four-node runnable pipeline, hijacks the tab and crashes on arrival; the platform application map added to `application-map.md` §B.4; defects 82–84. Esri left unanswered by instruction. |
| 23 Sep 2026 | **Session 18** (design tokens and UI/UX synthesis): spacing scale, the single 100ms motion token, layering and focus treatment measured and added to `design-system.md` §L.4b; **`UI_UX_SPECIFICATION.md` added** — the consolidated, build-ready design specification. |
| 23 Sep 2026 | **Session 17** (system architecture): client payload measured at **63.4 MB** incl. a **12.9 MB WebAssembly rendering engine**; service topology, the executor/job/results query protocol, `PUT`-per-change autosave, dual service workers and empty client storage recorded in `observed-architecture.md`; defects 77–81; **`PLATFORM_BLUEPRINT.md` added**. |
| 23 Sep 2026 | **Session 16** (two real models fitted and compared): **Model comparison output resolved** — dialog-configured, three-panel verdict with the winner colour-coded (`visualizations.md` §G.2i); fitted-model headers and **Create pipeline**; Parallel coordinates and Vector plot roles; defects 75–76; **`RECOMMENDATIONS.md` added**. Four UNKNOWNs closed. |
| 23 Sep 2026 | **Session 15** (statistical objects and statistics-flavoured charts, blank sandbox on RETAILDEMO_2): §G.1's Statistics and ML role tables re-verified and confirmed; placeholder rendering, Cluster's two-panel output and row disclosures, Model comparison's precondition, and the Box plot / Histogram / Fit Line option catalogues added as `visualizations.md` §G.2h; Geo group corrected to a **layer stack**; a seventh undo grammar; defects 69–74. |
| 23 Sep 2026 | **Session 14** (geography items and the geo-map family, blank sandbox on RETAILDEMO_2): the New Geography Item dialog in full (`screens.md` §C.4b), the seven map layers and their roles (`visualizations.md` §G.2g), basemap services, `GeographyItem` added to the data model, patterns 18–20, defects 64–68. Two standing UNKNOWNs closed; an Esri terms dialog was left unanswered by choice. |
| 23 Sep 2026 | **Session 13** (Data pane, multi-select and drag-and-drop, blank sandbox on PRODUCTS): the multi-item drop resolver and the three-zone drop-target model (`visualizations.md` §G.2e–G.2f), Data-pane selection corrected in `components.md` and `interaction-model.md` §H.3b, defects 58–63, and the vendor's four-measure correlation rule confirmed on the drop path (§P.3). Two earlier selection claims retracted. |
| 23 Sep 2026 | **Session 12** (Suggestions follow-up, second sandbox with a second data source): slot-1 chart type shown to be a **random draw**, multi-source scoping resolved, and the session-11 verdict on the vendor's correlation claim **corrected** — the correlation mechanism is real, the missing piece is a semantic veto. Defects 19 and 53 re-scoped; two UNKNOWNs closed, one opened. |
| 23 Sep 2026 | **Session 11** (Suggestions pane, blank sandbox on RETAILDEMO_2): the engine characterised as a fixed four-slot template rotation (`visualizations.md` §G.2d), pane and card anatomy (`screens.md`, `components.md`), activity A19 rewritten, defects 48–57, defects 19 and 35 sharpened, and a first pass at the vendor-documentation claims (§P.3, revised by session 12). |
| 23 Sep 2026 | **Session 10** (favorites crawl, nine saved reports, read-only): analytic and custom objects (`visualizations.md` §G.2c), viewer pane corrections and the four filter section kinds (`screens.md` §C.3c), report prompt bar (§C.3d), four new dialogs, six new components, control cascades and the first disclosed keyboard shortcuts (`interaction-model.md` §H.6b, §H.7), narrow-width behaviour (`design-system.md` §M), patterns 14–17, defects 39–47, defect 29 widened to four causes, UNKNOWN list refreshed (parameters, analytic objects and custom templates resolved). |

## Evidence labelling

- **OBSERVED** — seen directly in the running UI.
- **INFERRED — confidence: High / Medium / Low** — deduced from observed behaviour.
- **DOCUMENTED** — from vendor training material, not re-verified in the app.
- **UNKNOWN** — could not be determined from the UI. Listed explicitly rather than guessed.

## Originality constraints

1. Do not copy the vendor's name, logo, icon set, licensed typeface, theme names or any screenshot.
2. The design tokens describe proportions and roles — reproduce the *system*, not the brand hue.
3. Vendor-flavoured terminology ("Crosstab", "Key value", "Data roles", "Lattice") has a neutral mapping in `implementation-spec.md`.
4. No proprietary source was read; everything here is black-box behaviour.
