# Datalytics redesign — implementation plan

Source of truth: `DATALYTICS_REDESIGN_HANDOFF.md` and `boards/` in this folder (for the
finished steps; Ask AI follows v1, see below). New sessions: read `HANDOVER.md` first.
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
- [x] 3b Dataset detail shell + Overview + tab map
- [x] 3c Remaining tabs + Share dialog
  - >> GATE A: stop, report the whole Datasets screen
- [x] 4a Ask AI Phase 1: layout, thread, column panel, answer card (visual redesign reverted at the owner's request, see 4-revert)
- [x] 4b Ask AI Phase 1: all states (first run, no dataset, thinking, clarification, offline, error) (visual redesign reverted, see 4-revert)
- [x] 4-revert Ask AI back to the v1 layout with fixes; Datasets menu clipping fixes
  - >> GATE B: stop, report Ask AI — **approved 2026-10-06**

> **Ask AI decision (2026-10-06, owner):** the Ask AI page uses the v1 layout and look
> (as at `120e0ef`) with fixes. The step 4 boards in `boards/step4-ask-ai-phase1/` are
> no longer the spec for it. Kept from step 4: translations, Pending without timed
> stages, the themed delete dialog, offline detection (locks the question box with one
> line), clarification column chips, "What was wrong?" after 👎, and Edit question on
> an error.
> **Decision at GATE B (2026-10-06, owner):** GATE B is approved. Datasets and Ask AI
> are done and stay as implemented. Steps 5 and 6 below (Home, Viewer, Builder) are
> **replaced** by designs from another Claude Design project ("Home Redesign" and
> "Dashboards Parts 1–4"), to be exported to
> `/media/saeed/New Volume1/projects/design-handoff-2/`. Upload, Connections, Lineage
> and the AI button come after that. The theme and design system stay as they are.
> New sub-steps for the new designs will be added here once they arrive; don't start
> them before the owner says so. See `HANDOVER.md`.

- ~~5-gap Gap pass for Home and Viewer~~ (replaced, see above)
- ~~5a Home~~ (replaced)
- ~~5b Viewer~~ (replaced)
- ~~6-gap Gap pass for Builder~~ (replaced)
- ~~6a Builder layout restyle~~ (replaced)
- ~~6b Builder copilot tab, AI offline, and all states~~ (replaced)
> **New designs (2026-10-06):** `/media/saeed/New Volume1/projects/design-handoff-2/`
> (read its README). The `prototype/` folder is the source of truth; the PNGs have
> stitching glitches. Serve it (`python3 -m http.server 8765` from `prototype/`) and
> compare against it. Lucide icons from unpkg are prototype-only; the app keeps its
> own icons. **Desktop only**: skip the tablet and mobile frames. Only Dashboards
> Part 2 (Builder) is approved. Home and Parts 1, 3 and 4 are under the owner's
> review; **don't start a sub-step before its design is approved.**
>
> **Owner's decisions after the 7-gap report (2026-10-06):**
> - **Sidebar and top bar:** keep v1 for everything: group headers, all rail items
>   (Glossary, Dataflows, Automations and Migration stay; the prototype only lacks
>   them because it was made from screenshots), Platform fold and count, collapse
>   icon, direction toggle, the LLM picker, search button, breadcrumbs, the bell's
>   unread count. Two exceptions:
>   - The Builder starts with the icon-only rail; the user can still expand it.
>   - Present hides the dashboard header too, as long as Esc and the on-hover
>     controls still exit.
> - **Builder:** keep and re-home every v1 Builder feature the prototype doesn't
>   show. Nothing is dropped (widget templates, report filters with date presets,
>   layout recipes and Free layout, calculated columns, Auto hierarchy, Ask /
>   Insights / Suggestions panes, the config panel's tabs and settings search,
>   Display rules, Ranks, the Object-to-edit picker, page types, Shift+arrow resize,
>   Ctrl+K, all align/distribute modes, kiosk auto-advance, conflict merge, Refresh,
>   OpenReportsMenu, header fold, sensitivity badge, access dialogs).
> - **Skipped** (they would change widget config semantics, renderer behaviour, the
>   move path or WidgetRenderer): per-widget number format, Show title, automatic
>   switch to horizontal bars, arrow keys moving all selected widgets, drill
>   triggered from outside a widget.
> - **Allowed:** Ask AI `?q=` prefill, schematic thumbnails drawn from each page's
>   widget layout, suggested questions built from dataset columns.
> - View-only users keep v1's gating (no Edit, Present or Add for them). Guest links
>   keep v1's model (several links, each URL shown once, 1–90 days) with the new
>   styling.
> - Every item that needs new backend work stays out (Phase 1 rule) and is listed in
>   "Backend follow-ups" below.
> - Order: lower-risk screens first, the Builder last.

- [x] 7-gap Gap pass for Home and Dashboards Parts 1–4
- [x] 7a Home *(Home design approved 2026-10-06)*: hero with the ask box (Ask AI gains `?q=`), chips from dataset columns, stat tiles, quick actions, Continue (dashboards only), Dashboards and Datasets sections, admin-only Activity and Refresh & jobs, first run, loading, an error per section (whole page only when reports or datasets fail), AI offline
- [x] 7b Dashboards list *(Part 1 approved 2026-10-06)*: Views/Folders column over the workspace tree, filters, grid/list, cards with schematic thumbnails, ⋯ menu, New dashboard dialog, bulk actions, every state including error and folders-failed; v1's subfolders, folder rename/delete, move confirm and publish toggle kept
  - >> GATE C: stop, report Home and the Dashboards list
- [x] 7c Share, Export, Version history *(Part 4 approved 2026-10-06)*: restyle over the existing grants, guest links, embed configs, schedules, PDF/Excel export and versions; v1-only features kept
- [x] 7d View and Present *(Part 3 approved 2026-10-06)*: view header, focus mode, view-mode AI panel (Ask, Insights, Suggest charts), Present controls (header hidden, Esc and hover controls exit), AI offline, v1 viewer gating
  - >> GATE D: stop, report View, Present and Part 4
- [x] 7-QA Fixes from the QA report `/media/saeed/New Volume1/projects/redesign-captures/qa-1/QA_REPORT.md` (owner, 2026-10-06), before 7e: Broken B1 (top priority), B2, B3, B5 (try to reproduce), B7, B8; Visual V1–V10 (V9: numbers must stay distinguishable); T1 on the redesigned screens only; all of T2 (the Arabic sidebar labels in `ar.ts` may be fixed, text only). A failing test before each fix where possible; before/after captures. B4 and B6 go to "Backend follow-ups".
  - >> stop and report before 7e
- [x] 7e1 Builder: header and toolbars (save state, Edit/View, page tab menu, Layout menu with v1's recipes), icon-only rail on entry
- [x] 7e2 Builder: left panel (Insert gallery with preview, Fields, Templates; v1's widget templates, report filters and calculated columns re-homed)
- [x] 7e3 Builder: right panel rail and Properties (Format / Data / Interactions over the existing config panel, keeping every v1 tab and settings search; pinned second panel)
- [x] 7e4 Builder: canvas overlays and widget states (alignment guides, group box, hover toolbar, skeleton, empty result with Clear filters, error details, heavy-page banner)
- [x] 7e5 Builder: shortcuts dialog, copilot offline, and the states the prototype doesn't draw (empty page, read-only, load error, save conflict)
  - >> GATE E: stop, report the Builder
- [x] 7-QA2 Fixes from the second QA report `/media/saeed/New Volume1/projects/redesign-captures/qa-2/QA_REPORT_2.md` (owner, after GATE E): Broken N1 (raw JSX on the Insights button), N2 (Version history and opening a dashboard must not force Edit mode; check v1), N3 (39 revisions at 13:01 with repeated numbers: display bug or autosave), N4 (Arabic hover toolbar covers the widget ⋮ menu), N5 (one-line `key` fix in CustomGraphRenderer.tsx only); B8 with the QA steps exactly; V1 and V4 at 1280 px and 125% zoom; V10 leftovers (dark Data table white square, Platform settings context column); Visual 6–10; Translation 10, 11, 12, 14, 15 and the Key influencers footnotes. A failing test before each fix where possible; before/after captures. B3, B4/13/16 and B6 go to "Backend follow-ups"; the remaining T1 items stay in 8-i18n.
  - >> stop and report
- [ ] 7-QA3 Fixes from the third QA report `/media/saeed/New Volume1/projects/redesign-captures/qa-3/QA_REPORT_3.md` (owner): Batch A builder behaviour (A1–A10); Batch B builder visuals (B1–B6); Batch C builder Arabic (ar.ts) with a check against hard-coded English in Builder components; Batch D round-2 leftovers (D1 breadcrumb at 125%, D2 dark tooltip label, D3 list ⋯ column, D4 one locale-driven date formatter, D5 Insights number isolation).
  - [x] Batch A
  - >> GATE A: stop, captures EN + AR before/after
  - [x] Batches B–D
  - >> GATE B–D: stop, captures EN/AR × light/dark
- [x] 7-QA3-N3 Stop the save burst at its source (frontend only, owner-approved after GATE A).
  - Evaluated: no backend change is needed.
  - Today `persistWidgetLayouts` fires `updatePage` and one `updateWidget` per widget with `Promise.all`. Two effects call it just by opening a page in Edit: the automatic Executive packing of a page with no layout mode, and the compaction of a packed page whose widgets overlap.
  - The fix:
    - both become render-only (the `packedPreview` the canvas already draws);
    - the first real layout edit (drag, resize, nudge, align, distribute, recipe) persists the drawn positions with `layout_mode`;
    - every layout persist writes sequentially, not in parallel.
  - Test: opening an old dashboard (no layout mode, overlapping widgets) in Edit makes zero `updateWidget` / `updatePage` calls, so zero versions.
  - One real edit still writes one version per moved widget. Batching that into one version is the backend row.
- [x] 7-QA4 Fixes from the fourth QA report `/media/saeed/New Volume1/projects/redesign-captures/qa-4/QA_REPORT_4.md`: Broken E1 (new display rule's raw server error), E2 (a dropped field filling a second role); Visual V1–V9; Arabic T1–T6. One GATE at the end; then straight on to 8-i18n, and QA5 over both.
  - >> GATE QA4
- [x] 8-i18n The QA report's T1 strings on pages the redesign has not reached (Glossary, Organizations, Platform settings, Admin settings Basemap, Org units, Row/column security, API keys, Custom connectors, SSO, Maps, Models "random forest", Activity codes, Connections "Combine databases"). QA3 adds: Glossary "Business terms"; Admin Settings Basemap; Platform settings, including the endpoint list scrambled in RTL; SSO "Issuer URL", "Client ID" and the redirect line. QA4 adds:
  - Activity action codes (report.create, …);
  - the admin pages' confirm dialogs (ApiKeys, AdminUsers, AdminRoles, AdminOrgUnits, AdminSso, AdminCustomConnectors, row/column security rules);
  - the Connections toasts ("— connected", "Connection failed", "Test failed") and SourceReview toasts;
  - the dashboards-list group label (`listParts.tsx` "{n} dashboard(s)");
  - the Home dashboards delete title (`hm.dash.deleteTitle`, unisolated name);
  - the report panels outside the Builder's own surface that are still English: Measures, Column formats, Prep pipeline and steps, Model settings and view, Map layers, Map pins, Graph layers, Hierarchy tree, Custom categories, Custom functions, Calc columns, Access dialog, Subscribe, Outlier details, Data view(s), Boundary set picker, Relative date editor, Geo match check, Suggestions pane.
  - These are counted by the same scanner (`src/test/hardcodedStrings.ts`); add each file to `BUILDER_FILES` once translated.
- [x] 7-QA5 Fixes from the fifth QA report `/media/saeed/New Volume1/projects/redesign-captures/qa-5/QA_REPORT_5.md`: F1–F4, R1–R4, L1–L9. One GATE; then push and a short QA6 on these items only.
- [x] 7-QA5b Small fixes before QA6 (S1–S6), one commit, no GATE: delete dialogs open on Cancel, the cross-filter tooltip, automatic chart titles, audit-trail action names, hierarchy and sensitivity labels in Arabic, the Welch evidence line in right-to-left.
- [ ] Then: Upload, Connections, Lineage, the AI button
- [ ] FINAL Full regression: all tests, build, capture every screen, compare against all designs, final summary, fix the flaky `Lineage.test.tsx` (and watch `geoRenderers.test.tsx` and ReportBuilder's "report-level display rules" under load), and a clean-up list (test datasets 7 and 8, chat threads, the uncommitted init.sql edit). QA3 adds: dashboard "QA3-Builder" #16 (made 00:01; share link made and revoked 00:02–00:03; not made by the QA3 run, so the owner decides), and the cached insights QA3 may have saved on "Demo — Sales" and in the Builder AI panel. QA3 adds: stop the port-3002 Vite server ("before" captures) and remove its worktree (`git worktree remove` on the scratchpad `before` folder).
  - >> GATE F: stop, final report

## Backend follow-ups (found during the frontend steps)

Not part of the frontend steps (1–7); candidates for the handoff's section 7 phases.

| Found in | Item | Why it needs the backend |
|---|---|---|
| 3c Data | Download CSV of a dataset (with the Data tab's filters, sort and search) | No dataset export endpoint exists; only Ask AI runs can be exported. |
| 3c Share | Change a grant's View/Edit level in place | `/datasets/{id}/shares` can create and delete grants, not update one. |
| 3c Share | "N row-security rules apply to this dataset" in the share dialog | No endpoint reports the rules that apply to a dataset (related to N9). |
| 7-gap Home, list | Favorites (star a dashboard, Favorites filter and view) | No model or endpoint; `PinnedTile` pins widgets, not dashboards. |
| 7-gap Home, list | Owner name and avatar on dashboards; a display name for the greeting | `ReportOut` has only the `created_by` id; `User` has no name field; non-admins can't look users up. |
| 7-gap Home, list | Duplicate a dashboard | No copy endpoint (rebuilding from page templates loses filters, parameters, rules and theme). |
| 7-gap Home, list | A "Shared" status (this dashboard has been shared with someone) and an exact "Shared with me" on Home | No flag on `ReportOut`; per-row grants calls are author/admin only. (The Dashboards page's "Shared with me" view is built from the workspace tree's `shared_with_me`, see 7b.) |
| 7-gap Home | Connection health ("All healthy") | `DataSourceOut` has no status; `sync_status` isn't exposed; only a live test per connection. |
| 7-gap Home | Recently opened datasets in "Continue where you left off" | `RecentView` tracks reports only. |
| 7-gap Home | Activity events: comments, refresh failures, "shared with a team"; an activity feed for non-admins | Comments aren't audited; refresh failures live in admin refresh-runs; grants are per email; audit-log is admin-only. |
| 7-gap Home | Progress % for a running refresh | `RefreshRun` has no progress field. |
| 7-gap list | View counts and "Most viewed" sort | `RecentView` keeps one row per user and report; no global count. |
| 7-gap list | "Suggested by AI" proposals with Keep / Dismiss | Nothing stores pending proposals or proposes from recent questions. |
| 7-gap list | Undo after delete; bulk share; request edit access | No restore, bulk grant or access-request endpoints. |
| 7-gap Builder | KPI delta ("vs previous period / vs target") and sparkline | The KPI query returns one value. |
| 7-gap Builder | Lock a widget | No field; would also touch the drag handlers. |
| 7-gap Builder | Comment linked to a widget; unread comments | Comments carry only `page_id`. |
| 7e Builder | Count badges on the rail (unread comments, open review findings) | Unread needs per-user read state; review findings are computed in the pane, not served. |
| 7-gap Builder | "Split page" from the heavy-page banner; duplicate a page | No endpoints (page duplicate only via the template endpoints). |
| 7-gap View | A viewer's "Bookmark this view" | Bookmark endpoints bump the revision and need edit rights; no personal bookmarks. |
| 7-gap View | Widget-aware AI ("Reading 12 widgets", "Based on" chips, "N widgets read") and page-specific generated questions | The agent takes only `dataset_ids` or `data_source_id`; no report/page/widget scope. |
| 7-gap View | Insights "Generated N ago" and saved dismissals | The scan is persisted but there is no GET endpoint; no dismiss storage. |
| 7-gap View | Author-defined default filter chips per page | v1 page filters are per viewer (localStorage); no saved config. |
| 7-gap Share | "Can comment" level; transfer ownership | No comment level in the capability ranks; no transfer endpoint. |
| 7-gap Share | Invite with user suggestions, groups, pending invites for outside emails, notify by email with a message | Invite is email-only by design and 404s for non-members; grants are per user; `create_grant` sends no email. |
| 7-gap Share | Guest link that never expires; link that carries the current filters | Guest links require 1–90 days; filters aren't stored on the link. |
| 7-gap Share | Embed display options (tabs, filters, Ask AI, theme, size) | `EmbeddedReport` reads only the token. |
| 7-gap Schedule | Pause / edit a schedule; multi-day picker; PNG format; pages selector; AI summary; groups as recipients | No `enabled` column, no PATCH route; one weekday; xlsx/pdf only. |
| 7-gap Export | "Fit to content" paper; filter summary, page numbers, AI appendix; uses current filters; live preview | PDF accepts paper, orientation, contents and pages only, built server-side without UI filters. |
| 7-gap Export | PowerPoint; page PNG; CSV zip; pick widgets for one workbook; raw/filtered options; size estimate | Not supported by the export endpoints. |
| 7-gap Export | Background export with step progress, 24 h download link, error naming the failing widget with "Export without it" | Downloads are synchronous blobs; errors don't name a widget. |
| 7-gap History | Named versions; preview a version; compare with current; per-version change summary; copy or PDF of a version | No label column; the versions list is metadata only (no snapshot content). |
| GATE D (v1 Suggestions) | Suggestions pane proposes "average year by category"; its preview is refused (422) | The same identifier/measure problem as KI-6: `year` is classed as a measure. Fix the role in the backend (KI-3/KI-6) so suggestions never average a year or an id. |
| 7-QA B4 | An Arabic follow-up in a conversation that started in English is answered in English | The answer language follows the conversation, not the question (see AP3: localize by the question's language). |
| 7-QA2 B3 | Clarifications name columns the dataset doesn't have ("sales by department"), so no column chips can be offered | The model must name real columns (AN1: ground the clarification on the dataset's columns). |
| 7-QA2 B4 / 13 / 16 | Answers (and clarifications) come back in a language other than the UI's: an Arabic follow-up answered in English, the AI panel in English in the Arabic UI, an Arabic clarification in the English UI | The answer language must follow the UI language (AP3), sent with each question. |
| 7-QA2 B6 | "average by" took about 3.5 minutes; an Arabic follow-up spun for over 2.5 minutes with no cancel | A server-side timeout and a Stop / cancel endpoint (AN2). |
| 7-QA3 N3 (client half fixed in 7-QA3-N3, confirmed by QA4: opening Demo — Sales Overview in Edit left revision 39 unchanged) | Re-checked in QA3: still open at the root. QA2 only grouped the burst in the history ("39 changes"). Opening a page with no layout mode in Edit still runs the automatic packing, which sends one `updateWidget` per widget in parallel (`persistWidgetLayouts`), so the server snapshots a version per widget. `VERSIONS_KEPT = 50` (`routers/reports.py`), so one such open can push most of the older history out. | One version per user action: a batch layout endpoint (or coalescing saves seconds apart), an atomic revision increment, and retention that counts actions rather than rows. |
| 7-QA4 E1 | A display rule whose operator does not fit its column ("date > 0") fails on the server with Python's own message, `'>' not supported between instances of 'str' and 'int'` | The client now picks a fitting default, offers only operators that fit the column's type, and shows a short translated message (server text as detail). The server should validate rule types when a rule is saved and answer with a code, not a Python exception. |
| 7-QA4 T5 (with T12) | "Is this difference real?" sends English prose | Shown as sent, `dir="auto"`: `summary`, `tests[].business.sentence`, error `detail`s. Composed by the client in Arabic from the numbers: `tests[].sentence`. Matched by pattern (breaks quietly if the wording changes): the three `caveats[]`. Should be codes: `tests[].question`, `tests[].effect_label`, `tests[].test`. Source: `app/services/analysis/inferential.py`. |
| 8-i18n | The platform settings catalog (GET /platform/settings), the connector catalog's labels, boundary-pack descriptions/source/licence, the Activity `entity` text ("report #386") and model notes/warnings are English prose from the server | The client now translates the settings catalog BY KEY (12 categories, 75 labels, 23 help texts) and the 101 audit action codes, falling back to the server's English for anything unknown; a reworded server label keeps the old translation. The server should send stable codes/keys and parameters, not prose. |
| 7-QA5 L6/L7 | Custom-connector field labels (from `services/connectors.py`), select option values (TLS modes, auth, method), connector type names and categories, and the boundary-pack manifest (names, descriptions, licences, source citations) are English from the server | The client translates known connector field keys and the 5 manifest packs by id (with the server's English as fallback; a pack description/licence only while the server's English is unchanged). The server should send keys or Arabic text. |
| 7-QA5 (AI) | Every model endpoint timed out during QA5 (ConnectTimeout) | Not a frontend item: from this machine (now on 10.140.x) the three model servers 10.125.18.37:8014/8015 and 10.125.18.189:8000 do not answer even from inside the backend container -- a network/VPN reachability issue. Related to B6/AN2 (no timeout or Stop in Ask AI). |
| 7-QA3-N3 (after the client fix) | Opening no longer writes. A layout edit still costs one version per widget it stores: the first edit of an old 4-widget page added 5 (the page + 4 widgets), its undo 5 more. | Still needed: a batch layout endpoint (one version per action), an atomic revision, and a way to clear `layout_mode` (PATCH drops a null, so undo writes `''`). The 50-version cap stays. |
| 7-QA2 N3 | One automatic layout pass (Executive packing when a page is first edited) left 39 versions in half a second, with repeated revision numbers; the burst can also push older versions past the retention window | Every widget save snapshots a version and the revision is read-then-bumped without a lock. Needs one version per user action (a batch layout endpoint, or coalescing saves seconds apart) and an atomic revision increment. The history now shows such a burst as one entry. |
| 7-QA2 T12 (seen again in QA3) | Insights narrative, finding titles and details are English in the Arabic UI | The insights endpoint takes no language; the engine writes English. Needs the UI language on the request (AP3). The pane's own words are translated. |
| 7-QA B6 | Ask AI is slow (about 70 s for a simple answer, about 4 min before a clarification), with no timeout or cancel | Needs a server-side timeout and a cancel endpoint (AN2: stream progress + cancel). |

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

### 3b Dataset detail shell + Overview + tab map — `de71f78`

**Changed:** new tab set (Overview, Columns, Data, Analysis, Rules & alerts,
Models, Aggregates) with counts; old `?tab=` keys redirect and the URL is
rewritten. Header restyled (pills, meta line, ⋯ menu, primary Build a
dashboard; connection refresh controls unchanged). New
`pages/datasetDetail/Overview.tsx`: facts, trust checks, columns at a glance,
Used by, lineage, insights, admin-only Recent activity, first-run steps, and
profiling / error / empty states. The former Overview sections moved, unchanged,
to Analysis (insights, influencers, associations, segment, anomalies), Columns
(column profile) and Rules & alerts (quality rules box); 3c restyles them.

**Deviations from the boards:**
- No automatic profile on a normal visit: the existing code deliberately scans only right after an import, so Columns at a glance offers "Profile the columns" when no profile is saved. The profiling skeleton says "Profiling 13 columns…" without a done-count: the endpoint reports no progress.
- Checks line: "View checks" opens Rules & alerts instead of "View 3 rows": the try call returns counts, not rows.
- Insights card: generates on demand and links to the full list on the Analysis tab ("Open in Analysis"); there is no stored "last week" scan to summarise without running one.
- Recent activity shows upload, label change and share events only, per the handoff; the general log's 200 rows are org-wide, so a quiet dataset can show none.
- Models tab shows no count: it would need an extra request on every visit.
- The ⋯ menu holds Certify (admins), Edit query (admins, builder datasets) and Run analysis.

**Environment note (2026-10-06):** the machine rebooted mid-step and the data
drive came back as `/media/saeed/New Volume1`. Docker left an empty, root-owned
`/media/saeed/New Volume/projects/...` skeleton behind; removing it needs sudo.

### 3c Remaining tabs + Share dialog — `0f217fc`, `230ab1f`, `14ddd5b`, `b8df925`, `0e6da8d`, `af2460a`

Committed in parts (Columns/Data/Analysis, Rules & alerts, Models/Aggregates,
Share + translations, fixes) after the 2026-10-06 reboot, each after the full
suite and build; the screen comparison ran once over all of 3c before ticking.

**Changed:**
- Columns: `ColumnMeaningPanel` is the tab's table (meaning, distribution, empty %, summary, Use as pill opening role / summary / worth explaining / may be suggested / hidden). Type filter, search, "n of m described", "Hidden columns (n)". v1's per-column statistics stay folded under "Detailed statistics". Profile helpers shared with the Overview (`columnProfile.tsx`); values bidi-isolated.
- Data: v1's left panel became a toolbar (Filter with chips, sort, Row filter, ƒx Column, Group & bin, Measures, Steps), each opening its unchanged panel. Type tags in headers, row numbers, "(filtered from N)". BUG-037's narrow-screen rule retired with the side column it fixed.
- Analysis: question list over the registry ("All 19 analyses"); built-in questions open key influencers, segments, patterns, insights, anomalies; the rest open `StatisticsPanel` limited by a new `only` prop. Deep links pick their question.
- Rules & alerts: Quality rules card (state, result after Run now, Warn/Block pill, + Rule), the one-off quality report folded under it, Alerts restyled, new Freshness card.
- Models: train card, model cards with fit bar and plain words, changed-since-training warning, facts grid from the model card, "Also tried".
- Aggregates: table of aggregates (locked RLS columns, status, Edit / Rebuild), the "dashboards don't switch" note, New aggregate form.
- Share dialog: Person / Role / Org unit switch, Shared directly, static "Can also open it" (dashboards counted from lineage), row-security note.
- All new copy in `en.ts` and `ar.ts`.

**Deviations from the boards:**
- Automatic analyses (segments, patterns, key influencers) now start when the Analysis tab is first opened instead of on every visit to any tab: on the single-process dev server they held up the open tab's requests (Rules & alerts waited seconds for its edit permission). They still run without a click.
- Analysis list adds "What stands out?" (insights) and "What looks unusual?" (anomalies): v1 features the board's list omits.
- Columns: no highlighted row for a column whose check fails (that needs the checks "try" call on every visit; the Overview already shows it).
- Data: no "Download CSV" (no dataset export endpoint: backend work) and no "n of m columns" picker (no such feature exists). Cell values keep v1's raw text, not currency formats. "Edit cells" stays above the table.
- Rules: a rule row shows the check in words plus its kind; checks have no names. "New alert" keeps its v1 label (tests and other screens use it) rather than "+ Alert".
- Models: no "Retrain" button (training again under the same name already makes the next version; the warning says so); facts show "—" where an older model card did not record them; the note does not claim "4 approaches / 20%".
- Aggregates: no "Used by" column (would need lineage per aggregate).
- Share: the picker is a select, not a type-ahead; each grant's level is shown as text (there is no endpoint to change it in place); no "2 rules apply" count (N9).
- Captures of Rules & alerts and Aggregates used browser-only sample data: the dev database has no saved checks or aggregates.
- Two flaky 3a tests fixed (per-call timestamps, ambiguous table query). `Lineage.test.tsx` is still flaky; scheduled for FINAL.

### 4a Ask AI layout, column panel, answer card — `fc9a935`

**Changed:**
- Scoped page is History | thread | Columns, edge to edge (cancels the shell padding the way the report builder does). A scope bar names the dataset with its kind and size ("Uploaded file · 2,000 rows · 13 columns") around v1's compact picker.
- History: "Conversations" with New chat beside it, a title search, Today / Earlier. Still lists only the current scope's threads (as v1). Delete now uses the app's confirm dialog instead of `window.confirm`.
- Columns panel (new): Groups / Numbers / Dates / Other with value counts or ranges from the saved profile; id columns go to Other as "identifier"; a click puts the column name into the question. Folds to a rail (remembered); a drawer with a Columns button under 1100px.
- Answer card (page only; the report builder's copilot keeps v1's rendering): header with dataset and run time, key numbers (highest, lowest, gap, rows back), the sentence with traced numbers dotted-underlined, the chart alone, Rows beside "How it was worked out" (plan, queries and repairs, rows back, numbers traced), Show SQL, Copy, Add to dashboard, one Export menu, a "⋯" menu keeping Retry / Copy SQL / Save as dataset, 👍/👎, then "Ask next" with two unused starter questions. Older answers are compact (sentence, chart, actions).
- After 👎 the card asks "What was wrong?"; the reply goes to the existing feedback endpoint's `comment` field (the client call gained an optional `comment`; the endpoint already accepted it).
- The thread scrolls to the start of the latest turn, not its last line (the card is taller than a screen).
- `ResultView` gained an optional `rows="none"` (chart without its rows toggle) and `chartFormatFor`; defaults unchanged.

**Deviations from the boards:**
- Key number "Rows read 3,612 → 4 groups" is "Rows back 4": the run stores rows returned, not rows read (backend). Same for the source line, which keeps v1's wording, and the "Ran it" step.
- Chart: (fixed in 4b) the top bar is now in the accent and the rest grey, through the bar renderer's existing per-row fills; the renderer itself is unchanged.
- Rows table keeps the shared grid (raw column names, "4 rows" footer) rather than the board's friendly-name-over-raw-name header.
- Composer keeps v1's hint line under the box; no dataset chip inside the composer (the scope bar above already shows and switches it).
- History items show the time, not the dataset name (the list is per dataset, as before).
- Captures used browser-only sample conversation data (a stored answer for "average margin_pct by region" on Demo — Sales); no live model call.

### 4b Ask AI states — `69f5454`

**Changed:**
- No dataset chosen: the same three columns. History lists every thread with what it asks about; picking one opens it in its scope. The chooser has a search, "Recently asked about" (from the conversations' targets, with counts), all datasets and connections. The composer is locked with "Choose data above to start asking". v1's certified/test-looking filter stays under the lists. v1's hero and illustration are gone.
- First run: eyebrow (name · rows), "Ask <dataset> anything", intro, four starters, three how-it-works tiles. History says "Your conversations about this dataset will appear here." The composer placeholder names the dataset.
- Thinking: three-dot pulse, "Working on your answer · 6 s", skeleton, "Usually 5–20 s…". v1's timer-driven checklist is removed (for both mounts, per the handoff); the long-wait notes stay, now translated. A new question folds the previous answer to compact.
- Clarification: rendered question; option cards for columns the reply puts in bold, code or quotes that match the dataset's columns ("Use region · A column in Demo — Sales · 4 values"), then the server's own choices; "Or type your answer…". Picking sends the reply through the normal ask. Once answered, the card folds to "Needs one detail · You chose …" and the reply isn't repeated as a bubble.
- AI offline: `llmApi.endpoints` now also broadcasts each answer (a window event plus the latest value; path, params and type unchanged). The page reads the top bar's poll with `choiceLight(...) === 'down'`, so there's no second poller. Banner above the composer: "new questions are paused", what still works, "Checked N s ago", plus links "Explore <dataset> without AI" (Data tab) and "Build a chart yourself" (/reports?new=1). Composer locked. The builder mount never locks.
- Error: title, v1's hint, a visible "Try instead" with starters, Try again (primary) and Edit question (puts the question back in the box), Technical details open and `dir="ltr"`.
- Profile is read once by the page and shared by the columns panel and the clarification options.
- Localized: the pending texts, "Could not reach the agent", "Could not load this conversation", the result caption and "No rows.", "Tables considered", the Save-as-dataset prompts and toasts, copy/download toasts, the aria-labels (Copy SQL, Download CSV/Excel/PDF, Good/Bad answer, Save as dataset, Ways to continue), "Saving…".

**Deviations from the boards:**
- Connections show their type ("SQLite · asks across tables") rather than "4 tables": the connections list has no table count.
- Error text keeps v1's hint ("Try rephrasing with a column name…") instead of a sentence naming the number of tries: the failed run doesn't say how many repairs it made.
- The clarification option sends "Use <column>"; the resolved line says "You chose Use region" (the board's "Group by faculty" wording isn't derivable from the reply).
- Columns are inserted into the composer as plain text, not as a styled token (the composer is a plain textarea).
- Compact older answers keep v1's "Show rows (n)" toggle under the chart.
- Captures used browser-only sample data (conversations, the stored answer, a never-answering ask for Thinking, a "down" `/llm/endpoints` for Offline).

**Clean-up for FINAL:** `pages/ask/AskIllustration.tsx` and the `.dl-ask--hero` / `.dl-ask__hero*` CSS are now unused.

### 4-revert Ask AI back to v1 with fixes; Datasets menus — `7b50e5c`, `8818373`, and the commit that adds this entry

**Owner's decision:** no 4a/4b visual redesign. Ask AI looks like v1 (`120e0ef`); the step 4 boards are no longer its spec.

**Reverted to v1:** the three-column layout and edge-to-edge page, the columns panel, the answer card (key numbers, "How it was worked out", Export/⋯ menus, "Ask next", compact older answers, dotted underlines, highlighted top bar), the no-dataset chooser (v1's hero and Step 1 picker are back), the first-run cards (v1's chips are back), the clarification and error cards, the conversation search, the dataset size beside the picker, the placeholder naming the dataset, and scroll-to-start (v1 scrolls to the bottom). Removed files: `AnswerCard.tsx` (+test, css), `pageStates.tsx`, `ColumnPanel.tsx`, `DataChooser.tsx`; their unused strings were pruned from `en.ts`/`ar.ts`.

**Kept, in v1's look:**
- Translations of the chat's hardcoded English (pending texts, load/reach errors, result caption, "No rows.", "Tables considered", Save-as-dataset prompts and toasts, copy/download toasts, aria-labels, "Saving…").
- Pending without the timer-driven stages: v1's dot, counter, skeleton and long-wait note.
- Themed delete dialog instead of `window.confirm`.
- Offline: read from the top bar's `/llm/endpoints` poll (broadcast by `llmApi.endpoints`, no second poller). While the model is down, v1's question box is locked ("New questions are paused while the model server is unreachable") with one line above it in v1's error-text style. No banner. The builder mount never locks.
- Clarification: "Use <column>" chips for the columns the reply names in bold, code or quotes, beside the server's choices, in v1's chip style (`clarifyColumns.ts`).
- "What was wrong?" after 👎: a small v1-style field under the actions; the reply goes to the feedback endpoint's `comment`.
- Edit question beside Retry on an error, in v1's button style.
- `agentApi.feedback` keeps its optional `comment`.

**Datasets menus (owner asked to check every dropdown/menu on the redesigned Datasets screens):**
- `7b50e5c`: the list's row menu was clipped by the table card (only the Suggest dashboards sparkle showed in English, nothing in Arabic). It now opens on the page (`portal`, `align="end"`).
- `8818373`: ActionMenu counts its 4px gap when deciding to open upward; the last row's menu was cut by the window edge.
- This commit: the header's refresh options popup (connection-imported datasets) ran under the side nav when the header wrapped at narrower widths. It now flips to the button's start edge when it would leave the content area.
- Checked in a browser, English and Arabic, at 1440px and 900px: every popup trigger on the list, the detail header ⋯ on all seven tabs, the live dataset, the Share dialog (selects only), and the refresh popup (on a dataset presented as imported, since none is seeded). After the fixes no popup is clipped, covered or off-screen. Expanding controls (Use as, + Rule, model cards, Data toolbar panels) open in place; native selects can't be clipped.

**Captures:** Ask AI in eight states × four themes, v1 (`120e0ef` files restored temporarily) beside the current page, with the same browser-only sample data. They match, apart from the kept items above.


### 7-gap Gap pass for Home and Dashboards Parts 1–4 — no code change

Compared the served prototype (`design-handoff-2/prototype/`, desktop frames) with the
current app and backend, screen by screen: Home, Dashboards list (Part 1), Builder
(Part 2), View & Present (Part 3), Share / Export / Version history (Part 4). Each
element was classed as in v1, backend data exists (frontend only), or needs new
backend work; the last group is in "Backend follow-ups". Also listed the sidebar and
top bar differences (S1–S7, T1–T6) and the states the prototype doesn't draw (error
for Home and the list, AI offline for the Home ask box and the View AI panel, Builder
load error / conflict / empty / read-only, shared and embedded viewers, Part 4
errors). The owner's decisions are in the note above the 7a–7e list.

**Findings worth keeping in mind:**
- v1's rail already has foldable group headers; the prototype just shows the chevron
  on open groups too. Kept as v1.
- Offline detection reads the LLM picker's poll, so the picker must stay for the
  AI-offline states to work.
- The prototype shows Edit and Present beside "View only"; v1 hides them for viewers
  (kept).
- Present in v1 exits on any key; the new controls use arrow keys, so Esc becomes the
  exit (7d).

### 7a Home — `3ed767f`

**Changed:**
- `pages/Home.tsx` rebuilt from the approved prototype (`home.html`), split into `pages/home/` (`parts.tsx`, `DashboardsSection.tsx`, `DatasetsSection.tsx`, `AdminCards.tsx`, `Thumb.tsx`, `feeds.ts`, `home.css`).
- Hero:
  - date, "Good morning/afternoon/evening, <name>" (the email's local part, as the top bar shows it), the question box with the mascot.
  - Submitting goes to `/ask?q=…`. Ask AI reads `q` once and drops it from the URL. While no data is chosen it shows "Choose the data to ask this about: “…”". The first chat that opens gets it in its box, unsent (new optional `initialInput` on ChatPane).
- Starters: built from the newest dataset Ask AI can answer from, with `datasetSuggestions` from its columns. Each opens `/ask?dataset=<id>&q=…`.
- Tiles:
  - Dashboards (count, "N published").
  - Datasets (count, rows of stored datasets).
  - Connections (count, their types).
  - Last refresh (newest `last_refreshed_at`). Its second line is "N of M jobs failed" over the last 24 h of refresh runs for org admins, and the lineage graph's failing count for everyone else.
  - A tile whose call fails says so, with Retry.
- Quick actions: New dashboard (`/reports?new=1`), Upload, New connection, Ask AI (focuses the box; goes to `/ask` while the box is locked).
- Continue where you left off: `/reports/recent` (4), with schematic thumbnails drawn from each dashboard's first page (one box per widget at its grid place, a glyph per kind).
- Dashboards section:
  - Six shown, All / Mine, Recent / Name, grid / list (remembered).
  - Draft / Published badges, "View only" for viewers.
  - Hover: Open, Share (author or admin, the list page's ShareDialog), ⋯ Rename / Delete (editors), Copy link, Export as PDF (the server applies the export policy).
- Datasets section:
  - The five most recently changed, with source icon and words (`classify.ts`), rows × columns ("N columns · live" for DirectQuery), last refreshed, and freshness (Fresh / Stale / Refresh failed / Uploaded / Live).
  - Actions: Preview (a drawer with the Datasets list's preview panel), Build dashboard, Ask AI (only for datasets Ask AI can answer from).
- Org admins only:
  - Recent activity: the audit-log actions that make a sentence (upload, create, publish, unpublish, share, release, restore, refresh, delete; 5 shown).
  - Refresh & jobs: last 24 h counts; failures, then running, then the latest success; Retry on a failed dataset refresh.
  - Neither endpoint is called for anyone else, and both cards are absent for them.
- First run:
  - The setup steps replace the quick actions while there are no datasets or no dashboards. Progress is counted from datasets, dashboards and Ask AI conversations.
  - The question box is locked with "Connect data first to ask questions".
- Loading skeletons for every section.
- Failure is per section. Only the reports or datasets list failing blanks the page (v1's LoadError, never an empty workspace).
- AI offline (the top bar's poll via `useAiOffline`): the box is locked ("The AI is offline right now" plus v1's one line "New questions are paused…"), the mascot greys out, and the starters hide. The rest of Home works.
- All new copy is in `en.ts` / `ar.ts`. Names are bidi-isolated. The Arabic activity lines use the passive ("تم نشر … بواسطة …") so they don't guess anyone's gender.
- New capture script `e2e/capture/redesign/cap_step7a.mjs` (8 states × 4 themes).

**Deviations from the prototype:**
- Left out (backend, listed in "Backend follow-ups"): favourites (the star and the Favorites filter), owner avatars, "Shared with me", Duplicate, connection health ("All healthy"), recently opened datasets in Continue, comment/refresh-failure/"shared with Finance" activity, running %.
- The starters say which dataset they are about ("Try with <dataset>"): they are built from that dataset's columns and open Ask AI scoped to it. The prototype's chips name no data.
- Connections tile shows the connection types instead of "All healthy".
- The jobs list shows "Running · started N ago", not a progress bar.
- Continue's empty text says "Dashboards you open…" (datasets are not tracked).
- Activity names are email local parts ("sara"), not full names; there is no name field.
- Whole-page error keeps v1's LoadError card; the prototype has no error state.

**From v1 Home:**
- Dropped (the design replaces them): the collapsible sections, the plain "Home" title (the greeting replaces it), and "my dashboards first, else all" (now the All / Mine filter).
- Kept: "View only", the live dataset's "N columns · live", the opening loader.
- Tests: "no create buttons in the header" and "sections collapse" were removed (the design reverses both). The others were adapted, and new ones cover the hand-off to Ask AI, starters, offline lock, tiles, admin-only calls, per-section errors and first run.

**Checks:** Home tests 25, AskAI and ChatPane additions, full suite 278 files / 3701 tests, build, containers rebuilt. Captures in light, dark, Arabic, Arabic dark for full, sample, first run, loading, error, offline, member and section errors were compared with the prototype at 1440 wide. The menu, preview drawer, question hand-off and starter were checked in the browser with no page errors.
- Captures other than `full` used browser-only data: the dev database has no refresh runs and few audit rows.

**Note for 7b:** the reused `ShareDialog` (`pages/reports/listParts.tsx`) still has hardcoded English. It is unchanged here; 7b restyles that list.

### 7b Dashboards list — `c55d50a`

**Changed:**
- `pages/Reports.tsx` rebuilt from the approved prototype (`dashlist.html`), edge to edge like the builder (`dl-bleed`), with `pages/reports/` `FolderNav.tsx`, `DashCard.tsx` (card and row), `dialogs.tsx` (New dashboard, Move to folder), `model.ts` and `dashboards.css` (classes prefixed `dsh-` so nothing collides with the app's own `.dl-tree` / `.dl-seg` / `.dl-empty`).
- Side column:
  - Views: All dashboards, Recent (`/reports/recent`, 50, in the order opened), Shared with me (the workspace tree's `shared_with_me`: a folder grant or a grant naming the viewer, never merely "not mine").
  - Folders: every folder of the tree, nested, with the dashboards beneath each. Each is a drop target. A menu on the ones the viewer may manage offers New subfolder, Rename, Delete.
  - Inline New folder.
  - The drag hint.
  - "Folders couldn't load · Retry" when the tree fails.
- Toolbar:
  - Search over names, descriptions and dataset names (the shared `useListFilter`, restyled; shown from 8 dashboards, as on the Datasets list). `/` focuses it.
  - All / Drafts / Published with counts, a Dataset filter, Sort (Recently modified / Name A–Z), grid / list (remembered).
- Grouping: the All view, with nothing narrowing it, shows a section per folder (subfolders inside, collapsible, remembered), then "Not in a folder". A view, a search or a facet shows a flat grid with a count. A folder view shows its own dashboards, then its subfolders.
- Card: schematic thumbnail, tick box (editors), "View only" chip, hover Open / Share (author or admin) / ⋯. Name, description or page count, Draft / Published / AI suggestion badge, modified time, dataset chip (v1's rule: hidden when the name already says it).
  - ⋯: Open, Share…, Copy link, Move to folder…, Rename, Publish / Unpublish, Export as PDF, Delete, each behind the same rule as v1.
- List view: a table with folder, dataset, status and modified, with group rows.
- Bulk bar (once anything is ticked; a click on a card then ticks it): Move to…, Export (one PDF each), Delete (the shared confirmation naming them), "Select N that look like test data", clear.
- New dashboard dialog:
  - Blank: name, dataset, folder. With no dataset it opens the builder asking for data and is marked fresh, as v1.
  - Template: the four built-in page templates, drawn from their real layouts. The template page is added and the empty default page removed.
  - With AI: a goal and a dataset, handed to the existing Suggest dashboards dialog (new optional `initialGoal`).
  - `?new=1` (palette, Home) opens it.
- Move to folder dialog, with v1's warning about who can then open it. A drop is confirmed with the same words. The server's refusal is shown as given.
- States: loading skeleton, first run (three ways to start), no match (what was searched, Clear search, Build it with AI, recent dashboards), filters with no result, empty Recent / Shared, empty folder ("New dashboard here"), whole-list error (v1's LoadError, header kept), folders failed. A failed datasets call hides only the chips and the filter.
- The share dialog's hardcoded English is translated (`dsh.sd.*`).
- New capture script `e2e/capture/redesign/cap_step7b.mjs` (15 states × 4 themes).

**Deviations from the prototype:**
- Left out (backend, see "Backend follow-ups"): favourites (star, Favorites view), owner avatars and the Owner column, view counts and Most viewed, Duplicate, a "Shared" status, "Suggested by AI" proposals with Keep / Dismiss (dashboards made by Suggest dashboards wear an "AI suggestion" badge instead, without a section of their own), Open in edit mode, Request edit access, bulk Share, undo after delete or move.
- "Shared with me" is built after all: the tree marks granted dashboards. The 7-gap follow-up row was narrowed to the "Shared" status.
- Moves are confirmed (v1), not done at once with an undo toast. Deletes are confirmed (v1); there is no restore endpoint for an undo.
- The New dashboard dialog's templates are the four built-in page templates, not the prototype's invented "Sales / KPI scorecard / Operations". With AI proposes several drafts through Suggest dashboards rather than creating one.
- The search box appears from 8 dashboards (v1's and the Datasets list's rule).
- The tablet "Folder:" dropdown is not built (desktop only).

**From v1:**
- Kept: subfolders, folder rename and delete with "contents move up", move confirmation, Publish / Unpublish, delete confirmation, the dataset chip rule, Suggest dashboards' goal text, the fresh-report marker, `?new=1`, the opening loader, "Select test dashboards".
- Replaced: the "My dashboards / Granted to me" grouping (the Shared with me view), the Sections / Folders toggle and the breadcrumb drill-down (the side column), and the separate Select mode (tick boxes on hover).
- Tests: `Reports.test.tsx` rewritten around the new page. `loadFailures.test.tsx` expects the new first-run title. (The GATE C report said the old file had 75 tests; it had 71. See the audit below.)

**Checks:** Dashboards tests 47, load failures and list wiring, full suite 278 files / 3677 tests, build, containers rebuilt.
- The template flow was checked against the real API (create, add template, delete the default page, then the probe was deleted).
- Captures in light, dark, Arabic and Arabic dark for grid, card menu, list, folder, bulk, no match, New dashboard (blank and template), new folder, move, first run, empty folder, loading, error and member were compared with the prototype at 1440 × 900. Fixed during the comparison: list column widths, an English name clipped at its start in the Arabic list, a second focus ring on the search box, and zero counts shown while loading or after an error.
- Captures for empty folder, first run, loading, error and member used browser-only data. They are copied to `/media/saeed/New Volume1/projects/redesign-captures/7b/`, with 7a's in `…/7a/`.

**GATE C audit of the old tests (2026-10-06, owner's request):** each of the old file's 71 tests was mapped to a new test or dropped because it pinned the replaced layout only.
- Dropped (layout replaced):
  - The My workspaces / Granted grouping (6 tests: split by authorship, plain grid ×2, each dashboard under its own heading, empty folder under the viewer's own group only, folder inside its authorship group).
  - Collapsing a whole group.
  - "One full-width column, no workspace tree" (the design adds the side column).
  - "Loose dashboards before the first folder heading" (now a last "Not in a folder" section).
  - The folder drill-down view (3 tests: breadcrumb, the remembered Sections / Folders choice, a new folder inside the viewed folder; subfolders are made from the folder's menu).
  - "New dashboard opens the builder at once" (now the dialog; covered by the Blank test).
  - "The heading gets its whole row" (the new header holds the count and menu beside it; wrapping is still pinned).
- Re-pinned in `Reports.test.tsx` ("kept from v1"), 19 tests where the behaviour stays but had lost its test:
  - Select mode doesn't open the dashboard.
  - Exactly one Delete.
  - A granted-but-editable dashboard keeps its design controls.
  - Someone else's dashboard has no Publish.
  - Removing a grant.
  - A control click doesn't open the dashboard.
  - Controls are reachable and named.
  - The stretched title link (the whole card opens it).
  - Controls show on hover and focus and are never hidden on touch.
  - Two-line clamp with the full name on the link.
  - Folder headings wrap.
  - A hand-written description is left alone and the API value is never rewritten.
  - No dataset says nothing.
  - Heading counts (subtree, and zero).
  - Expanding again.
  - No folder headings while searching.
  - The tree is re-read after a new folder.
  - An unchanged rename sends nothing.
  - A drop on "Not in a folder" moves to the top level.
- Two behaviours had been lost along with their tests, and are restored in `dashboards.css`:
  - On a touch screen (no hover) the card and row controls and the folder menus are now always shown.
  - Folder headings wrap instead of truncating.
- Totals: `Reports.test.tsx` 66 tests; full suite 278 files / 3696 tests; build passes.

### 7c Share, Export, Version history — `71537f9`

**Changed:**
- New `components/report/share/`:
  - `ShareDashboardDialog.tsx`, used by the builder's header, the Dashboards list and Home.
  - `ShareSections.tsx`: v1's guest links and embedding, translated and restyled.
  - `ExportDialog.tsx`.
  - `share.css`.
  - Replaced `ShareLinksDialog.tsx`, `PdfOptionsDialog.tsx` and the list's `ShareDialog`. Their tests were carried over (`ShareSections.test.tsx`; the PDF-options behaviour is pinned in `ExportDialog.test.tsx`).
- Share, People tab:
  - Invite by email at Can view / Can edit / Can edit + data.
  - The owner row; each person's level as a select (re-sending a grant changes it); remove.
  - General access, Restricted or Everyone in your organisation: the publish flag, with the publish gate's message on refusal.
  - The link to this page.
  - "Anyone with a guest link": v1's model (1 / 7 / 30 / 90 days, pin layout, URL shown once, list with views, revoke with the confirmation). It is greyed with the server's reason when `share_link` is refused.
  - Only the author or an admin manages people and access; others are told so. A legacy dashboard says it has no individual sharing.
- Share, Embed tab: v1's host-signed embed configs (secret once, iframe / Python / Node samples, enable / disable / delete).
- Share, Schedule tab: v1's SchedulePanel.
- Share, footer: Your access, and why · Access by role (admins).
- A viewer without edit rights has no Share button (v1 gating); "View only · why?" stays.
- Export:
  - PDF: A4 / Letter / A3, landscape / portrait, contents page, pages; zero pages blocked.
  - Data (Excel, one sheet per chart, says what was withheld).
  - Offline package, and Print (the print view).
  - A schematic preview of the first chosen page.
  - States: preparing (spinner), file ready, error (the server's reason, read from the Blob, plus Try again).
  - The export policy greys every download with its reason; Print stays.
- Version history:
  - Grouped Today / Yesterday / Earlier, with the current marker, author, copilot note, and page / widget counts.
  - Selecting a version offers Restore; there is none on the current version.
  - Restore asks through the app's confirmation instead of `window.confirm`, with "saved as a new version first, viewers see it straight away, name and sharing unchanged" and v1's missing-dependency warning.
- All strings in `en.ts` / `ar.ts`; the embed and guest-link copy is now translated.

**Deviations from the prototype:**
- Left out (backend, see follow-ups):
  - Can comment, user suggestions, groups, pending invitations, Resend, invitation email and message, Transfer ownership.
  - A never-expiring link, a link carrying the current filters, embed display options (tabs / filters / Ask AI / theme / size).
  - Schedule on/off, Pause, Edit; multi-day picker; PNG format; pages selector; AI summary.
  - PowerPoint, page PNG, CSV zip, choosing widgets, filter summary / page numbers / AI appendix, "uses current filters", live preview, background export, step progress, 24 h download link, "export without it".
  - Named versions, the Named-only filter, preview and compare, per-version change summaries, Make a copy, version PDF.
- General access is a two-card choice, not a dropdown menu (two options).
- The Schedule tab keeps v1's form (its fields differ from the prototype's and are all real).
- Export preview is a schematic of the page (as in the prototype), not a rendered PDF.

### 7d View and Present — `65fe98a`

**Changed:**
- Header:
  - A ⋮ More menu in both modes, just before the mode button so that button never moves (v1's rule, pinned by a test). Items: Print, Version history and Report settings (editors; from reading they switch to edit mode), Your access, and why, and Access by role.
  - Share and Export are buttons opening the 7c dialogs.
- Widget hover toolbar (reading only): Ask AI about this widget, and Focus. It straddles the card's top edge so the widget's own controls (cross-filter arrows, ⋮) stay as they are. It is always shown on touch screens.
- Focus: the widget full screen, rendered by the same WidgetRenderer, with three questions to ask about it.
- AI panel (reading and Present), opened by the Ask AI button on the canvas or Ctrl+/:
  - Ask: ChatPane on the dashboard's datasets, one thread per dashboard, locked with one line while the model server is unreachable. Starters come from the columns, and "Ask AI about this widget" puts a question in the box, unsent.
  - Insights: InsightsPane; it works offline.
  - Suggest: SuggestionsPane, editors only.
  - Viewers get Ask and Insights, with nothing that adds to the page. InsightsPane's `onAdd` became optional for that.
- Present:
  - The header, the editor's page bar, the Filters line and the status bar are hidden (S7). Title and page name sit at the top, keyboard hints top-right.
  - Bottom controls: previous / next, counter, dots, Auto-play (15 s with a progress line; starts OFF since GATE D, `4cec1e5`, the reader turns it on), Ask AI, Exit (Esc).
  - Arrows, Space and Page Up / Down page through (mirrored in Arabic). Esc closes the AI panel, then exits.
  - The controls fade after 2.5 s idle.
  - v1 exited on any key, which made the arrows useless; that is replaced.
- Present stays editors-only (v1 gating). View-only readers keep "View only · why?".
- New `e2e/capture/redesign/cap_step7c.mjs` and `cap_step7d.mjs`.

**Deviations from the prototype:**
- Left out (backend):
  - A reader's "Bookmark this view" (bookmarks need edit rights).
  - Widget-aware AI ("Reading 12 widgets", "N widgets read", "Based on" chips, page-specific questions).
  - Insights "Generated N ago" and saved dismissals.
  - Author-defined default filter chips.
- Left out (would touch WidgetRenderer or its query):
  - "Data behind this chart" in Focus.
  - Drill down and Copy image in the hover menu. The widget's own ⋮ menu keeps v1's export, View as and analyses, and Focus says so.
- Subscribe stays its own header button (v1 component); the prototype lists it under More.
- The Present stage is not scaled, and does not need to be (checked at GATE D): the canvas is a fluid 12-column grid, so it already fills the screen width, with a 24 px margin, at 1280 and 1920.
- Present title, controls and hints follow the prototype. The Ask AI panel in Present is the same panel as in reading.

**Seen while capturing, not changed (existing code):**
- Present renders every widget eagerly, which surfaces two v1 console messages: a React key warning from `CustomGraphRenderer` (chart renderers stay untouched) and the sandboxed Live embed widget's localStorage error.
- The v1 Suggestions pane proposes "average year by category", whose preview the server refuses (422); it does the same in edit mode.

**Checks:**
- Builder tests 138 (Present now exits by its controls and by Esc, not any key; reading, focus, the AI panel, Ctrl+/, a viewer's panel, Present paging and auto-play are pinned).
- Share 12, Export 5, guest links / embed 10, version history 8.
- Full suite 279 files / 3720 tests; the only failure was the known flaky `Lineage.test.tsx`, which passes alone.
- The build passes.
- Captures for 7c and 7d in light, dark, Arabic and Arabic dark were compared with the prototype. Fixed during the comparison: the Present stage padding, editor chrome showing in Present, and a doubled name in the AI panel's context line.
- Fixed before commit: the Focus view had been mounted outside the cross-filter provider, which would have crashed it.
- Captures used browser-only data for grants, guest links, versions, export responses, an unreachable model and a view-only reader. They are copied to `/media/saeed/New Volume1/projects/redesign-captures/7c/` and `…/7d/`.

### 7-QA Fixes from the QA report — `a18e0ab` and the commit that adds this entry

**Broken:**
- B1 Datasets list: the page is a size container. Below 1100 px of page, the preview stacks under the table, and the table keeps a minimum width and scrolls sideways before the Name column collapses.
- B2 Ask AI: a dataset opened by link (`?dataset=`) shows in the picker even when it looks like test data.
- B3 Clarification chips also come from plain column words in the reply ("margin" → `margin_pct`), not only quoted names. Limit: a reply that names no column still has no chips (AN1, backend).
- B5 Data tab: a sequence number per preview load, so an older answer never overwrites a newer one. Not reproduced live; this is the race that matches the report.
- B7 Home row total counts every dataset (the live one was left out). Overview "Used by" lists "+N more" past 8. The folder tree reloads after a single or bulk delete. The stale folder count itself was not reproduced.
- B8 Not reproduced: fresh loads, rail navigation, and a backend slowed to 4 s per call; typing was never lost and the first chip click always worked. No change.

**Visual:**
- V1 Dashboards list: the small columns have fixed widths, so the name takes what is left. Below 960 px of table, the Folder column collapses (it is not removed, so the colSpan-7 group rows still fit) and the folder shows under the name. Below 720 px the table scrolls sideways. The spans that clip carry `dir="auto"`, so text loses its end, not its start, in Arabic. At 1440, 0 of 11 names are clipped.
- V2 Bulk bar: "1 dashboard selected", "Also select the one that looks like test data". Labels never wrap; the bar wraps instead.
- V3 Search: the browser's own clear button is hidden; "1 result"; a shorter placeholder. Typed text gets `dir="auto"` in the shared ListFilter, and the no-match title puts the query in a `<bdi>`.
- V4 Breadcrumb (CSS only, `index.css`; TopBar.tsx untouched): below 1360 px the muted section word goes first, so the page name keeps the room.
- V5 Not reproduced (the shell never overflowed at 1024–1920). Defensive: `.dl-shell { overflow: clip }`, so nothing inside can scroll the shell.
- V6 Key influencers: a condition and its "small group" mark each stay on one line.
- V7 Dates isolate by their own script (FSI) with no-break spaces, so "1 يناير 2024 – 28 ديسمبر 2025" reads in order.
- V8 Answer direction by words, not letters (`proseDir`), so an Arabic sentence full of English names stays RTL.
- V9 Prose and chat chart labels keep 2 dp below 100, as the grid does (18.96 and 19 no longer both read "19"). Numbers between traced claims get the plain highlight. This changes redesign 1b's "1 dp from 10 up" (61.535 now reads 61.54).
- V10:
  - `color-scheme` per theme (the white scrollbar corner in dark mode).
  - Home quick-action subtitles wrap to two lines.
  - Language menu rows follow the menu's direction, with the label in a `<bdi>`.
  - The answer bar is called as a function instead of a component declared inside ChatPane. It was remounted on every render, so the first 👎 lost its click and AddToDashboard lost its state.
  - LLM server name and context boxes widened.

**Translation:**
- T1 on redesigned screens:
  - Data tab: Edit cells, Prev/Next, and the Filters and Global Filter panels.
  - Rules & alerts: the alert row, including the cadence.
  - New dashboard dialog: the untitled name, and template names by key, with the server's name as fallback.
  - Dataset Share dialog: the avatars.
- T2:
  - Column counts use plural forms ("8 أعمدة", "12 عمودًا"), and plural selection now reads Arabic-Indic digits.
  - Ask AI → "اسأل الذكاء الاصطناعي", Lineage → "تتبّع المصدر", Automations → "الأتمتة" (ar.ts text only).
  - Your own activity lines read in the first person ("حذفتَ …").
  - The Columns header is "الاستخدام" (the dangling "كـ" read as cut off).

**Checks:**
- A failing test before each fix, except B8 (not reproduced) and V5 (defensive). CSS-only fixes are pinned by rule tests (`layout.test.ts` ×3, `crumbLayout.test.ts`).
- Full suite: 285 files / 3768 tests pass. Type-check and build pass.
- Before/after captures (light, dark, Arabic; 1100–1440) are in `/media/saeed/New Volume1/projects/redesign-captures/qa-1-fixes/{before,after}/`.
- B4 and B6 are in "Backend follow-ups". T1 on the other pages is step 8-i18n.

### 7e Builder — `ca51517` (7e1), `4d43bc4` (7e2), `7f647d7` (7e3), `750dc4c` (7e4), `0f0e4e2` (7e5)

**Changed (edit mode; reading keeps 7d):**
- 7e1 Header and toolbars:
  - Header: back arrow, the name (rename in place), dataset chips, Draft (unpublished; published dashboards keep ReleaseControl), "Saved · 2s ago", undo / redo, sensitivity, then Refresh, Share (primary), Present, Export, Subscribe (icon), Open reports, ⋮ and the Edit / View switch.
  - Second row: Report / Data / Model; page tabs with a ⌄ menu (Rename, Move left / right through the page update, undoable, mirrored in Arabic, Page settings, Delete); + and v1's template menu; Layout with v1's recipes and Free layout; zoom − / + and Fit.
  - Footer: page, widgets on it, the selection, Shortcuts.
  - S6: the builder opens with the icon rail; the saved choice is untouched and the rail's toggle still expands it.
- 7e2 Left panel: Insert / Fields / Templates (v1: Charts / Fields / More).
  - Insert: v1's gallery with a hover and focus preview (a schematic, and what each chart is best for).
  - Fields: dataset card first, search, quiet rows (badge, name, count) whose v1 tools show on hover or focus; report filters and date presets moved here from More.
  - Templates: page layouts as cards, your page templates, save this page, import a page, then v1's widget templates. The panel defaults to 264 px.
- 7e3 Right rail and Properties:
  - The rail holds every v1 panel in the prototype's groups. It replaces v1's eight-word toolbar and More panels; pressing the open panel returns to Properties.
  - AI is one button with Ask / Insights / Suggest tabs.
  - Properties has a head, the object card, Report settings, and a pin that keeps it beside the next panel.
  - Format / Data / Interactions sit over v1's settings tabs; every tab and the settings search are kept, and search reaches every section. The panel is 300 px.
- 7e4 Canvas overlays, all beside WidgetRenderer and off the move path:
  - guides and "col 1–6 · row 8 · aligned ×5" for the selected widget
  - a group box around a multi-selection; v1's eight align / distribute modes moved into Properties
  - a quick toolbar (Duplicate, Assign data, Filters)
  - "No rows match these filters · Clear filters"
  - a heavy-page banner past the Review panel's count, now one shared constant
- 7e5 States:
  - the shortcuts sheet, which lists only bound keys; Ctrl+D and Ctrl + / − were added (Ctrl+/ stays the page copilot's, as in v1: a second binding opened two things at once)
  - the page copilot locks with one line while the model server is down
  - a builder-shaped skeleton while loading
  - a load failure keeps Retry, gains the way back, and is in the reader's language (LoadError takes an optional title)
  - the empty page opens Templates
  - the conflict banner restyled; read-only stays v1's gating

**Deviations from the prototype:**
- The Edit / View switch stays last in the header (v1 and 7d rule, pinned by a test); the prototype puts it before Present. v1's Refresh, Subscribe, Open reports, sensitivity and ReleaseControl stay in the header. On a narrow header, Present and Export become icons and keep their words as accessible names.
- Not built (new endpoints or semantics):
  - Duplicate page and Split page (both listed)
  - rail count badges (listed)
  - KPI delta / sparkline (listed)
  - per-widget Number format, Show title and the automatic horizontal bars (owner: skipped)
  - a drag handle on the quick toolbar (move path)
- The Layout menu holds v1's recipes and Free layout, not the prototype's Show grid / Snap to grid. v1 has no grid overlay, and snapping is always on.
- The collapsed left panel is v1's chevron strip, not a 44 px icon column. Field badges keep v1's glyphs (#, Aa, ƒx), whose names are pinned.
- Loading, error and needs-data widget states stay WidgetRenderer's own (v1).
- The canvas is not mirrored in Arabic (v1); the guides follow it.

**Tests:**
- Re-pinned, with nothing dropped:
  - zoom (×2)
  - add page
  - delete page (now in the page menu)
  - the pop-up marker (now in words)
  - the left-tab names (11 calls)
  - the panel helper and report rules (×2), now from the rail
  - the interaction carry-through test (set under Interactions, title under Format)
- New:
  - toolbar (10), rail (5), Templates (4), gallery (4), canvas overlays (5), shortcuts (2), Layout S6 (1)
  - settings sections (4), StatusBar (1), copilot offline (1)
  - builder integration (11)
- Full suite: 291 files / 3816 tests pass. Type-check and build pass.
- New `e2e/capture/redesign/cap_step7e.mjs`. Captures (light, dark, Arabic, Arabic dark) were compared with the prototype and copied to `/media/saeed/New Volume1/projects/redesign-captures/7e/`.

### 7-QA2 Fixes from the second QA report — the commit that adds this entry

**Broken:**
- N1 Insights: the Build button was a string holding JSX, shown as raw markup (v1 bug). It is a real button now.
- N2 A dashboard opens for reading.
  - v1 (since the 25 Sep UI refresh) opened every dashboard in Edit for anyone who could edit it.
  - Now only a just-created blank dashboard opens in Edit: `?edit=1` from New dashboard and "Build a dashboard", or `?pick=data`. AI-built dashboards arrive complete and open in View.
  - Version history from ⋮ opens a panel over the view; it no longer switches to Edit.
- N3 The 39 entries are real, not a display bug.
  - Opening a page with no layout mode in Edit runs v1's automatic Executive packing. It saves each moved widget as a separate parallel request, and the server snapshots a version per save. Parallel requests read the same revision, hence the repeats.
  - A burst like this can also push older versions past the retention window.
  - The history now shows such a burst as one entry ("39 changes"), expandable; its Restore goes to before the burst.
  - The server fix is in the backend list (one version per action, batch layout save, atomic revision). Changing the client's parallel saves would touch v1's move/save path, so it was left.
- N4 The reading toolbar (Ask AI, Focus) is centred on the widget's top edge. In Arabic it sat on the widget's own ⋮.
- N5 CustomGraphRenderer passes `key` directly, not inside the spread props object. The change is 5 lines in that function, with no other renderer change.
- B8 Not reproduced locally, even with slow secondary requests or focus tracking.
  - Likely cause: the search box appeared only after the dashboard list loaded. While the server was busy (the QA run had multi-minute Ask AI requests in flight), a click where the box would be landed nowhere.
  - The box is now there from the first paint. What is typed meanwhile applies when the rows arrive. The shared ListFilter gained an `always` option, and other pages are unchanged.
  - Home: a pressed chip shows it is opening and the others wait. The Ask AI route loads on demand, so the click looked lost.

**Visual:**
- V1 Below 720 px of table, Status folds into the name cell too and the columns shrink. The minimum drops to 540 px, so a 606 px box (125% zoom) needs no sideways scroll, and the Arabic group header is no longer clipped.
- V4 Below 1280 px, the top bar's Search shows only its icon and the model picker narrows (CSS only; TopBar.tsx untouched). At 1152 and 1229 the page names show in full.
- V10:
  - Dark Data table white square: the real cause was the unstyled `::-webkit-scrollbar-corner` (custom scrollbars paint it white); round 1's `color-scheme` change didn't reach it.
  - Platform settings: on a narrow panel each model server is a grid of labelled fields, nothing scrolled out of sight.
- Visual 6 Chart tooltip value and label in the text colour (CSS only).
- Visual 7 The print view is paper: light while open, with the reader's theme back on leaving. The bridge tokens are also declared on `[data-product]` subtrees.
- Visual 8 Present shows the title once when the page's title is the dashboard's name, and opens scrolled to the top.
- Visual 9 Revoking the link just minted takes its one-time URL away. Revoked and expired links fold behind "Show N revoked or expired links"; there is no delete endpoint, and they are the record of who had access.
- Visual 10 / T10 Version history times use a 24-hour clock in the reader's language (Arabic showed "01:01 PM").

**Translation:**
- 11: the widget ⋮ menu (labels only; "؟" lands at the end).
- 12: Insights' own words. The server's narrative and findings stay English with `dir="auto"` (backend row added).
- 14: the partial-period note, composed in Arabic from its fields, with the period label isolated.
- 15: the print view buttons.
- Key influencers: the caveat and the server's skip notes are translated by their fixed patterns; an unknown sentence is shown as sent.

**Checks:**
- A failing test before each fix, except B8 (fixed by its likely cause; pinned by tests) and the CSS-only fixes (pinned by rule tests).
- Full suite: 294 files / 3844 tests. The only failure was the known flaky `Lineage.test.tsx` (FINAL), which passes alone. Type-check and build pass.
- Before (the QA's screenshots) and after captures are in `/media/saeed/New Volume1/projects/redesign-captures/qa-2-fixes/{before,after}/`.
- B3, B4/13/16, B6, N3 and T12 are in "Backend follow-ups". The remaining T1 items stay in 8-i18n.


### 7-QA3 Fixes from the third QA report — Batch A (builder behaviour), the commit that adds this entry

The QA3 report and screenshots were not on this machine. `qa-3/QA_REPORT_3.md` is rebuilt from the step brief; the QA's screenshots still need to be added to that folder.

**Fixed:**
- **A1** One selection rule (`reportBuilder/selection.ts`).
  - When the multi-set is in use, it holds every selected widget, including the one first selected by a plain click. That one used to be outlined but not counted.
  - The last widget added is the primary, so Properties follows the latest click.
  - Shift+click on a selected widget removes it, and one left becomes a single selection. Escape and the ✕ clear both.
- **A2 / A3 — unconfirmed fix: first item in QA4, with a real pointer.** A field drop finds its widget by the pointer against the drawn tile boxes (`widgetIdAtPoint`), not by `e.target.closest(...)`. An overlay drawn over a tile but outside it lost the drop.
  - Not reproduced headless: Playwright drops worked in EN and AR before the change.
  - Fixed by the likely cause; pinned by a unit test (overlay on top, RTL) and a builder test (a drop event on the canvas itself fills the KPI's measure).
- **A4** The quick toolbar's Filters sends the Assign data event with `tab: 'Filters'` and `open: false`. The panel opens Data › Filters, with no dialog.
- **A5**
  - Properties seeds its fields per widget. It now remounts (`panelEpoch`) after a change made outside it: a drop or a fix on the widget, Convert to, or a field click.
  - The page panel follows `page.name`. It skips the name it sent itself, so a save landing mid-typing never rolls the field back, and the sync saves nothing.
- **A6** In Edit, a click on a mark selects the widget only: `handleClick` returns before any cross-filter.
  - Decomposition drill (navigation inside the widget) and slicer/text-filter controls are unchanged.
  - View and Present still filter by clicking.
- **A7** Two causes.
  - (1) Drag, resize and the arrow nudge measured from the stored layout. On a page still auto-packed, that is not where the widget is drawn. The packed preview was also dropped as soon as a drag began, so every widget jumped.
  - (2) `dropPacked` compacted the whole page, floating the dropped widget up and sliding others into its hole.
  - Now the drop cell is where it lands. Only widgets it collides with are pushed down (cascading), and the ≥35% swap is kept. Resize, duplicate and delete still compact as before.
- **A8** `lib/readingOrder.ts`: top→bottom, then start→end (right→left in Arabic; the canvas itself is not mirrored).
  - Computed from the drawn layout, so it follows moves.
  - A Tab order set by the author (`tabIndex`) wins, and widgets without one follow in reading order.
  - Used by Tab order, Selection, the Mobile layout's unplaced widgets and the phone stack. In View the canvas DOM is in that order, so the keyboard follows the eye.
- **A9** Every entry to Edit folds the app rail to icons. 7e1 folded only the first time.
- **A10** A duplicate is placed under the original as drawn, selected alone, and scrolled into view. Escape also blurs a focused tile.

**Tests:**
- New: selection (5), dashboardLayout drops (2), widgetIdAtPoint (3), readingOrder (5), page-name sync (2), the Filters tab (1), Edit-click no filter (1), builder count + Escape (1), drop on a KPI by pointer (1).
- Re-pinned:
  - 7e4 multi-select now clicks A, then Shift+clicks B (it relied on Shift+clicking A twice).
  - S6 now expects the rail to fold again on View → Edit.
  - Drillthrough: the click-to-drill test runs in View.
- A failing test before each fix, except A2 (not reproduced; likely cause).

**Captures:**
- `e2e/capture/redesign/cap_qa3_a.mjs` uses one scratch dashboard per scene, made and deleted through the API. Results are read back from the API.
- Before is HEAD served from a worktree on :3002; after is :3001.
- Folders: `/media/saeed/New Volume1/projects/redesign-captures/qa-3-fixes/{before,after}/A*`, in light, dark, Arabic and Arabic dark.
- Reproduced headless on the old build: A4 (opened All), A6 ("1 filter" chips on every widget), A8 (order scrambled), A9 (rail expanded).
- Not reproduced headless: A2, A3, A7. Drops and moves worked there on a free-layout page.
- After: every item checks out in all four modes. A7 was also run on a packed page in EN and AR: KPI 1 lands on row 8, nothing else moves.

**Recorded, not fixed (see Plan and Backend follow-ups):**
- N3 re-checked: still open at the root, top backend item.
- 8-i18n and FINAL additions.
- N7: re-test in QA4.

### 7-QA3 Batches B–D (builder visuals, builder Arabic, round-2 leftovers), the commit that adds this entry

**B — Builder visuals:**
- **B1 — deviation from the brief's default.** The floating button is NOT hidden.
  - In Edit it is the page copilot, the dashboard's editor (CLAUDE.md). The rail's AI panel (Ask, Insights, Suggestions) asks about data and edits nothing, so hiding the button would leave the editor reachable only by Ctrl+/.
  - The brief's alternative is applied: the button floats inside the canvas column, measured from `[data-canvas-scroll]`. It never covers the right panel, the pinned Properties, the rail, or the fields panel on the start side, in either direction.
  - v1 measured only the settings panel.
- **B2** The col · row tag sits in the gutter under the widget (16px, so it reaches only the next widget's empty top padding).
  - At the canvas bottom it goes above the widget instead.
  - It shows during drag and resize, and gives a row range ("row 1–5").
  - Both ranges are in `<bdi dir="ltr">`, so Arabic no longer reads "3-1".
- **B3** The save state has a fixed 104px width, ellipsized, with the full text on hover. It sits in one unbreakable group with undo/redo, so they never move.
  - The sensitivity select has a fixed 124px width and is no longer capped in a narrow header.
  - In a narrow header (below 1180px) the report name gives way instead: 120px, ellipsized, full name on hover.
  - The header stays one row (52px) at 1440, EN and AR.
- **B4** The widget header controls:
  - paint on the widget's own colour (`--dl-wbg`), solid under the icons;
  - join the header row when the widget is selected or focused (no overlap; the fixed 84px reserve is gone);
  - leave the title a minimum of `min(8em, 45%)`, while the status chips shrink and clip;
  - while a widget is selected, drop the → ← markers (the Interactions tab says the same thing), and on a widget narrower than 260px also drop the delete icon (it stays in ⋮ and on the Delete key). A 3-column KPI now reads "Revenue o…", not "Reven…".
- **B5** A canvas column narrower than the canvas minimum (600px) scales the page to fit (`fitScale`). Drag and resize use the same scale. Pinned at 1440, the column is 428px and nothing overflows.
- **B6** Toasts sit at `--dl-toast-bottom`, raised to 44px while a status bar is on the page.
- **Found in capture:**
  - "Assign data" on a placeholder of a widget that was not selected opened no dialog: its settings panel mounted after the event.
  - The builder now repeats the event once (`relayed`). A test fails without that.

**C — Builder Arabic:**
- The builder's strings are in `i18n/builder/{canvas,panes,rules,shell}.ts`, spread into `en.ts`/`ar.ts`. That is about 680 keys.
- The settings panel keeps its English-as-key `PANEL_AR` (+28 entries). Role names are translated at display (`roleLabel`); `ROLE_SPECS` is untouched.
- The English output is byte-identical: the tests query it.
- All the items the QA listed are covered:
  1. placeholders;
  2. data roles, Custom page size, background image, and the Interactions section (the heading was clipped by letter-spacing on joined Arabic letters: no spacing in RTL now, and it wraps);
  3. the Assign data dialog;
  4. every rail pane's content (Review quotes are «» around a `<bdi>`);
  5. the delete-page dialog: the name is isolated (FSI…PDI), and the shared confirm's default buttons are now translated;
  6. the direction-aware empty page ("from the right panel" in RTL);
  7. toasts as full templates, including Undone/Redone, settings-change and Convert-to labels;
  8. "primary", "+ Add Dataset", and the "Click" key;
  9. the ⋮ pop-ups (Why, What moves, Is this difference real; ؟ at the sentence end), with the aggregation in words in Arabic.
- Also: the rules pane's sub-editors (ValueMap, Interval, DataBar).
- **Guard:**
  - `src/test/hardcodedStrings.ts` + `builderStrings.test.ts` parse the 33 Builder files with the TypeScript compiler and fail on English in:
    - JSX text;
    - seen attributes (title, aria-label, placeholder, alt, label);
    - toast and confirm messages;
    - UI-named object properties (`label:`, `title:`, `hint:` …).
  - Message keys are not prose.
  - `// i18n-ok` marks the rare non-prose literal (code samples, URL placeholders, "PDF").
- **Left as is, recorded:**
  - text from the server or the AI (`dir="auto"`, backend T12/AP3);
  - column names, operator codes, widget-type ids;
  - palette names ("Graphite"), which the guard does not reach (they are data);
  - the StatusBar zoom buttons have no label (adding one changes the English accessible name).
  - A copy's title "{name} (copy)" is now written in the author's language and saved as such.
- **For a native-speaker check:** Review badges (ربط / إتاحة / خطأ / تحذير / معلومة), "Operator" → الشرط, "ms" → ملّي ثانية.
- The translation was done by four parallel agents on disjoint files, then reviewed in Arabic captures.

**D — Round-2 leftovers:**
- **D1** The breadcrumb gives way by flex weights, not breakpoints, so it holds at a real or a CSS-scaled 125%:
  - the middle link shrinks first, then the section word, both keeping a stub;
  - the page name does not shrink (up to 60% of the trail).
  - Before, at a CSS-scaled 125%, the Arabic name was 19px ("D."); now it is whole.
- **D2** The dark tooltip's series name ("sum(revenue)") uses the text token.
- **D3** The cause: a shareable row has three 30px buttons, 118px with padding, in a 112px column. The ⋯ was cut by 6px.
  - The column is now 124px.
  - Narrow (below 720) the hover shortcuts go (they are in ⋯), and the narrow width now actually applies (the base rule after it used to win).
- **D4** `lib/dateFormat.ts` `formatDate(value, style)` is driven by the UI language:
  - English: en-GB, 24h;
  - Arabic: Arabic months with Latin digits, then the reader's digit choice.
  - It replaces 23 browser-locale calls (Activity, Audit, Jobs, Deliveries, notifications, the dataset panels, comments, schedule…) and `formatTimeAgo`'s fallback.
  - A test fails on any new `new Date(…).toLocaleString()` without a locale.
- **D5** `lib/isolateNumbers.tsx` puts every number, %, money value and range in `<bdi dir="ltr">`, with `dir="auto"` on each insight paragraph: Insights hub, dataset Insights tab, builder Insights pane. Five test queries were re-pinned to whole-text matches.

**Tests:**
- New:
  - B (8)
  - CSS rules B3/B4/B6 (4)
  - C: guard (33 files), canvasArabic (10), panes (4), rules (3), shellArabic (5)
  - D: dateFormat (4), isolateNumbers (3), crumb (2), list (2)
  - Assign-data relay (1)
- Re-pinned:
  - the coord-tag text now gives a row range;
  - the shell delete test expects the isolated name;
  - five Insights queries use whole-text matches.
- `e2e/capture/redesign/cap_qa3_bd.mjs` captures before (:3002) and after (:3001) into `qa-3-fixes/{before,after}/B*,C*,D*`, in EN/AR × light/dark (C in Arabic only: the English is unchanged by design).
- Full suite: 305 files / 3941 tests pass. Under full load "ReportBuilder report-level display rules > persists …" once timed out (4.6s); it passes 3/3 alone and passed in the run before. Added to FINAL's flaky-test watch list. Type-check and build pass.

### 7-QA3-N3 Stop the save burst at its source — the commit that adds this entry

**Change (frontend only):**
- `shownLayouts(page)` (lib/dashboardLayout) is what the canvas draws:
  - the automatic layout for a page with no layout mode;
  - a packed page with overlapping widgets compacted;
  - otherwise the stored layout.
- The two effects that SAVED those on opening in Edit are gone (v1: one parallel `updateWidget` per widget, plus a page update).
- `persistWidgetLayouts`, the path every user layout change takes (drag, resize, nudge, align, distribute, recipe):
  - merges the shown positions into the change;
  - on a page with no layout mode, sets `layout_mode: 'packed'` and the template in the same step;
  - writes page-then-widgets one request at a time (was `Promise.all`).
- Undo writes the pre-edit layouts back, one at a time, and puts a first edit's page back to "no layout mode" (`''`: PATCH drops a null, and the client reads `''` as no mode).

**Version counts (real API):**
- Measured by `e2e/journeys/n3_versions_journey.mjs` on a scratch dashboard with two pages: "Old" (no layout mode, 4 widgets) and "Overlap" (packed, 2 overlapping widgets).

| Step | Before (HEAD, :3002) | After (:3001) |
|---|---|---|
| Open in Edit and visit both pages | 8 → 14 (+6), and both pages' stored layouts rewritten | 8 → 8 (+0), stored layouts unchanged |
| Re-open the reset page | +5 | +0 (18 → 18) |
| First real edit (drag one widget on "Old") | +1, but only because opening had already stored everything | +5 = 5 sequential PATCHes (page, then 4 widgets), 0 in flight together. Stored = shown: after a reload, the 3 other widgets are drawn where they were |
| Undo of that edit | +1; layouts NOT restored (packed values); mode stays "packed"; 4 writes overlapping | +5; stored layouts restored exactly; mode back to "no layout mode"; 0 overlapping |

**Tests:**
- New:
  - `shownLayouts` (3);
  - builder: zero writes on opening, for no layout mode and for packed-with-overlaps (2);
  - first edit page-first, sequential (max 1 in flight), every shown widget stored; undo restores layouts and mode (1);
  - the real-API journey (12 checks).
- Full suite: 305 files / 3947 tests pass. Type-check and build pass.
- The journey's first in-flight counter waited for Playwright's `requestfinished`, which fires late. It now ends a request at its response; the request log confirms strict order.

**Still open (backend row):** one version per stored widget (+5 for one drag on an old 4-widget page).

### 7-QA4 Fixes from the fourth QA report — the commit that adds this entry

QA4 confirmed N3 (opening Demo — Sales Overview in Edit left revision 39 unchanged) and almost all of 7-QA3. N3 is fixed on the client; the batch layout endpoint and the 50-version cap remain backend items. The report and screenshots are in `redesign-captures/qa-4/`.

**Broken:**
- **E0 (the owner's, after QA4)** The whole document scrolled on Home: the shell slid up over an empty strip.
  - Cause: Home's visually hidden "Actions" table header (`.dl-sr-only`, `position: absolute`, added in 7a `3ed767f`) had no positioned ancestor, so it was placed against the document at its static position, y≈1557 in a 1080px window. The clipping shell and the page scroller do not clip an absolute element whose containing block is above them.
  - Confirmed: `before-redesign` is clean (1080 on every page); `da76a61` and HEAD before the fix had Home at 1557, and a wheel over the sidebar scrolled the window 477px.
  - Fix: `.dl-shell` and `.dl-shell__content` are `position: relative`, so every absolutely positioned element in the app is contained and clipped by the shell. The QA V5 rule (the shell clips) is kept.
  - Check: `e2e/journeys/document_scroll_journey.mjs`, Home, Dashboards, Datasets and the Builder, EN and AR, dark, 1920×1080: `scrollHeight === innerHeight`, and after a long wheel over the content and over the sidebar the window has not scrolled and the shell's top is 0. 8/8 pass; the old build fails Home in both languages (1557, scrolled 477). Pinned by a CSS rule test.
- **E1** A new display rule starts on what the server can evaluate:
  - "> 0" on the first numeric column;
  - with none, a colour per value (`value_map`), which fits a text column.
  - Operators follow the column's type: no > ≥ < ≤ "between" on a text or date column, and switching to one drops the comparison to "=".
  - A server rule error is a short translated message, with the server's text as an LTR detail (`<details>`).
  - Server-side validation is in Backend follow-ups.
- **E2** `lib/fieldPlacement.roleForField` is the one rule for drop and click:
  - a column already on the widget, in any role, is never placed again;
  - a text field never goes into Measure, Target or Size (Target was not recognised as numeric);
  - with no fitting role, the "became a new chart" path runs.
  - A builder test had relied on the old behaviour (its fixture served the saved config from the second load on, so "sales" was already on the widget when clicked, and the old planner put it into Dimension); the fixture now serves the empty config until the first save.

**Visual:**
- **V1** `lib/contrastTokens`: a widget with a plain-colour custom background sets `--text`, `--muted`, `--border`, `--surface2` and `--dl-table-rule` on itself from the background's luminance. Title, header icons, axis ticks, data labels, legend and grid all read those, in both themes.
- **V2** Below 1020px of header, what gives first:
  - the dataset chip shows only its icon (the name stays its accessible name and tooltip), after the source chip, which was already hidden there;
  - the title part keeps 360px, and the actions wrap to their own row instead of sliding over the chip.
  - At 900px with "Opened reports (5)": no overlaps, EN and AR (3 header rows).
- **V3** Panel headers (`.dl-bd-ph`, every right-rail panel) are sticky. Before, the Properties header scrolled 344px away and left the collapse "<" over the fields; now it stays.
- **V4** The col · row tag measures itself and the canvas after drawing: one that would cross the canvas's bottom or end edge goes above the widget, or into its corner.
- **V5** The per-widget quick toolbars are hidden during a multi-selection; the group bar acts on all of them.
- **V6** The real cause: a bar picked in View kept its cross-filter ("1 filter" on every widget) and its highlight in Edit, where a click no longer filters (QA3 A6), so nothing could clear it. Entering Edit clears the cross-filters (`ClearSelectionOnEdit`, inside the provider) and the widget selection. The test fails without it.
- **V7** In the Performance pane the number is mono and "ملّي ثانية" is in the text font. The coord tag's words are in the text font, only its ranges mono. Arabic is never letter-spaced: one `:root[dir="rtl"]` rule overrides the inline `letterSpacing` of the uppercase headings.
- **V8** Every crumb has its full text as a tooltip. QA3's 60% cap on the page name is gone (it cut "لوحات المعلو…"); so is a floor, since a floor wider than a short name ("Datasets") overflowed the trail and cut the crumb in front. At 100% and at 1152px nothing is cut, EN and AR. Under a CSS-scaled 125% (the QA's method; the breakpoints do not fire) the page name loses ~1px, with its tooltip.
- **V9** (agent) The Ask AI answer chart used the Builder's renderers without their measured width, so the axis planner assumed 560px and kept four region names upright. It is now wrapped in the Builder's `MeasuredChart`: tilt, thin, then clip, mirrored in RTL.

**Arabic:**
- **T1** Role names go through `roleLabel` in Review and in the drop toast and undo label.
- **T2** `lib/chartName` gives the gallery names (Arabic) / gallery labels (English) in the Performance pane and Convert to.
- **T3** `CollapsibleSide`'s resize/collapse/expand labels are full templates. The canvas filter bar and floating filter window are translated, and all three are now in the guard.
- **T4** `describeConfigChange`:
  - lists become counts with plurals ("3 rules" / "3 قواعد"), objects "set", nothing "none" / "لا شيء";
  - in Arabic, settings are named by their panel labels ("قواعد العرض").
- **T5** (agent) The "Is this difference real?" body: frontend-owned labels, the composed verdicts, the effect words and the three footnotes are translated; the server's sentences stay as sent (`dir="auto"`). Also: the subtitle's aggregation in words, and isolated numbers never wrap ("p =) 0.8487)").
- **T6** (agent) The dataset delete (Datasets, Connections) and the Dashboards delete/move/folder titles are full templates with the name isolated (FSI…PDI); the row menu label too.

**Out of scope, recorded:**
- Activity action codes and the other English report panels → 8-i18n list.
- Insight sentences → T12.
- Dates on Jobs, Deliveries, notifications and Schedule → re-check in QA5 if data exists.
- "What moves revenue" → QA5.
- A2/A3 → the owner's real-mouse check.

**Tests:**
- New:
  - fieldPlacement (5); E1 (4); contrastTokens (4) + widget (1); V4 (1); V6 (1); V5 assertion; undo T4 (2); chartName (1); QA4 CSS rules (3);
  - (agents) difference Arabic (3), delete dialogs (4), answer chart axis (4).
- Re-pinned:
  - the field-click fixture (above);
  - the colour-map test (a new rule now starts on the first numeric column);
  - the crumb rule test.
- `e2e/capture/redesign/cap_qa4.mjs`: before (:3002 at `da76a61`) and after (:3001) into `qa-4-fixes/{before,after}`, EN/AR × light/dark. V9 has no capture (it needs a live LLM answer); its unit test covers it.
- Full suite: 311 files / 3984 tests pass (run with 4 workers), after E0. With the default worker count, while the capture servers were busy, three slow tests timed out (the map click 24s, geo time-play 11s, report-level display rules 7.8s); each passes alone. Type-check and build pass.
- Seen while capturing (not in the QA report): on the Datasets page, the first click on a non-selected row's ⋯ sometimes opens and at once closes its menu in Playwright; a second click opens it. The QA opened it normally with a real browser. Watch in QA5.

### 8-i18n Pages outside the Builder in Arabic — the commit that adds this entry

**Approach (as in the Builder):**
- One message module per area in `src/i18n/pages/` (`adminSecurity`, `adminPlatform`, `dataPages`, `panelsA`, `panelsB`, `modelsMaps`), spread into `en.ts`/`ar.ts`: about 1,900 keys.
- Full templates with placeholders and ICU plurals (Arabic dual and few/many forms).
- Names isolated: `<bdi>` in JSX, «\u2068…\u2069» in plain strings.
- Codes and values sent to the server unchanged.
- English byte-identical: the 20 English captures are pixel-identical before/after (SSO differs only by the server port in its callback URL).
- Six agents worked in parallel on disjoint files, plus one for the leftovers, then the result was reviewed in Arabic captures.

**Covered** (each file in its area's guard, `src/test/strings.<area>.test.ts`):
- **Admin security:** row and column security rules, connection rules, roles, users (incl. bulk import), export policy.
- **Admin and platform:**
  - Organizations, Org units, SSO, API keys, Custom connectors, Maps, Admin settings with Basemap.
  - Platform settings: the server's catalog is translated by key, with the server's English as fallback. Non-secret string values (the LLM_ENDPOINTS JSON, URLs, ids) are LTR-isolated, which fixes the endpoint list scrambled in RTL.
- **Data pages:**
  - Connections (toasts, the connection dialog, Combine databases), Source review, Glossary ("Business terms").
  - Activity: the 101 audit action codes, in words in Arabic. English keeps the raw code, which a test pins; an unknown code shows raw, LTR.
  - Jobs, Deliveries, the dashboards-list group label, and the Home dashboards delete confirm (name isolated).
- **Report panels:**
  - Measures, Column formats, Custom functions, Calc columns (with the function catalog's 10 categories and 84 hints), Custom categories, Hierarchy tree, Access dialog and explainer, Subscribe, Suggestions, Pack terms.
  - The prep pipeline (panel, steps, step editor, join note), Outlier details, Data views, Relative dates.
  - Models tab ("random forest" → الغابة العشوائية), model settings and view, map/pin/graph layers, boundary sets, geo match.
- **Shared:** `LoadError`'s default heading, body and buttons. In Arabic the heading is generic, because callers pass `what` in English.

**Left in English, and why:**
- Server prose: settings help without a key, connector catalog labels, model notes and warnings, the Activity entity text, error `detail`s. These are in the backend row.
- Formulas, function signatures, snippets, SQL and expression samples, product and protocol names (OpenID Connect, SAML 2.0, PostgreSQL), and metric abbreviations (AUC, R², RMSE). These are marked `// i18n-ok`.
- Data values a step writes (Training/Validation/Test, the catch-all "Other"), and saved defaults the user can edit ("Joined dataset", "Boundaries").
- Not on this step's list, still English: DatasetDetail's own text, CommandPalette, WorkspaceTree, QueryBuilderDialog/QueryCanvas, ExpressionBuilder, analysisResults, the dataset side panels (Alerts, Aggregates, Data quality, Column meaning), FolderShare/DatasetShare dialogs, Upload, SharedReport, `lib/friendlyError`. The scanner counts them. They are the next i18n list, under "Then: Upload, Connections, Lineage, the AI button".

**Export-policy tooltip:** its English "Everything is allowed: untick "All" to choose" showed when every export is OFF. Fixed after the gate (owner's call): "All exports are off: untick "All off" to choose", the same meaning as the Arabic, pinned by a test.

**Tests:**
- New: six area guards (59 files); Arabic render tests per area (adminSecurity 6, adminPlatform 6, dataPages 5, panelsA 8 + 3, panelsB 9, modelsMaps 7).
- Re-pinned: the palette-wiring allow-list (the model card's arrow now mirrors in RTL).
- Full suite: 323 files / 4091 tests pass (4 workers). Type-check and build pass.
- Captures: `e2e/capture/redesign/cap_8i18n.mjs`, 20 pages × EN light / AR light / AR dark, before (:3002 at `4bd4025`) and after, in `redesign-captures/8-i18n/{before,after}/`.

### 7-QA5 Fixes from the fifth QA report — the commit that adds this entry

QA5 confirmed E0, E1, E2, V2–V6 and V8 from 7-QA4, and the 8-i18n pages (mostly Arabic). The report is in `redesign-captures/qa-5/QA_REPORT_5.md` (copied from `qa5-report.md`), with its screenshots.

**Broken / visual:**
- **F1** A widget with a light custom background now also sets `--surface` (white under dark text, dark under light text), so every chart tooltip, which draws with `--surface`/`--text`, has one consistent pair in both themes. With `data-contrast`, legend labels take the widget's text colour and swatches get a thin outline (Recharts legends, every chart type).
- **F2** The Σ (quick calculations) and ⌖ (classify) pop-ups are a shared `components/ui/AnchoredMenu`:
  - portalled to `<body>`, fixed under the button;
  - flipped above when there is no room, and shifted inside the window;
  - aligned to the right edge in RTL.
  - The quick-calc items are translated by key.
- **F3** The outlier rows table uses the data views' `formatCell` ("-6208.69"), each number LTR-isolated.
- **F4** (agent) Every admin credential field that is not the user's own login has `autoComplete="off"` / `"new-password"` and a distinct `name`/`id`:
  - custom connectors (`connector-<field>`), connections (`conn-<field>`);
  - SSO (`sso-client-id`/`-secret`), API keys;
  - basemap, the new-user and new-org forms.
  - Pinned by a test that no field is named username/password/email.

**Right-to-left:**
- **R1** (agent) Every operator and code-like token in the expression builder is LTR-isolated: operator buttons incl. `(` `)`, function chips, the Simple preview; the Advanced textarea and argument inputs are `dir="ltr"`, and `<option>` symbols use LRI…PDI in RTL. Also the prep filter summary and its input.
- **R2**
  - Arabic table cells are `unicode-bidi: plaintext`: a cell with no letters reads LTR, so the minus or currency stays in place.
  - Recharts tooltip values are LTR-isolated.
  - The outlier summary's numbers are isolated.
  - The field-format samples ("$1,234") are LRI…PDI-isolated in the Arabic option text.
- **R3** The 404 page's path is LRI…PDI-isolated in Arabic ("/activity").
- **R4** Map tooltips (choropleth, pie layer) take the place name's direction (`dir="auto"`) with the value isolated.

**Arabic:**
- **L1/L2** (agent) The expression builder (headings, Simple/Advanced, groups, system hints, type tags as separate translated words) and the step editor ("+ Condition" → «إضافة شرط», "is blank", value types, screen-reader labels) are translated; ExpressionBuilder is in the guard.
- **L3** (agent) `lib/dtypeName` (`dtypeName`, `dtypeShort`) for 11 type codes, used everywhere a type is shown (column security, column formats, custom categories, page properties, source review, dataset badges, the settings panel). **English now shows words** ("Number", "Text") instead of codes; no test pinned the codes. Badges keep NUM/DATE/TXT/BOOL, but integer/float/geometry badges became INT/DEC/GEO.
- **L4** The field Properties aggregation list uses the panel's own Arabic names.
- **L5** Report-filter operators are words in both languages ("equals (=)" / «يساوي (=)»), in the select and the saved-filter chips; codes are saved unchanged. One builder test re-pinned.
- **L6/L7** (agent) Connector field labels by key; starter packs by id; server prose `dir="auto"`, isolated, on its own lines; the SSO product list isolated LTR. Server-owned text is in the backend row.
- **L8 (verified, was broken)** The arrow-nudge and drag/resize undo labels were English ("Move "KPI 1""). Now templates: «نقل «KPI 1»».
- **L9 (verified, already fixed by 7-QA4)** Checked live in Arabic on the build QA5 tested:
  - panel labels «تغيير حجم «الإعدادات»» / «طيّ …»;
  - Review roles («المقياس»);
  - a rule-change undo reads «من قاعدة واحدة إلى لا شيء», with no JSON.

**Seen in QA5, not in this step's list (for QA6 / later):**
- E2's automatic chart title "Count by product" is English.
- A cross-filter click in View shows an empty tooltip box (V6).
- The T5 headline and gap sentences are server text (T12); the Welch line is garbled in RTL.
- The red Delete button has default focus in delete dialogs (Enter deletes).
- The Admin Audit trail shows action codes and "1d".
- Hierarchy rows' screen-reader labels ("Move Region up") and the dataset sensitivity tooltip are English.
- E1: a date column offers only equality conditions (no before/after).
- The expression builder's Arabic placeholder mixed with a code sample reads oddly in its LTR box.
- Datasets: a long blank area beside the preview.
- Word-check notes (Part 4): «تلقائي عند الخصوصية», «إيقاف الكل», «م.ب» -- for the native-speaker pass. (Fixed here: the share dialog's "7 يومًا" is a proper plural now, «7 أيام», pinned by a test.)

**Out of scope, recorded:**
- AI timeouts (backend row above).
- Dates on Jobs/Deliveries/notifications/Schedule, still with no data (date-format guard; check in FINAL).
- The next i18n step's pages.
- QA5 created and deleted dataflow #1, QA5-flow; dataflows are added to the allowed QA items for future rounds.
**Tests:**
- New: AnchoredMenu (3), contrast tokens (1), outliers F3/R2 (1), NotFound (2), CSS rules (R2), Arabic days plural (4).
- (agents) ExpressionBuilder Arabic (6), dtypeName and column security (2 files), admin forms autocomplete and labels (8).
- Re-pinned: the report-filter chip ("region equals (=) North").
- Full suite: 329 files / 4156 tests pass (4 workers). Type-check and build pass.
- Captures: `e2e/capture/redesign/cap_qa5.mjs` (41 scenes per side), before (:3002 at `c235968`) and after, in `redesign-captures/qa-5-fixes/{before,after}/`, plus the L8/L9 check (`L9-review-ar-light.png`).

### 7-QA5b Small fixes before QA6 — the commit that adds this entry
- **S1** Every confirm dialog that deletes now opens with focus on **Cancel**, so Enter (or a key repeat from the Enter that opened it) answers "no". This is the default for every destructive `ConfirmDialog`. Two benign-styled confirms pass the new `focusCancel` option: the hierarchy level removal and the version restore. A truly benign one (move to folder) still focuses its action. Every delete in the app goes through `ConfirmDialog` (checked by searching every API delete call). The one exception was the **prediction-model delete, which had no confirm at all**; it now asks first. The other modal dialogs have no delete in them.
- **S2** No code change. The QA's "empty tooltip box" is the cross-filtered chart's own tooltip with dark text on a dark box. That is the F1 contrast bug, reproduced on the pre-QA5 build (`c235968`). On `said` the same tooltip is light and readable. `cap_qa5b_s2.mjs`, before = pre-QA5.
- **S3** `lib/autoChart` titles (8 templates: "Count by product", "revenue by region", "Trend of …"…) go through `bc.canvas.auto.*`, with field names isolated. The title is saved with the widget, so it stays in the language it was made in. English is unchanged (pinned for every rule).
- **S4** The Admin Audit trail shows actions with the Activity page's words (shared helper `activityActionName`), in the rows and the filter. The filter still sends the code. An unknown code shows raw, LTR. All 17 admin-audit codes the backend writes were already in the Activity list. The load-error subject is translated too. Not changed: the target (`report:16`) and the detail ("1d") are server values.
- **S5** Hierarchy chains (screen-reader labels, the drag hint, the pick tooltip) and the dataset sensitivity control (tooltip, label, what a label enforces, toasts) are in Arabic; both files are in the guard. The server's reason text stays as sent, isolated. `SharedReport`'s "Sensitivity label" (the guest page, all English) is left for the i18n list.
- **S6** The evidence chip ("Welch's t-test · p = … · negligible effect (Cohen's d …)") is one template whose parts are each isolated: the test name, p, the effect name and the size, LTR. Before, the Arabic line ran "Welch · p = 0.8487" into one stretch and showed the size as "0.0119-". The server's headline and gap sentences are unchanged, as the brief asked. The date before/after conditions stay on the list above.

**Tests:**
- New: ConfirmDialog (Cancel focus, Enter does not delete; benign vs `focusCancel`), model delete asks (1), autoChart Arabic (2), audit Arabic (1), hierarchy Arabic (1), sensitivity Arabic (1), evidence-chip isolates (1).
- Re-pinned: the ConfirmDialog focus and Tab-order tests.
- Full suite: 329 files / 4168 tests pass (4 workers). Type-check and build pass.
- Captures: `e2e/capture/redesign/cap_qa5b.mjs` (S1, S3–S6) and `cap_qa5b_s2.mjs` (S2), EN light and AR light/dark. Before is :3002 at `7cba905` (S2 at `c235968`); after is in `redesign-captures/qa-5b-fixes/{before,after}/`. S1 before: focus on Delete, and Enter deleted the scratch dashboard; after: focus on Cancel, and it survives.
