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
- [x] 3b Dataset detail shell + Overview + tab map
- [x] 3c Remaining tabs + Share dialog
  - >> GATE A: stop, report the whole Datasets screen
- [x] 4a Ask AI Phase 1: layout, thread, column panel, answer card (visual redesign reverted at the owner's request, see 4-revert)
- [x] 4b Ask AI Phase 1: all states (first run, no dataset, thinking, clarification, offline, error) (visual redesign reverted, see 4-revert)
- [x] 4-revert Ask AI back to the v1 layout with fixes; Datasets menu clipping fixes
  - >> GATE B: stop, report Ask AI

> **Ask AI decision (2026-10-06, owner):** the Ask AI page uses the v1 layout and look
> (as at `120e0ef`) with fixes. The step 4 boards in `boards/step4-ask-ai-phase1/` are
> no longer the spec for it. Kept from step 4: translations, Pending without timed
> stages, the themed delete dialog, offline detection (locks the question box with one
> line), clarification column chips, "What was wrong?" after 👎, and Edit question on
> an error.
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

## Backend follow-ups (found during the frontend steps)

Not part of steps 1–6; candidates for the handoff's section 7 phases.

| Found in | Item | Why it needs the backend |
|---|---|---|
| 3c Data | Download CSV of a dataset (with the Data tab's filters, sort and search) | No dataset export endpoint exists; only Ask AI runs can be exported. |
| 3c Share | Change a grant's View/Edit level in place | `/datasets/{id}/shares` can create and delete grants, not update one. |
| 3c Share | "N row-security rules apply to this dataset" in the share dialog | No endpoint reports the rules that apply to a dataset (related to N9). |

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

