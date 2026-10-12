# Datalytics redesign: handover

Written 2026-10-06, brought up to date 2026-10-12 at the end of the autopilot run.
For anyone picking the work up without the earlier sessions. Read this first, then
`AUTOPILOT.md` (the last work order and its progress log), then `PLAN.md` (the Log of
every earlier step and the backend follow-ups table).

## 1. Where we are

- **The frontend redesign is done (Phase 1, no backend changes).** Every step in
  `PLAN.md` and `AUTOPILOT.md` is ticked, FINAL included.
- **Redesigned:** Datasets (list, detail, all tabs, Share), Home, Dashboards list,
  Share / Export / Version history, View and Present, Builder, Ask AI (with the robot
  and the history rail), Lineage, Upload, the floating Ask AI button, Connections
  (list, drawer, review page), plus the 9-polish items. Arabic covers all of these and
  the shared components (i18n-2).
- **Next:** the owner's final QA, then the owner opens the PR from `said` to `main`.
  Nothing is in progress.
- **Last commits on `said`** (newest first; the owner pushes):

  | Commit | What |
  |---|---|
  | (newest) | FINAL docs: this handover, PLAN.md, AUTOPILOT.md |
  | `42149f0` | step 10A: the flaky full-run tests |
  | `40d6965` | step 9: i18n-2 remaining English |
  | `d9e9e4b` | step 8: 9-polish |
  | `14d1f5f` / `f15c78b` | step 7: Connections |
  | `c4e49b3` · `eda59e5` · `08651bd` / `e66ae7d` | steps 6, 5, 4: AI button, Upload, Lineage |

## 2. Decisions the owner made (all still in force)

**Process**
- **Branch:** work directly on `said`. Never create another branch.
- **Rollback point:** the pre-redesign commit is tagged `before-redesign` (`587b217`).
- **Commits:** commit after each sub-step. **Never push.**
- **PLAN.md:** after each sub-step, tick it and add a log entry (what changed, commit
  hashes, deviations from the design and why). Stop at every GATE line for the owner's
  review.
- **Stop immediately (don't wait for a gate)** if:
  - something needs sudo or the owner's password (tell them the exact command);
  - a test fails that can't be fixed without touching the handoff's "must stay
    untouched" areas;
  - a change would need backend work.
- **Small design questions:** pick the option closest to the design, log it, continue.
- **Before committing a step:** the step's tests, full `npm test`, `npm run build`,
  rebuild the containers, then capture the affected screens in **light, dark, Arabic,
  Arabic dark**. Compare them against the design, and fix differences or log why they
  were kept.
- **Phase 1 rule** (handoff): ship only what v1 already does, plus items whose data
  already exists. Anything needing new backend work is left out: never a placeholder,
  "coming soon" or empty slot. Backend-needed items go into PLAN.md's "Backend
  follow-ups" table.
- **Must stay untouched** (handoff): sidebar, top bar (`TopBar`, `LlmPicker`,
  `NotificationsBell`, `LanguageSwitcher`), existing API functions in
  `services/api.ts` (additions allowed for endpoints that already exist), business
  logic (permissions, RLS/CLS, quotas/429, autosave, undo, evidence tracing, export
  generation), and all backend code.

**Design and visual**
- **Theme and design system stay as they are.** Use the existing tokens (`--mc-*`,
  `--dl-*`, `datalytics.css`); don't restyle globally.
- **Sidebar and top bar:** keep v1's exactly (items, order, grouping, collapse button);
  only page content changes.
- **Every screen needs:** dark mode, Arabic RTL (light and dark), and its states (full,
  first run, empty, loading, error).
- **Charts in RTL:** keep v1 behaviour (mirrored layout via
  `chartRenderers/axisOptions.ts`, LTR legend). The old "chart internals stay LTR" note
  in the design-system manifest is outdated.
- **Model-written text:** direction comes from the text's own majority script
  (`lib/autoDir.ts` `majorityDir`), not `dir="auto"`. Values inside sentences are
  bidi-isolated (U+2066 … U+2069), and digits go through `localDigits`.
- **Builder:** must allow manual arrange/resize and be fully usable with the AI server
  down; the copilot is optional. (Carry this into the new Dashboards designs unless the
  owner says otherwise.)
- **Earlier design work** was done on a Claude canvas, for reference only. Home, Viewer
  and Builder are now superseded by the new design project.
  - Redesign canvas: https://claude.ai/artifact/MjHt9gMNTq79GfjVKA25pu
  - Design system "Datalytics v1 (baseline)": https://claude.ai/artifact/AzngmVqgLTANt829CbT5ky
  - The owner had approved "variation C" (Merged v2) for Home, Builder and Viewer, and
    the "Merged — Datasets" design.

**Step by step**
- **Step 1:** approved.
  - Commit `e2e/capture/` and the Arabic / chart / Show SQL / clarification captures,
    and fix the README.
  - Discard the `package-lock.json` change.
  - Leave the uncommitted `init.sql` edit alone.
- **Step 2:** approved, including the colours and the "Left out" wording.
- **Step 3:** split into 3a, 3b and 3c; all three approved, including every choice
  logged in PLAN.md.
- **GATE A:** approved, including:
  - Automatic analyses (segments, patterns, key influencers) start only when the
    Analysis tab is opened. The dev server is single-process and they blocked other
    tabs.
  - Two extra Analysis questions kept from v1: "What stands out?" and "What looks
    unusual?".
  - No "Retrain" button on Models (training again under the same name already makes a
    new version).
  - Backend-needed items logged in PLAN.md: Data tab CSV download, changing a share
    grant's level in place, and the row-security rules count in Share.
- **Ask AI (2026-10-06): the owner rejected the built step 4 visual redesign.**
  - The page keeps v1's layout and look (as at commit `120e0ef`). The step 4 boards in
    `boards/step4-ask-ai-phase1/` are no longer the spec. Do not re-propose that
    redesign.
  - Kept from step 4, in v1's look:
    - translations of all the chat's hardcoded English;
    - Pending without the timer-driven fake stages;
    - the app's themed delete dialog instead of `window.confirm`;
    - offline detection from the top bar's `/llm/endpoints` poll (`llmApi.endpoints`
      broadcasts each answer, so there's no second poller). While the model is down,
      v1's question box is locked with "New questions are paused while the model server
      is unreachable" and one line above it, with no banner. The report-builder mount
      never locks.
    - "Use <column>" chips on a clarification, for the columns the reply names in
      bold, code or quotes (`components/chat/clarifyColumns.ts`);
    - a "What was wrong?" field after 👎, sent as the feedback `comment`;
    - an Edit question button beside Retry on an error.
- **Datasets menu clipping (2026-10-06):** fixed and audited on every Datasets screen,
  in English and Arabic.
  - Row menu fix: `7b50e5c`.
  - ActionMenu bottom-edge fix: `8818373`.
  - Header refresh popup at narrow widths: `c99a7c3`.
- **GATE B (2026-10-06): approved.** Datasets and Ask AI are done and stay as
  implemented. Steps 5 and 6 are replaced by the new design project (section 1). The
  theme and design system stay.
- **Keep until FINAL:** test datasets 7 ("Student cohorts (test)") and 8 ("ID only
  (test)"). FINAL has passed; they now wait for the owner (section 7).
- **Autopilot (2026-10-12):** thousands grouping for quantity columns only; the Builder
  canvas is not mirrored in Arabic; dashboards open in View; Present auto-play starts
  off; never change the teammate's features (Guided setup, HierarchyRenderer/Sunburst,
  condition boxes, no-code formulas) beyond integration and translation.
- **The owner's uncommitted edits** to `docker-compose.yml` and `docker-compose2.yml`
  (the `init.sql` mount removed) are theirs. **Never stage or commit them.**

## 3. Environment

**Drive and folders**
- **Repo:** `/media/saeed/New Volume2/projects/data_analysis_dashboard_ai-`.
  - The app is under `AI_data_tool/data_analytics/`: `frontend/`, `backend/`,
    `docker-compose.yml`.
  - The drive's mount name has changed with reboots ("New Volume1", now
    **"New Volume2"**). Older notes and logs name "New Volume1"; read them as the
    current mount.
- **Don't delete the leftover `/media/saeed/New Volume` folder.** Docker left it as an
  empty, root-owned skeleton (not a git repo). The owner wants it kept.
  - Check you're in the real repo with `ls -d <path>/.git`.
- **Captures** are outside the repo, in `/media/saeed/New Volume2/projects/redesign-captures/`.

**Docker**
- **Run `docker compose down` before shutting the machine down** (from
  `AI_data_tool/data_analytics`).
- **Start or rebuild:** `docker compose up -d --build` from `AI_data_tool/data_analytics`.
  A rebuild takes a few minutes, and the containers restart during it.
- **Ports:**
  - App: http://localhost:3001. Vite dev server; `frontend/src` is bind-mounted, so
    source edits show live.
  - API: http://localhost:8000.
- **Docker group:** the user `saeed` is in the `docker` group, and plain `docker` works.
  If it ever says "permission denied" (a shell started before the group was added),
  run `sg docker -c "docker …"`, or log out and back in. Don't use sudo.
- **The backend is a single-process dev uvicorn:** a heavy request (an analysis) holds
  up the others.

**Node**
- Node 20 comes from **nvm**, and the agent's shell doesn't read `~/.bashrc`. Prefix
  commands with `source ~/.nvm/nvm.sh && …`.
- From `frontend/`:
  - `npx vitest run` (359 files, 4480 tests, about 75 s; green three runs in a row);
  - `npm run build` (runs `tsc` first);
  - `npx tsc --noEmit -p .`.

**A second dev server** (for "before" captures or a branch check)
- Start it with `VITE_API_URL=same-origin npx vite --port <port>`. Without that the
  page calls :8000 directly and the backend's CORS refuses any port but 3000/3001.
- A git worktree with a symlinked `node_modules` loads React twice in dev mode (a blank
  page). Build it instead: `VITE_API_URL=same-origin npx vite build && npx vite preview --port <port>`.
- The Analysis tab waits about 8 s for `/analysis/registry`; give a capture that long.

**Login and other notes**
- **Seeded login** (local test credentials, also in the repo's CLAUDE.md):
  `admin@datalytics.local` / `demo-password`.
- **No AI model is assumed.** The captures use browser-only fake data (Playwright
  `page.route`), so they don't depend on a live model.

## 4. Code map (what the redesign added)

- **i18n:** `src/i18n/en.ts` and `ar.ts` through `useT()`. Every new string goes in both.
- **Shared helpers:**
  - `lib/inlineMarkup.tsx`: markdown-ish bold/links in model text.
  - `lib/displayNumber.ts`: `formatProseNumber`, `formatCell`, `readingValue`.
  - `lib/autoDir.ts`: `majorityDir`.
- **Datasets list:** `pages/Dashboard.tsx` (route `/datasets`) with
  `pages/datasetsList/` (`classify.ts`: `typeName`, `sourceKind`, `sourceWords`, …;
  `datasetsList.css`).
- **Dataset detail:** `pages/DatasetDetail.tsx` with `pages/datasetDetail/`.
  - `constants.ts`: tabs and `tabFromKey`.
  - `Overview.tsx`.
  - `columnProfile.tsx`: `useColumnProfile`, `typeTag`, `RangeBar`.
  - `AnalysisNav.tsx`: question groups and `HASH_PICK`.
  - Per-tab css.
- **Dataset panels:** in `components/dataset/` (ColumnMeaningPanel, ChecksPanel,
  AlertsPanel, PredictionModelsPanel, AggregatesPanel) and
  `components/DatasetShareDialog.tsx`. `StatisticsPanel` gained an `only` prop.
- **Ask AI:**
  - Page: `pages/AskAI.tsx` and `pages/ask/` (v1, plus `useAiOffline.ts`).
  - Chat: `components/chat/` (ChatPane, Pending, ResultView, ChoiceOptions,
    `clarifyColumns.ts`).
- **Shared components:**
  - `components/ActionMenu.tsx`: use `portal` (and `align="end"`) for a menu inside
    anything that clips or scrolls, such as table cards.
  - `components/ui/ConfirmDialog` (`useConfirm`).
  - `components/ai/AskFab.tsx`: the floating Ask AI button (View mode).
- **Autopilot pages:** `pages/lineage/` (`model.ts` pure graph logic, `Graph.tsx`,
  `SidePanel.tsx`, `ListView.tsx`, `exportPng.ts`), `pages/upload/readFile.ts`
  (browser-side preview), `pages/Connections.tsx` with `pages/connections/`.
- **i18n page files:** `src/i18n/pages/*.ts`, spread into `en.ts` / `ar.ts` (Ask AI,
  Lineage `lin2.*`, Upload `up2.*`, Connections `cn2.*`, polish `pol.*` / `mt2.*`,
  i18n-2 `i2d.*` and `i2c.*`). Plurals use `{n, plural, …}` with Arabic forms through
  each file's `arCount`; an English plural branch must not start with a word.
- **Guards:** `src/test/hardcodedStrings.ts` with one `strings.*.test.ts` per area
  (`// i18n-ok` exempts a line that must stay as it is, such as code samples).
- **Numbers in tables:** `lib/displayNumber.ts` `formatTableCell` (column format, else
  grouped quantities; never years or ids).
  - `components/ui/PromptDialog`.
  - Tests render through `test/renderWithProviders.tsx`.

## 5. Capturing and checking screens

- **`frontend/e2e/capture/capture_screens.mjs`:** the full 106-screen capture.
  - Always pass `--out <dir>`. Its default writes to
    `/media/saeed/New Volume1/projects/screenshots_2/`, the owner's reference set,
    which must not be overwritten.
- **`frontend/e2e/capture/redesign/`:** scripts used during the redesign. Each takes an
  output folder; set `ONE=1` for light theme only.
  - `cap_step3b.mjs`, `cap_step3c.mjs`: dataset detail tabs (some with fake checks and
    aggregates).
  - `cap_ask_both.mjs`: Ask AI in 8 states × 4 themes with fake conversations; an
    optional second argument picks states.
  - `audit_menus.mjs`: clicks every popup trigger on the Datasets screens (English and
    Arabic) and reports any popup that is clipped, covered or off-screen; `W=900` for
    a narrow window.
  - `audit_refresh.mjs`: the dataset header's refresh popup (fakes an imported
    dataset).
  - Autopilot: `cap_10d.mjs`, `qa_ap3_ask.mjs` (39 checks), `cap_ap5.mjs` …
    `cap_ap9.mjs` (one per step), and `reg_final.mjs` (every main page, EN light +
    AR dark: console errors, page errors, 5xx calls, sideways overflow).
  - Run them with `source ~/.nvm/nvm.sh && BASE=http://localhost:<port> node frontend/e2e/capture/redesign/<script> <outdir>`.
- **Saved preferences:** the scripts log in through the UI and set
  `localStorage` `theme`, `datalytics.language` and `datalytics.direction` before
  loading a page.
- **Design boards** for the finished steps are in `docs/redesign/boards/`. The new
  Home/Dashboards and Ask AI designs used are in `projects/design-handoff-2/` and
  `design-handoff-3/` (next to the repo on the same drive).

## 6. Known flaky tests

- **None now.** The six files that failed only in a full run waited on heavy renders
  with Testing Library's default 1s. `src/test/setup.ts` now allows 5s
  (`asyncUtilTimeout`), `vitest.config.ts` 20s per test, and the URL-line checks in
  `Reports` / `Home` retry. Three full runs in a row passed (`42149f0`).
- **If one fails again,** re-run the file alone, then look for a check that reads
  something already on the page once (`expect(await findBy…).toHave…`) instead of
  waiting for it to change.

## 7. Clean-up that needs the owner (not done)

- **Test datasets 7** ("Student cohorts (test)") **and 8** ("ID only (test)").
- **QA chat threads** in Ask AI.
- **Dashboard "QA3-Builder" #16** (not made by a QA run; the owner decides).
- **The "profit" column** the QA runs met.
- **The uncommitted `init.sql` change** and the `docker-compose.yml` /
  `docker-compose2.yml` edits: the owner's, never staged.
- **Seen in the final pass, left as is:** in View and Present, widgets inside a
  container (tab group) keep their own grid slots empty (original code; see the FINAL
  entry in PLAN.md).

## 8. What to do next

- The owner's final QA, then the PR from `said` to `main`.
- **Backend phases:** the full list of backend follow-ups is the table in `PLAN.md`
  ("Backend follow-ups"), one row per item found during the frontend steps, the
  autopilot's included (Lineage, Upload, AI button, Connections).
- **Still English, outside every list so far:** `FolderShareDialog` and the embed page
  (`EmbeddedReport`) have no translation hook yet.
