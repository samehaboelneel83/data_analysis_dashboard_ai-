# Datalytics redesign — autopilot plan

This file is the work order for the rest of the redesign. Work through it top to bottom **without waiting for approval between steps**, except where it says STOP. Keep this file up to date: tick each step when it's done and add a short entry to the Progress log at the end. If a session ends, the next one resumes from the first unticked step.

## Context

- Repo: `/media/saeed/New Volume2/projects/data_analysis_dashboard_ai-/AI_data_tool/data_analytics/`, branch `said`. The owner pushes from his terminal. You commit locally only; never push, rebase or force.
- Read first: `docs/redesign/PLAN.md` (the newest entries: step 10 Ask AI, "Step 10: where I stopped", 7-QA6, the merge of main) and `docs/redesign/HANDOVER.md`.
- Designs: `/media/saeed/New Volume2/projects/design-handoff-3/`
  - `datalytics-archive/`: the full Claude Design project. Canvas files at its root (`Lineage Redesign.html`, `Upload Redesign.html`, `Connections Redesign.html`, `AI Button Redesign.html`, `Ask AI Redesign v2.html`). The prototypes they frame are under `datalytics-archive/redesign/`, and `README.md` describes the design system.
  - `ask-ai/`: the Ask AI handoff, `robot/ask-robot.html`, and `empty-polish/ask-ai-empty-preview.html`.
  - `lineage/`: the Lineage standalone.
  - Step brief: `docs/redesign/11-Lineage.md`.
- The AI model servers are unreachable on this network. Fake AI responses **in the browser only, for captures and tests**; never in the product.

## Rules (every step)

1. **Phase 1:** no new backend work, and no fake or sample data in the product. If a design element needs data the API doesn't have, leave it out and add it to PLAN.md's backend follow-ups.
2. **Design vs our system:** the prototypes are specs, not code to paste. Use our tokens, components, icons (lucide-react) and fonts. Where a design's own prompt or notes conflict with these rules, these rules win.
3. **Translations:** every UI string goes through translation, with full templates and plurals. Extend the hard-coded-English guards to every new file. Arabic mirrors; numbers, SQL, ids and names stay left-to-right isolated.
4. **Scope:** desktop only. Pages must stay usable at 1024px; skip phone layouts.
5. **Motion:** animate transform and opacity only, and turn everything off under `prefers-reduced-motion`.
6. **Accessibility:** real buttons and inputs, labels, focus rings, keyboard support.
7. **Usage-saving:**
   - Captures: EN light and AR dark at 1440; add 1024 only for layout changes. No GIFs.
   - Run targeted tests while working, and the full suite once at the end of each step.
   - At most 2 parallel sub-agents, and only for translation work.
   - Don't re-read files you already know.
8. **Each step ends with:** type-check, build and full suite green (or failures shown to be the known flaky ones), one commit `step <id>: <summary>`, a tick in this file, and a Progress-log entry of at most 10 lines (what changed, what was left out and why, backend items added, the capture folder).
9. **Captures** go to `/media/saeed/New Volume2/projects/redesign-captures/<step>/{before,after}/`.

## STOP and ask the owner only for

- Deleting or changing real data: datasets, dashboards (including #16), connections, the calculated column "profit" on Demo — Sales, or users.
- Any backend, database, migration or docker change.
- Changing the teammate's features beyond what's needed to integrate (Guided setup, HierarchyRenderer/Sunburst, condition boxes, no-code formulas). Integration fixes are fine; rewrites need approval.
- A design choice that would change an approved behaviour listed under Decisions.
- A failure you can't fix within the step.

Everything else: decide using the defaults below, record the decision in the Progress log, and continue.

## Decisions already made (use these)

- **Ask AI:** v1 is replaced by the new design.
  - Two-column empty state with the always-open chooser.
  - The robot mascot, with states idle / typing / thinking / happy / error / sleep. Its head is the avatar on cards; only the newest card animates.
  - Real duration only via one `GET /agent/runs/{id}` after an answer. "Edit question" also on answers. Composer limit 2000, with the warning colour from 1801.
  - The error card shows column-based chips, "Try asking about these columns". Loading shows elapsed time and a skeleton, with no step list. No "Synced …" line.
  - Export ▾ menu in the actions row. No totals row.
- **Thousands grouping:** quantity columns only. Years, ids and coordinates are never grouped.
- **Desktop only.** Builder canvas is not mirrored in Arabic. Dashboards open in View. Present auto-play starts off.
- **Flaky tests:** treated as one FINAL item (shared cause), not a growing list.

---

## Steps

### [x] 1. Ask AI Part D: history rail
As planned in PLAN.md step 10. Restyle, and move the rail to the inline-end at 288px; it becomes an overlay below 1180px. Today / Earlier groups, New chat, rename, delete, collapse, filtered to the chosen data, and empty states ("Pick a dataset to see its questions." / "No questions yet for this dataset."). Show creation time only; failed flags and updated time are backend items.

### [x] 2. Ask AI polish and close step 10
- **Empty state:** match `ask-ai/empty-polish/ask-ai-empty-preview.html`.
  - One tools row inside the chooser: All / Datasets / Connections with counts, plus a "Mine" toggle. Remove the second filter row (Certified / Mine / test-looking). If "hide test-looking" must stay, make it a toggle in the same row.
  - Type tiles and a mode chip per row: Import, DirectQuery, Live. Under the chip, a relative updated time from the shared date formatter.
  - An accent bar on the active row, a bordered search with a focus ring and a "/" shortcut, and a one-line footer: key hints, then an outlined "Upload dataset".
  - An eyebrow with counts. The hero title at 40px, with three translated facts under it.
  - A neutral disabled Send button.
- **From `Ask AI Redesign v2.html`:** add only these two robot reactions. The robot looks toward the chooser while the pointer is over it, and does a happy bounce with a small burst when a dataset is chosen.
- Mark step 10 done in PLAN.md.

### [x] 3. Self-QA of Ask AI and the 7-QA6 fixes (Playwright, no code unless broken)
- **Ask AI** (with mocked AI responses in the browser): run each flow.
  - Empty state: chooser search, tabs, keyboard, and "Upload dataset".
  - Pick a dataset, then step 2.
  - Loading, then the answer: rows, SQL, Export, Copy, 👍/👎, Edit question, Retry.
  - The error card, and "agent unreachable".
  - The composer limit.
  - History: switch, rename and delete a scratch chat.
  - The robot states, and sleep after 20s.
- **7-QA6:**
  - Donut legend on a light-background widget in dark.
  - Data view numbers.
  - "-5" in condition boxes and the step editor.
  - Map strings in Arabic.
  - TLS option labels.
  - Template page names in Arabic.
  - The sunburst accepts levels by drop.
- Fix what's broken in one commit. Delete any scratch items you create.

### [x] 4. Lineage (step 11)
Follow `docs/redesign/11-Lineage.md`.
- Do Part 0 as a written table in the Progress log, without stopping.
- Then build it in two parts, each with its own commit:
  - **A:** graph, cards, edges, legend, toolbar, search, filters, issues only, pan/zoom/fit, mini-map.
  - **B:** focus mode (Upstream/Both/Downstream, 1 hop/All), side panel with impact, list view, keyboard navigation, empty/loading/error, dark, RTL mirrored, and Export PNG if it can be done on the client.
- Keep existing routes and deep links working.

### [x] 5. Upload redesign
- Design: `datalytics-archive/Upload Redesign.html`, prototype `redesign/upload.html` (`up.js`, `up.css`).
- Frames: landing, drag-over, review of one file (with a date warning), review of 3 files (combine on, one still uploading), import settings, importing, success, error.
- Keep the existing upload API and flows. Do Part 0 in the log, then build. Leave out what the API can't do; for example, if combining files isn't supported, drop that frame and record it as a backend item.

### [x] 6. AI button redesign
- Design: `datalytics-archive/AI Button Redesign.html`, prototype `redesign/assist.html` (`assist.js`, `assist.css`).
- What it shows:
  - The floating Ask AI button on dashboards: idle with an insight badge (only if real insights exist), hover pill with a tooltip, shrunk and semi-transparent while scrolling, open with suggestions, thinking, answer with a mini chart.
  - Draggable with the position remembered per user in local storage, opened with Ctrl+/, and hidden in Present.
  - RTL at the bottom-left.
- It is the existing copilot button; keep its behaviour (in Edit it's the page copilot) and the constraint that it never covers panels.

### [ ] 7. Connections redesign
- Design: `datalytics-archive/Connections Redesign.html`, prototype `redesign/connections.html` (`cn-core.js`, `cn-review.js`, `cn.css`).
- Frames:
  - List: default with failing and unstable rows, row ⋮ menu, empty, loading.
  - Add: type picker, form, test succeeded, edit with a failed test ("Fix" from the list).
  - Review: table preview, columns, query results, relationships, entities, business terms.
- It's the biggest step. Do Part 0 in the log, then build in two parts, each with its own commit:
  - **A:** list and add/edit/test.
  - **B:** review screens.
- Respect the teammate's flow: a new connection goes to `/setup/:id`. Keep the credential autofill protections from 7-QA5 F4.

### [ ] 8. 9-polish (small frontend items)
- Dashboards list: "Open in edit mode" in the ⋯ menu, and undo after a move.
- View hover menu: Drill down and Copy image, reusing the widget ⋮ actions.
- Home: a redesigned whole-page error state.
- Builder: a drag handle on the quick toolbar, and a rail count badge for open review findings.
- Datasets list: the health strip shown while loading.
- Dataset pages: a Models count on the overview, currency cell formats on the Data tab, Retrain on the Models tab, and type-ahead in the Share dialog.
- Quantity-column thousands grouping in the dataset grid, the Data view and the other data tables.

### [ ] 9. i18n-2: remaining English
- Pages and components: the dataset detail page, command palette, workspace tree, query builder, share dialogs, dataset side panels, and the guest page (SharedReport).
- Strings: any missing Setup strings, the measureTemplates names, the DashboardProposals language ternary, the HierarchyRenderer aria-label, and the ChecksPanel/TestResult units.
- Also any English that the new pages from steps 4–7 left behind.
- Extend the guards.

### [ ] 10. FINAL
1. **Flaky tests:** six files fail only in the full run (Lineage, PrepPipelinePanel, Reports, ReportBuilder, WidgetRenderer, geoRenderers). Find the shared cause (workers, timeouts under load, leaked timers/mocks/DOM) and fix it. The full suite must pass 3 runs in a row.
2. **Clean-up you may do:** remove all extra git worktrees, and stop any server you started on :3002.
3. **Clean-up that needs the owner (STOP and list, don't do):** QA test datasets 7 and 8, QA chats, dashboard #16, the "profit" column, and the uncommitted init.sql change.
4. **Regression:** one Playwright pass over every main page (Home, Dashboards, Builder, View/Present, Datasets, Ask AI, Lineage, Upload, Connections, Admin) in EN light and AR dark. Note any console errors and layout breaks, and fix the small ones.
5. **Docs:** update HANDOVER.md and PLAN.md for hand-off, including the full backend follow-ups list.
6. Then STOP with a summary of at most 20 lines. The owner will run a final QA and open the PR.

---

## Progress log

(Newest at the bottom. One entry per step, at most 10 lines.)

### 1. Ask AI Part D: history rail (2026-10-12)
- **Changed:** `HistoryPanel` restyled to the design: 288px on the inline end, "History" heading, outlined New chat, Today / Earlier, one row per thread (icon, title, creation time; Rename and Delete take the time's place on the row in hand), and a foot line. Overlay below 1180px with Hide history, the scrim and Escape.
- **Empty states:** "Pick a dataset to see its questions." (the rail now also stands on the empty page at ≥1180px, New chat off), "No questions yet for this dataset." and a connection wording for both the empty state and the foot line.
- **Translated:** the Rename / Delete labels and the title field were hard-coded English; `HistoryPanel.tsx` is in the guard.
- **Left out:** failed flags and last-activity time (already backend rows in PLAN.md). No new backend items.
- **Missing inputs noted:** `ask-ai/empty-polish/ask-ai-empty-preview.html` and `docs/redesign/11-Lineage.md` are not on disk. Steps 2 and 4 will follow this file's own text and the prototypes that exist (`redesign/ask2.*`, `hero2.*`, `lineage/`, `redesign/lin.*`).
- **Tests:** `askHistory.test.tsx` (7). Full suite 351 files / 4413 tests, one failure: the known flaky `Lineage.test.tsx`. Type-check and build pass.
- **Captures:** `redesign-captures/ap1-history/{before,after}/` (`cap_10d.mjs`, EN light and AR dark, 1440 and 1024).

### 2. Ask AI polish, step 10 closed (2026-10-12)
- **Changed (from this file's list; the preview file is not on disk):** one tools row in the chooser: All / Datasets / Connections with counts, then "Mine" and "Test data (n)" toggles; the old second filter row (Certified / Mine / test-looking) is gone from Ask AI. Rows: a tile and a mode chip per row (Import, DirectQuery, Live) with the relative updated time from the shared `formatTimeAgo` under it; an accent bar on the active row. A bordered search with its own focus ring and a "/" shortcut; a one-line footer (key hints, outlined Upload dataset). The hero: an eyebrow with counts, a 40px title, three translated facts. Send was already neutral when disabled.
- **Decision:** "Certified" is dropped from the Ask AI chooser (not in the list); certified datasets still sort first. The Mine / test toggles are page state, not the shared remembered filter.
- **Robot (from Ask AI Redesign v2):** an idle robot looks toward the chooser while the pointer is over it; choosing data gives a short happy bounce with a spark burst (not confetti).
- **Backend items:** none new. **Tests:** chooser polish (6), robot reactions (2); full suite 351 files / 4421 tests pass; type-check and build pass.
- **Captures:** `redesign-captures/ap2-polish/{before,after}/` (`cap_10d.mjs` `no-data`, `polish-*`).

### 3. Self-QA of Ask AI and 7-QA6 (2026-10-12)
- **Ask AI:** `e2e/capture/redesign/qa_ap3_ask.mjs`, 39 checks with faked model answers: chooser (search, tabs, keys, "/", Upload), step 2, loading → answer (rows, SQL, Export, Copy, 👍, Edit question, Retry), error card and unreachable, the composer limit, History (switch, rename, delete a scratch chat through the real API; it is deleted), robot typing / thinking / happy / calm / sleep / wake. 39 / 39 after the fix.
- **Broken and fixed:** the Export menu closed as soon as it opened when a smooth scroll was still settling (the shared `ActionMenu` closed on any scroll while portalled). It now follows its button and closes only when the button leaves the window (+1 test).
- **7-QA6, re-run with `cap_qa6.mjs`:** A1 donut key dark-on-light in dark ✓, A2 Data view numbers ✓, A3 "-5" reads LTR in Arabic boxes ✓, A4 map strings in Arabic ✓, A6 TLS labels ✓, A10 template names in Arabic ✓, B2 sunburst levels by drop ✓. Its QA6- scratch dashboards were deleted by the script (checked: none left).
- **Not real issues:** a 404 on 👍 in the faked thread (the fake conversation id does not exist on the server).
- **Tests:** full suite 351 files / 4422 pass; type-check and build pass. **Captures:** `redesign-captures/ap3-selfqa/{ask,qa6}/`.

### 4. Lineage, step 11 (2026-10-12)
- **Part 0 (the brief `11-Lineage.md` is not on disk; from this file, the canvas and `redesign/lin.js`):** graph, cards, edges, search, filters, issues, pan/zoom/fit, mini-map, focus, side panel, list, keys, states, RTL, dark = **frontend only** (all from `GET /datasets/lineage/graph`). Owner filter and owner/created/rows in the panel = **needs backend** (not in the graph). A source's connection status (dot, "broken source") = **needs backend**. Export PNG = **frontend** (client SVG → canvas). Test connection in the panel = left out (exists on Connections).
- **A (`e66ae7d`):** canvas that pans, zooms (wheel and buttons) and fits; column heads in view; legend; mini-map that moves the view; cards with type, mode chip, steps and issue icons; edges fanned per card, joins / derivations dashed, red out of a failing dataset, labels on hover; "+ N more" folding; search with results that centres and pulses; Node type / Source type / Mode / Issues only fade; the design's empty state. Uploaded datasets hang off one "Uploaded files" source.
- **B:** focus bar (Upstream / Both / Downstream, 1 hop / All); side panel (impact, type, refresh, steps, status, feeds from, used by, Open, Ask AI); List view with chains; arrow-key moves; loading skeleton; `?focus=ds:5` deep link (Overview now links to it); Export PNG verified in Chromium. Route `/lineage` unchanged.
- **Decisions:** reports have no "Ask AI about this" (Ask AI takes a dataset or connection). Upload datasets show no "Last refreshed". The old direction-flip test is gone with the measured layout (layout is computed now).
- **Backend items added:** owner, creation date and row count per lineage node; a connection's status in the lineage graph.
- **Tests:** Lineage page (19), model and export (5), string guard; full suite 353 files / 4439 pass; type-check and build pass. **Captures:** `redesign-captures/ap4-lineage/{before,after,design}/`.

### 5. Upload (2026-10-12)
- **Part 0:** landing, drag-over, review, combine (batch "append"), sheet choice, importing, success, error = **frontend only** (existing `POST /datasets` and `/datasets/batch`). Preview before import = **frontend** for CSV/TSV/JSON (read in the browser from the reader's own file), **needs backend** for Excel/Parquet/XML/Access. Change a column's type, header/delimiter/encoding/date-format settings, "Try a sample dataset", per-file upload status, "Up to N MB" = **needs backend** (left out). Recent uploads = existing dataset list (datasets with a file).
- **Changed:** three steps (Choose files → Review → Import); drop zone + Browse, database card, Recent uploads and Tips; review with file rows, a name from the file, description, Combine switch, first 20 rows with type hints, row / column / empty-cell counts and a day/month date warning; the real upload progress (two added API calls with `onUploadProgress`), then "Saving"; a success card (Open, Ask AI, Build a dashboard, Upload another) and an error card (per-file errors, Technical details, Try again, Choose another file).
- **Decision:** after a single import the page shows the success card instead of jumping to the dataset (the design); Open keeps `?new=1`. "Keep this page open" instead of the design's "you can leave this page" (the upload runs in the page).
- **Backend items added:** previews of Excel/Parquet/XML/Access before import; import settings (types, header, delimiter, encoding, date format); a sample dataset; per-file upload status in a batch.
- **Tests:** Upload page (24), reader (4), string guard; full suite 355 files / 4442 pass; type-check and build pass. **Captures:** `redesign-captures/ap5-upload/{before,after,design}/` (`cap_ap5.mjs`, browser-only routes: nothing uploaded).

### 6. AI button (2026-10-12)
- **Changed:** the View-mode Ask AI button is `components/ai/AskFab`: the mascot on a round accent button that breathes (a ring that grows and fades) and blinks; on hover or keyboard focus it opens into an "Ask AI" pill with a tooltip "Ask AI about this dashboard Ctrl /"; it shrinks and fades while the canvas scrolls; it can be dragged to any of the four corners, remembered per user in this browser. Arabic puts it bottom-left (logical corners). The View canvas gets 88px of bottom room so no widget has to stay under it.
- **Kept:** it opens the page's existing AI panel beside the dashboard (never over other panels); Ctrl+/ toggles it (the page's handler); hidden in Present (checked) and in Edit, where the page copilot is used.
- **Left out:** the "new insight" badge (knowing whether new insights exist needs a scan; backend row: an insight count). The design's own pop-over panel states (suggestions, thinking, mini chart) are the existing panel's, unchanged.
- **Tests:** AskFab (3) plus the builder's existing button tests; full suite 356 files / 4445 pass; type-check and build pass. **Captures:** `redesign-captures/ap6-ai-button/{before,after}/` (`cap_ap6.mjs`).
