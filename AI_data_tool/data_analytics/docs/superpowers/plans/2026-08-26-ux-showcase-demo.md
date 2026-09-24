# UX Showcase Demo Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A second seeded demo report — "UX Showcase" — that demonstrates, with real data, every interactive facility the platform has: button actions, the five page types, hierarchical drill-down over an option tree, and the interactive options (cross-filter modes, bookmarks, prompts).

**Architecture:** Pure seeder extension. Every facility already exists in the product (verified in code — nothing new is built): page types `normal | hidden | popup | tooltip | drillthrough` (`PagePropertiesPanel.tsx:14-18`, `ReportPage.page_type`), button actions `navigate`/`url` (`WidgetRenderer.tsx:462-476`, `cfg.action`/`cfg.actionPageId`/`cfg.actionUrl`), drill hierarchies (`HierarchyNode`, `_seed_drill_hierarchy` in `demo_content.py`), bookmarks, prompts and interaction modes (page `interaction_mode`, `PagePropertiesPanel`). The demo pack ADDS a report that exercises each one, seeded through the existing `seed_demo_features` pipeline so load/unload semantics stay one transaction.

**Tech Stack:** backend seeder only (`app/services/demo_content.py`) + backend tests. No frontend changes — the point is that the existing UI renders it all.

**Spec:** the user's request (2026-08-25): "add multiple demo for UI/UX facilities like actions, interactive options, page types and hierarchical data types option tree in widgets and controls and drill down". Plus the conventions in `demo_content.py`'s own module docstring (org-scoped, flush-not-commit, idempotent by drop-and-rebuild, demo-tagged for unambiguous removal).

## Global Constraints

- Same execution machinery as the Layer 4 plan: backend tests in Docker via PowerShell (`docker run --rm -v "d:\Omda 2025\projects\data_analysis_dashboard_ai\AI_data_tool\data_analytics:/repo" -w /repo/backend datalytics-backend:test python -m pytest <args> -q --no-header -p no:warnings`); focused tests per task, full suite at the final checkpoint; commits end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
- Additive: `demo_content.py` conventions are binding — no seeder commits; everything reached through org-scoped collections; the existing demo (datasets, reports, features) must seed EXACTLY as before (its tests untouched and green).
- The showcase must survive `remove_demo_content` — everything hangs off the demo Report/Dataset rows the remover already finds.

---

### Task D1: The showcase report — pages and actions

**Files:**
- Modify: `backend/app/services/demo_content.py` (new function `seed_demo_ux_showcase(db, org_id, datasets) -> Report`, called from the router's seed pass after `seed_demo_features`)
- Modify: `backend/app/routers/demo.py` (call the new seeder inside the same transaction; include its report in the response counts)
- Test: `backend/tests/test_demo_ux_showcase.py`

**Interfaces:**
- Consumes: `datasets` dict returned by `seed_demo_datasets` (the `sales` dataset with 24 months of transactions), `Report`/`ReportPage`/`ReportWidget` models, `HierarchyNode`.
- Produces: one `Report` named `"UX Showcase (demo)"` with SIX pages:

| page | page_type | demonstrates |
|---|---|---|
| "Start here" | `normal` | a text widget explaining the tour + THREE button widgets: `action='navigate'` → the Drill-down page; `action='navigate'` → the Popup page; `action='url'` → the docs URL with a `{filter}` token if the URL template supports it (check `WidgetRenderer.tsx:476`'s replace) |
| "Drill-down" | `normal` | two chart widgets bound to the sales drill hierarchy (Region → Product → Month — reuse `_seed_drill_hierarchy`'s tree or seed a second tree Category → Product) at different starting levels, so clicking drills down the option tree |
| "Popup KPIs" | `popup` | three KPI cards — opens as a floating overlay from the Start-here button |
| "Hover detail" | `tooltip` | a small table — bound as the hover tooltip of the Drill-down page's main bar chart (wire whatever field binds a tooltip page to a widget; find it by grepping `tooltip` in `WidgetRenderer.tsx`/`PagePropertiesPanel.tsx` and copy the existing demo's detail-page wiring idiom) |
| "Transaction detail" | `drillthrough` | the existing detail-page pattern: reached by drill-through from the Drill-down page's charts, carrying the clicked context as a filter |
| "Hidden notes" | `hidden` | a text widget — proves the hidden type (visible in edit mode, absent in view mode) |

Steps (TDD): write the test class first — `TestShowcaseSeeds` (report exists with exactly these six page_types; the three buttons carry the right `action`/`actionPageId`/`actionUrl` configs pointing at REAL page ids in the same report; widgets bound to the hierarchy reference a real `HierarchyNode` root; re-seeding is idempotent — second call yields one showcase report, not two; `remove_demo_content` deletes it) — verify RED, implement, GREEN, commit.

### Task D2: Interactive options — cross-filter modes, bookmark tour, prompt page

**Files:**
- Modify: `backend/app/services/demo_content.py` (extend `seed_demo_ux_showcase`)
- Test: extend `backend/tests/test_demo_ux_showcase.py`

Add to the showcase:
- Page `interaction_mode` variants: set the Drill-down page to highlight-mode cross-filtering and the Start-here page to filter-mode (copy the exact field/values from `PagePropertiesPanel.tsx`'s interactionMode state), so the two pages demonstrate the difference side by side.
- A **prompt page** if the page model supports it (`PagePropertiesPanel` shows `promptColumn`/`promptLabel`): a page that asks for a Region before rendering.
- Two **bookmarks** on the showcase report ("Loss-making months", "Top region only") capturing filter states — follow the existing demo bookmark's seeding idiom in `seed_demo_features`.
- Tests: each addition pinned (modes differ between the two pages; prompt config present; bookmarks restore distinct filter states); existing demo tests still green (`tests/test_demo*.py -q`), then FULL backend suite once.

### Task D3: Verify in the browser, hand over

- Load the demo via the API on the running backend, screenshot the Start-here page and one drill interaction (headless browser, the session's existing screenshot workflow), attach to the report; note anything that renders wrong as findings rather than fixing silently.
- Update `ARCHITECTURE_COMPARISON.md`'s demo/UX rows if touched; rebuild HTML.

## Self-Review

- Coverage vs the user's request: actions ✅ (navigate + url buttons) · interactive options ✅ (interaction modes, bookmarks, prompt) · page types ✅ (all five) · hierarchical option tree in widgets/controls ✅ (drill hierarchy bound to charts at two levels) · drill down ✅ (hierarchy drill + drillthrough page). Nothing in the request is unaddressed.
- Placeholders: the tooltip-page binding and prompt fields are named as "find the exact field by grepping X" rather than guessed — deliberate, the implementer verifies against real code; everything else carries exact values.
- Types: `seed_demo_ux_showcase(db, org_id, datasets) -> Report` consistent across D1/D2/D3.
