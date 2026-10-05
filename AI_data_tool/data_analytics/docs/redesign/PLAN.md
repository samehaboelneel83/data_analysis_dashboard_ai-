# Datalytics redesign — implementation plan

Source of truth: `DATALYTICS_REDESIGN_HANDOFF.md` and `boards/` in this folder.
Work happens on branch `said`; the pre-redesign commit is tagged `before-redesign`.
Nothing is pushed.

## Rules for every sub-step

- Work on `said`. Commit after each sub-step. Never push.
- Follow the handoff's "What must stay untouched" rules and the Phase 1 rule.
- Before committing: the step's tests, full `npm test`, `npm run build`, rebuild
  (`docker compose up -d --build`), capture the affected screens (light, dark,
  Arabic, Arabic dark) and compare them against `boards/`. Fix visible
  differences, or log why they were kept.
- Stop immediately if something needs sudo, a test fails that can't be fixed
  without touching untouched areas, or a change would need backend work.
- Small design questions: pick the option closest to the boards, log it, continue.

## Plan

- [x] 1 Ask AI quick fixes
- [x] 2 Key influencers stopgap
- [x] 3a Datasets list
- [ ] 3b Dataset detail shell + Overview + tab map
- [ ] 3c Remaining tabs + Share dialog
  - >> GATE A: stop, report the whole Datasets screen
- [ ] 4a Ask AI Phase 1: layout, thread, column panel, answer card
- [ ] 4b Ask AI Phase 1: all states (first run, no dataset, thinking, clarification, offline, error)
  - >> GATE B: stop, report Ask AI
- [ ] 5-gap Gap pass for Home and Viewer (no code). List what has no backend data.
  - >> GATE C: stop, the owner decides what to hide
- [ ] 5a Home
- [ ] 5b Viewer
- [ ] 6-gap Gap pass for Builder (no code)
  - >> GATE D: stop, report Home + Viewer; the owner decides on the Builder gaps
- [ ] 6a Builder layout restyle (top bar, Fields panel, canvas, Inspector)
- [ ] 6b Builder copilot tab, AI offline, and all states
- [ ] FINAL Full regression: all tests, build, capture every screen, compare against all boards, final summary, fix the flaky `Lineage.test.tsx`, and a clean-up list (test datasets 7 and 8, chat threads, the uncommitted init.sql edit)
  - >> GATE E: stop, final report

## Log

### 1 Ask AI quick fixes — `405b2b2`, `6ec9358`

1a markdown via shared `lib/inlineMarkup`, 1b `lib/displayNumber` (prose and
grid rounding; exports keep raw values), 1c `majorityDir`, 1d autoChart for
numeric-looking labels; chat chart value labels rounded like the sentence.
Capture script committed with Ask AI states 02-05..02-08: `fc166e5`.

### 2 Key influencers stopgap — `e7c8627`

KI-1 default outcome (marked, then measure, then inferred; no identifier
fallback, picker prompt instead), KI-2 identifier suffixes, KI-7 ranked
renderer. Kept no red/green and "named like an identifier" wording (approved).

### 3a Datasets list — `6f61866`, `e85cbad`, `2b37a64`

**Changed:** `pages/Dashboard.tsx` (the `/datasets` list) rebuilt around a health
strip (counts by kind and status, stale/failing from the lineage graph's
`health`, links to the affected dataset), facets (Source, Status, Mine only,
Certified only, sort), Source / Freshness / Dashboards columns, a preview panel
(facts, sensitivity label, column chips, first rows, dashboards built on it,
Open / Build dashboard / Ask), and first-run, no-match, loading and error
states. New `pages/datasetsList/` (classify, DatasetPreview, CSS, tests).
`useListFilter` also returns `setQuery`. Bulk delete, the row menu, paging,
live counts and the shared/certified chips are unchanged.

**Deviations from the boards:**
- Dashboards count column added: the handoff text asks for it; the board omits it (text wins).
- Row ⋯ menu column kept: Suggest dashboards and Delete have no other entry point.
- Full pager with 8 per page kept: pinned by tests and BUG-031; the board shows "25 per page".
- First run says "upload a file or connect a database", not "drop anywhere on this page": a page-level drop would need a change to the upload flow, which stays untouched.
- No "up to 200 MB" (the configured limit is 100 MB) and no "6 sample datasets": numbers not hard-coded.
- Sample data tile only for admins: it links to Settings, which only admins can open.
- No "Check system status" on the error card: there is no status page every user can open.
- Health uses the lineage graph only, not one `pipeline-health` call per dataset.
- Health strip hidden while loading and on error (the board shows it): totals of nothing are pinned as a lie by an existing test.
- All of the above approved by the owner.
