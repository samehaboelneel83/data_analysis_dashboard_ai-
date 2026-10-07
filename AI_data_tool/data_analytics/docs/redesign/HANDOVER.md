# Datalytics redesign: handover

Written 2026-10-06 for a new Claude session, on another account, that cannot see the
previous session or its saved memory notes. Read this first, then `PLAN.md` (its Log
section has the details of every step), then `DATALYTICS_REDESIGN_HANDOFF.md`.

## 1. Where we are

- **Steps 1, 2, 3a–3c, 4a, 4b and 4-revert are done.** GATE A and GATE B are approved.
- **Datasets** (list and detail, all tabs, Share dialog) and **Ask AI** are finished and
  stay as implemented.
- **Ask AI uses the v1 layout and look, with fixes.** It does not use the step 4 boards
  (see section 2).
- **Steps 5 and 6 (Home, Viewer, Builder) are cancelled in their current form.** They
  will be replaced by designs from another Claude Design project, "Home Redesign" and
  "Dashboards Parts 1–4". Those will be exported to
  `/media/saeed/New Volume1/projects/design-handoff-2/`. Nothing there yet means: wait.
- **After that come** Upload, Connections, Lineage and the AI button.
- **No step is in progress.** Do not start one until the owner says so and the new
  designs are in `design-handoff-2/`.
- **Last commits on `said`:**

  | Commit | What |
  |---|---|
  | `c99a7c3` | Refresh popup fix + PLAN |
  | `8818373` | Ask AI back to v1 |
  | `7b50e5c` | Datasets row menu fix |
  | (newer) | This handover |

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
  (test)").
- **The owner's uncommitted edits** to `docker-compose.yml` and `docker-compose2.yml`
  (the `init.sql` mount removed) are theirs. **Never stage or commit them.**

## 3. Environment

**Drive and folders**
- **Repo:** `/media/saeed/New Volume1/projects/data_analysis_dashboard_ai-`.
  - The app is under `AI_data_tool/data_analytics/`: `frontend/`, `backend/`,
    `docker-compose.yml`.
  - The drive mounts as **"New Volume1"** since a reboot on 2026-10-06.
- **Don't delete the leftover `/media/saeed/New Volume` folder.** Docker left it as an
  empty, root-owned skeleton (not a git repo). The owner wants it kept: it keeps the
  drive mounting at "New Volume1".
  - Agent sessions may start with their working directory set to that old path. Always
    use absolute "New Volume1" paths.
  - Check you're in the real repo with `ls -d <path>/.git`. The mount name could change
    after another reboot.

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
  - `npx vitest run` (about 278 files, 3688 tests);
  - `npm run build` (runs `tsc` first);
  - `npx tsc --noEmit -p .`.

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
  - Run them with `source ~/.nvm/nvm.sh && node frontend/e2e/capture/redesign/<script> <outdir>`.
- **Saved preferences:** the scripts log in through the UI and set
  `localStorage` `theme`, `datalytics.language` and `datalytics.direction` before
  loading a page.
- **Design boards** for the finished steps are in `docs/redesign/boards/`. The new
  Home/Dashboards designs will arrive in `/media/saeed/New Volume1/projects/design-handoff-2/`.

## 6. Known flaky tests

- **`src/pages/Lineage.test.tsx`**, "re-draws the edges when direction flips on a
  MOUNTED page": fails now and then in the full run, and passes alone. Fixing it is
  scheduled for FINAL.
- **`src/components/report/chartRenderers/geoRenderers.test.tsx`:** failed to *load*
  once in a full run (2026-10-06), then passed alone and on the next full run. Watch it.
- **If a full run fails only on these,** re-run the file alone before treating it as
  real.

## 7. Clean-up list for FINAL

- Test datasets 7 and 8.
- Test chat threads.
- The owner's uncommitted `init.sql` / docker-compose edits: ask the owner, don't touch.
- `frontend/src/pages/ask/AskIllustration.tsx` is still used (v1 hero). The unused
  `.dl-ask--hero` CSS note in the 4b log no longer applies, because the revert brought
  the hero back.
- Fix the flaky `Lineage.test.tsx`.
- Backend follow-ups (PLAN.md table) are for the backend phases, not FINAL.

## 8. What to do next

Nothing until the owner asks. When they do, the likely first task is to read
`/media/saeed/New Volume1/projects/design-handoff-2/` (Home Redesign, Dashboards
Parts 1–4), propose sub-steps for PLAN.md with gates in the same style, and wait for
approval before coding.
