# Datalytics redesign — implementation handoff

For: Claude Code working in `AI_data_tool/data_analytics/` (read the repo's `CLAUDE.md` first).
Written: 5 Oct 2026. Covers everything approved on the design canvas so far.

- **Design boards as PNG: `design-handoff/boards/`, one folder per step. These images are the spec.** Each step lists its folder.
  - File names read `<screen>-<state>-<theme>.png`. Themes are `light`, `dark`, `ar` (Arabic, RTL) and `ar-dark`.
  - Every image is 1440 × 1000.
  - They were rendered from the canvas components. If a PNG and this text disagree, the text wins; tell the owner about the mismatch.
- Design canvas (for the owner; Claude Code can't open it): https://claude.ai/artifact/MjHt9gMNTq79GfjVKA25pu. Canvas page names are given next to each folder.
- Design system (v1 baseline): https://claude.ai/artifact/AzngmVqgLTANt829CbT5ky
- Original screenshots: `../../design-screenshots/` (first capture) and `../../screenshots_2/`

Paths below are relative to `AI_data_tool/data_analytics/`. `FE` = `frontend/src`, `BE` = `backend/app`.

---

## 0. Rules for every step

### What must stay untouched

| Area | Files | Rule |
|---|---|---|
| Sidebar | `FE/components/Layout.tsx`, `FE/components/navigation.ts`, the `.dl-rail*` CSS in `FE/index.css` | Same items, order, grouping and collapse button. No edits. |
| Top bar | `FE/components/TopBar.tsx`, `LlmPicker.tsx`, `NotificationsBell.tsx`, `LanguageSwitcher.tsx` | No edits. |
| API calls | `FE/services/api.ts` | Keep every existing function, path, parameter and response type. You may **add** client functions for endpoints that already exist on the backend, listed per step. Never invent an endpoint in a frontend step. |
| Business logic | Permissions (`ProtectedRoute`, `RequireAdmin`, capability checks), RLS/CLS, quotas and 429 handling, autosave, undo, conflict merge, cross-filter, evidence tracing, export generation | Restyle and recompose the UI around them. Do not rewrite them. |
| Backend | `BE/**` | No backend changes in steps 1–6. Backend work is in section 7. |

### Phase 1 rule

Phase 1 ships only what v1 already does, plus items whose data already exists ("B" / "AB" items). If something in a design needs new backend work, it is **left out**. Never show a placeholder, "coming soon", or an empty slot. The canvas has a "Phase 1" board for each screen. Build that version, not the "gaps marked" one.

### Tokens: canvas name → product variable

The canvas uses short names. Map them like this (`FE/styles/datalytics.css`, `FE/styles/mcait/*.css`):

| Canvas | Product |
|---|---|
| `--bg` / `--bg2` | `--mc-canvas` / `--mc-canvas-2` |
| `--surface` | `--mc-surface` |
| `--ink` / `--ink2` / `--muted` / `--faint` | `--mc-ink` / `--mc-ink-soft` / `--mc-muted` / `--mc-faint` |
| `--line` / `--line2` / `--line-strong` | `--mc-border` / `--mc-border-2` / `--mc-border-strong` |
| `--accent`, `-h`, `-soft`, `-line`, `-ink`, `--on-accent` | `--mc-accent`, `--mc-accent-hover`, `--mc-accent-soft`, `--mc-accent-line`, `--mc-accent-ink`, `--mc-accent-fg` |
| `--pos` / `--warn` / `--neg` / `--info` (+ `-soft`, `-line`) | `--mc-success` / `--mc-warning` / `--mc-danger` / `--mc-info` (+ `-soft`, `-line`) |
| `--s1` … `--s8` | `--dl-series-1` … `--dl-series-8` |
| `--bar-quiet` (non-highlighted bars) | `--dl-series-null` if it reads right; otherwise add `--dl-bar-quiet` to `datalytics.css` with light and dark values |
| `--r-card` / `--r-ctl` / `--r-badge` | `--dl-radius-card` / `--dl-radius-control` / `--dl-radius-badge` |
| `--shadow-card` / `--shadow-pop` | `--dl-shadow-card` / `--dl-shadow-overlay` |

Dark mode uses the product's existing dark theme (`data-theme="dark"`). Don't add new dark values except `--dl-bar-quiet` if you create it. Fonts are already the product's: Inter, IBM Plex Sans Arabic, JetBrains Mono.

### RTL rules (all screens)

1. **Charts keep v1 behaviour exactly** (`FE/components/report/chartRenderers/axisOptions.ts`):
   - x-axis reversed
   - y-axis on the right
   - axis titles and margins swapped
   - legend wrapper `direction: ltr`
   - `svg.recharts-surface { direction: ltr }`
2. **Fix the outdated note.** The comment at `FE/styles/datalytics.css:236` ("Chart internals stay LTR; the surrounding layout flips") and the MANIFEST's 13-themes-08 note are wrong. Correct them to: only the SVG surface and the legend wrapper stay LTR.
3. **Direction of model-written text** comes from the text itself, by **majority script** (see step 1c). Do not use `dir="auto"` (first strong character) or the question's language. User-typed text, such as questions and titles, keeps `dir="auto"`.
4. Wrap data values and numbers inside sentences with `unicode-bidi: isolate`. Numbers already get `dir="ltr"` marks.
5. Every new string goes in both `FE/i18n/en.ts` and `FE/i18n/ar.ts`.

### Verifying every step

- `cd frontend && npx vitest run <the test files named in the step>`, then the full `npm test`.
- `npm run build`. This runs `tsc`, so type errors fail it.
- Browser QA on the dev stack (http://localhost:3001; log in as described in `CLAUDE.md`). Follow the matching section of `qa/TEST_PLAN.md` and check:
  - English and Arabic, light and dark
  - every state on the canvas boards for that screen
  - the console stays clean
- Compare the running screen side by side with the PNGs in that step's `boards/` folder: same state, same theme, same direction.

---

## 1. Ask AI quick fixes on v1 (no layout change)

**Boards (PNG):** `design-handoff/boards/step1-ask-ai-quick-fixes/`:
- `v1-before-clarification-raw-markdown.png` and `v1-before-answer-raw-floats-table-only.png`: the original v1 captures showing the bugs.
- `target-answer-formatted-light.png` and `target-answer-direction-ar.png`: how formatted numbers, rendered bold and RTL direction should look. They come from the step 4 design; step 1 keeps v1's layout and only borrows those details.

Goal: fix the four v1 defects inside the current Ask AI layout. The redesign comes later, in step 4.

### 1a. Render markdown

- **Problem:** raw `**faculty**` shows. `FE/components/chat/AnswerText.tsx` renders plain text on purpose (docstring :12). The clarification is a bare `<p>{msg.text}</p>` at `FE/components/chat/ChatPane.tsx:487`.
- **Change:**
  - Move `renderInlineEmphasis` and `renderTextWithLinks` out of `FE/components/report/WidgetBody.tsx:96-117` into a new `FE/lib/inlineMarkup.tsx`, and re-import them in WidgetBody.
  - Use them in AnswerText, the clarification at ChatPane:487, and the error message text.
- **Watch out:** evidence claims carry `start`/`end` offsets into the **raw** answer string, markers included.
  - Compute the emphasis ranges on the raw text first.
  - Render segments by merging the claim ranges with the emphasis ranges, so a traced number inside `**…**` stays a traced button and is shown bold.
  - Never strip the markers before applying the claim offsets.
- **Tests (new: `components/chat/AnswerText.test.tsx`):**
  - `**faculty**` renders `<b>faculty</b>` with no asterisks.
  - A traced number inside bold is still a button.
  - Links only render for `https://`.

### 1b. Format numbers

- **Problem:** the model writes `61.53500000000001` and the grid shows `83.8883333333`.
  - Backend snapshots keep raw floats.
  - `cellText` (`FE/components/chat/ResultView.tsx:58-62`) rounds to 12 significant digits.
- **Change:**
  - Add `FE/lib/displayNumber.ts`:
    - `formatProseNumber(token)` for numbers in sentences and chart value labels:
      - Only touch tokens with **more than 2 decimal places**.
      - Round to 1 dp when |v| ≥ 10, 2 dp when 1 ≤ |v| < 10, and 3 significant digits below 1.
      - Keep `%` and sign.
      - Leave integers and anything already ≤ 2 dp alone. That covers years, ids and "1,234.5".
    - `formatCell(v)` for the grid: non-integer floats get at most 2 dp (3 significant digits below 1). **Integers stay exactly as they are, with no thousands separators.** That keeps the existing rule in the comment at ResultView.tsx:55 (ids and years).
    - Both functions pass their output through `localDigits` (`FE/lib/arabicFormats.ts`).
  - In AnswerText, apply `formatProseNumber` to each `NUM` match (regex at :19) **at render time only**. The evidence offsets still point at the raw text.
  - In ResultView, use `formatCell` for display.
- **CSV and Excel (decided by the owner): exports keep full precision.**
  - `toCsv` (ResultView.tsx:137) writes the raw values, not `cellText`/`formatCell`.
  - Replace the comment at :138 ("an export that disagrees with the screen…") with: "Exports carry raw values at full precision; the screen rounds for reading."
  - The Excel/PDF export comes from the backend snapshot (`GET /agent/runs/{id}/export`) and is already raw. Leave it alone.
  - Add a test: `toCsv` of `61.53500000000001` contains `61.53500000000001`.
- **Tests:**
  - `ResultView.cellText.test.ts` (display only; exports are covered above): `61.53500000000001 → "61.54"`, `83.8883333333 → "83.89"`, `2024 → "2024"`, `0.123456 → "0.123"`.
  - New `displayNumber.test.ts`: the prose token `61.53500000000001 → "61.5"`. `"1,234.5"` and `"2025"` are unchanged.

### 1c. Text direction from the answer text

- **Problem:** `dir="auto"` uses the first strong character. An Arabic answer that starts with a data value ("Medicine الأعلى بمتوسط 83.9…") is laid out LTR.
- **Change:**
  - Export `RTL_CHAR` and `LTR_CHAR` from `FE/lib/autoDir.ts`.
  - Add `majorityDir(text, fallback)`: count Arabic/Hebrew letters against Latin letters. Return `'rtl'` or `'ltr'` for whichever is larger, and `fallback` (the UI direction) on a tie or for empty text.
  - Apply it to the model text in:
    - AnswerText `<p>` (:62 and :96)
    - the clarification `<p>` (ChatPane:487)
    - the error text
    - the AnalysisResult interpretation
  - Keep `dir="auto"` for user-typed questions and conversation titles.
- **Tests (new `autoDir.majority.test.ts`):**
  - `majorityDir('Medicine الأعلى بمتوسط 83.9', 'ltr') → 'rtl'`
  - `majorityDir('Arts is lowest', 'rtl') → 'ltr'`
  - `majorityDir('83.9', 'rtl') → 'rtl'`

### 1d. Fix autoChart for numeric-looking labels

- **Finding:**
  - Capture 04 (table only, for `[faculty, average_final_score]`, 4 rows) came from an **older build**. Today's `autoChart` (ResultView.tsx:305-319) returns `'bar'` for that shape.
  - There is no `presentation` value that disables it (:343-349).
  - Live and reloaded answers are built the same way (ChatPane.tsx:101-123).
  - Confirm by asking that question on the current dev build (3001). The prod-style `docker-compose2.yml` image serves whatever was built into it.
- **Real bug:**
  - When the label column looks numeric (faculty codes 1–4, "101", Arabic-Indic digits), `nameIdx = numeric.findIndex(n => !n)` is −1, so it returns null and the result shows as a grid (:314-316).
  - `chartColumns` (:104-108) already labels by column 0 in this case.
- **Change:**
  ```ts
  let nameIdx = numeric.findIndex(n => !n)
  if (nameIdx < 0 && columns.length === 2 && new Set(rows.map(r => r[0])).size === rows.length) nameIdx = 0
  const valueIdx = numeric.findIndex((n, i) => n && i !== nameIdx)
  ```
  Also update the stale header comment in ResultView.tsx:11-20. It still describes the grid-only behaviour.
- **Tests (`ResultView.grouped.test.ts`, using its `res()` helper):**
  - `res(['faculty','average_final_score'], [['Engineering',61.53500000000001],['Science',70.2],['Arts',58.1],['Law',66.4]])` → `'bar'`. This passes today; keep it as a regression test.
  - `res(['faculty','average_final_score'], [[1,61.5],[2,70.2],[3,58.1],[4,66.4]])` → `'bar'`. This fails today and passes after the fix.
  - Existing coverage: `ChatPane.test.tsx:191-198`.

**Must stay untouched in step 1:** agent API calls, the ChatPane message state machine, the evidence computation, chart choice for every other shape, and the backend prompts.

**Verify:**
- Run `AnswerText.test.tsx`, `ResultView.cellText.test.ts`, `ResultView.grouped.test.ts`, `ChatPane.test.tsx`, `displayNumber.test.ts` and `autoDir.majority.test.ts`.
- In the browser, on Demo — Sales:
  - Ask "average margin_pct by region". Expect a bar chart, numbers to ≤ 2 dp, and bold rendered.
  - Ask the same question in Arabic with the Arabic UI. The answer must read right to left even when it starts with a region name.

---

## 2. Key influencers stopgap (KI-1, KI-2, KI-7) — frontend only

- **Seen in v1:** on a dataset with `cohort_ref`, Key influencers defaults to the ID and returns 1.00× results.
- **Boards (PNG):** `design-handoff/boards/step2-key-influencers/`:
  - `analysis-id-column-skipped-*`: a dataset with `cohort_ref`; the ID is skipped and the ranked chart is shown.
  - `analysis-full-*`

  Each comes in light, dark, ar and ar-dark.
- **Canvas:** page "Phase 1 — Datasets", board "Analysis · ID column skipped".

### KI-1: default outcome (`FE/pages/DatasetDetail.tsx:618-640`)

- Pick the outcome in this order:
  1. the highest-priority column in `ds.column_targets` (api.ts:262)
  2. a column whose authored `ds.column_meta[col].role` is a measure
  3. the current inferred rule: numeric, not identifier-like, not `nonAdditiveKind`, not all empty
- **Remove** the `?? numericCols.find(c => !looksLikeIdentifier(c.name)) ?? numericCols[0]` fallback.
- If nothing qualifies, don't auto-run. Show the outcome picker with the prompt "Pick what to explain" (new i18n key).
- Rewrite the comment at :617-627: it currently defends the identifier fallback as "better than none". That decision is reversed.

### KI-2: identifier names

- In `looksLikeIdentifier` (DatasetDetail.tsx:628-629), add `_ref`, `ref`, `_no`, `_num`, `_code` and `_key`.
- Add `_ref` to `ID_NAME` in `FE/lib/semanticGuard.ts:17`. It already has `_no`.
- Don't change `FE/lib/columnRole.ts:14`. It deliberately mirrors the backend `infer_semantic` pattern, and the backend pattern is aligned in KI-3 (section 7).
- Add a test per suffix in `semanticGuard.test.ts` and `DatasetDetail.test.tsx`.

### KI-7: proper renderer

- In `FE/components/analysis/analysisResults.tsx:240`, `key_influencers` falls through to `GenericResult`. Add a `KeyInfluencersResult` built from the existing row fields (`factor`, `group`, `mean`/`rate`, `lift`, `rows`, `share_of_rows`):
  - Rows sorted by |lift − 1|.
  - "factor = group" as the label.
  - A horizontal bar from a 1.0× baseline.
  - Rows and share-of-rows as the support columns. There are no p-values, so don't invent any.
  - Groups with too few rows are muted, with the copy "small group".
- Show "Left out" lines only for columns the client skipped as identifiers ("an identifier — values are all different"). No leakage text; that's N8.

**Must stay untouched:** `/key-influencers` and `/analysis/run` calls and parameters, the Re-run control, the other result renderers.

**Verify:**
- Tests: `DatasetDetail.test.tsx`, `semanticGuard.test.ts`, and `analysisResults.test.tsx` with a key_influencers fixture.
- Browser:
  - A dataset with `cohort_ref` plus a real measure defaults to the measure.
  - A dataset whose only numeric column is an ID shows the picker and doesn't auto-run.
  - Results render as the ranked chart in English and Arabic, light and dark.

---

## 3. Datasets Phase 1

**Boards (PNG):** `design-handoff/boards/step3-datasets-phase1/` (68 images):
- `list-*`: full / firstrun / empty / loading / error
- `overview-*`: same five states
- `columns-full-*`, `data-full-*`
- `rules-full-*`, `models-full-*`, `models-empty-*`
- `aggregates-directquery-*`, `share-dialog-*`

Each comes in light, dark, ar and ar-dark.

**Canvas:** page **"Phase 1 — Datasets (existing backend only)"** (14 boards). Full design and states: "Merged — Datasets". Tab map and gap list: the "Tab map + backend gaps" reference board.

**Files:**
- `FE/pages/Dashboard.tsx` (this is the `/datasets` list, see `App.tsx:100`)
- `FE/pages/DatasetDetail.tsx`
- `FE/pages/datasetDetail/constants.ts`
- `FE/components/dataset/*`: AlertsPanel, ChecksPanel, ColumnMeaningPanel, DataQualityPanel, PredictionModelsPanel, AggregatesPanel, PipelineHealth, DatasetListFilter
- `FE/components/StatisticsPanel.tsx`
- `FE/components/DatasetShareDialog.tsx`
- `FE/components/DatasetSensitivity.tsx`

### Tab map

`constants.ts` `Tab` changes from v1's `overview | data | meaning | statistics | alerts | checks | models` (+ aggregates) to `overview | columns | data | analysis | rules | models | aggregates`.

| v1 | New |
|---|---|
| Overview | Overview. Its data-quality rules box moves to Rules & alerts. |
| Data | Data |
| Meaning | Columns (merged with the column profile) |
| Statistics ("Analysis") | Analysis |
| Alerts + Checks | Rules & alerts. Checks stay hidden for DirectQuery, as in v1. |
| Models | Models |
| Aggregates | Aggregates (DirectQuery only, as in v1) |

Old URL tab keys must redirect: `meaning→columns`, `statistics→analysis`, `alerts|checks→rules`. Keep deep links working.

### List (`Dashboard.tsx`)

- **Health strip:**
  - Counts by kind and status.
  - Fresh / stale / failing come from the lineage graph `health` plus `pipeline-health` (formerly P2, now frontend).
  - Segments link to the stale or failing dataset.
- **Facets:** Source, Status, **Mine only** (`created_by === me`), Certified only. There is no Owner facet (that's P1).
- **Table:** Name + description · Source ("Import · PostgreSQL" from lineage `sources[].type` via `data_source_id`, formerly P3) · Rows · Columns · Size · Freshness in words · **Dashboards** count (lineage `reports[].dataset_ids`).
- **Preview panel:**
  - Facts: Rows, Columns, Uploaded, Label.
  - Column chips, first rows, "Dashboards built on it".
  - Actions: Open, Build dashboard, Ask.
- **States:** first run (drop zone + three options), no match, loading skeleton, error with retry.

### Detail: Overview

- **Header meta:** "Created by you · uploaded 42 min ago · 221.6 KB". If someone else created it, leave the owner out (P1).
- **Trust checks:**
  - Fresh. No "Replace file" (N4).
  - Complete, from analysis `missing_pct`.
  - Checks: "4 of 5 saved checks pass — 'margin_pct ≤ 100' fails on 3 rows", with "View rows" via the existing checks try call.
  - Certified, with the action shown to admins only.
- **Facts:** Rows · Columns · Uploaded · Size. No Period (P4) and no Grain (N7).
- **Columns at a glance:**
  - Numbers: **percentile range bars** (p5–p95 line, p25–p75 box, median tick) from the existing analysis endpoint.
  - Text: top values. Dates: monthly bars.
  - No histograms (N2).
- **Used by:** dashboards and derived datasets (lineage graph) and alerts (`/datasets/{id}/alerts`). No dataflows, pins or conversations (N1).
- **Lineage card:** "Uploaded file", not a file name (N5).
- **Insights card:** existing insights.
- **Activity card, admins only. Load only recent events, never the full log.**
  - Both endpoints already take `limit` (default 200, capped at 1000 server-side) and return newest first (`BE/routers/admin.py:461-475` and `:529-551`).
  - Call each **once with `limit=200`**, and don't paginate:
    - `monitoringApi.activity(200)` (`GET /admin/audit-log?limit=200`, `FE/services/api.ts:2175`), then filter `entity`/`entity_id` for this dataset in the client
    - `adminAuditApi` with `{ limit: 200, q: 'dataset:' + id }` (`GET /admin/admin-audit`, `FE/services/api.ts:2110`, filtered server-side)
  - Merge both lists, sort by time, and show the latest 5 with a "View in Audit" link to `/admin/audit`.
  - Title it **"Recent activity"**. The general log's 200 rows are org-wide, so a quiet dataset may show few or no events from it. If both lists are empty, show "No recent changes recorded", not an empty card.
  - **Check the exact target in the client**: `q` matches substrings, so `dataset:1` also matches `dataset:12`.
  - Shows upload, label change and share only. Hide the card for non-admins, and don't call the endpoints for them.
- **First-run steps:** generic, with no ingest findings (P7).

### Columns tab

One row per column: name + type · description and meaning editor (from ColumnMeaningPanel) · treat as / summarise as · distribution (range bar or top values) · Empty % · Summary.

There is no Distinct column (N2) and no "Suggest descriptions" (N6). There is a "Hidden columns (n)" button.

### Data tab

- v1's left panel (filters, global filter, pipeline, calculated columns) becomes a toolbar.
- Headers show name + type only (N10).
- "174 of 2,000 rows" uses the `data-preview` `total` (B4).

### Analysis tab

- Analyses are offered as questions from `GET /analysis/registry` and run with `POST /datasets/{id}/analysis/run` (B2).
- Key influencers uses step 2.

### Rules & alerts

- **Quality rules:** saved checks plus the old Overview rules. The copy reads "Checked before each refresh is published, and whenever you press Run now. 'Block' keeps the current version if a rule fails."
- **Alerts list:** from AlertsPanel.
- **Freshness:** "Not applicable — files don't refresh" for uploads.

### Models

Fit in plain words · baseline · split · trained on · drift · candidates. All of these come from model-card fields (B3). No leakage notice (N8).

### Share dialog

- Explicit grants from `/datasets/{id}/shares`.
- The "Can also open it" section is **static copy**: you (creator), workspace admins, "anyone who can open its N dashboards" (N from lineage). No counts of admins or viewers (N9).

**Must stay untouched:**
- every `datasetsApi` call and parameter
- certify (admin-only), sensitivity labels, RLS/CLS behaviour
- the upload flow, pipeline and calculated-column logic
- incremental settings and the aggregates logic

**Verify:**
- Tests: `Dashboard.test.tsx`, `DatasetDetail.test.tsx`, `listFilterWiring.test.tsx`, `loadFailures.test.tsx`, and the `components/dataset/*.test.tsx` files.
  - Add tests for the tab-key redirects, the admin-only Activity card, and the exact-target audit filter.
- Browser:
  - Walk every PNG in `design-handoff/boards/step3-datasets-phase1/`. Each state × light / dark / ar / ar-dark should match.
  - Log in as `demo-emea@example.invalid` to check that RLS/CLS still hide rows and the `cost` column.

---

## 4. Ask AI Phase 1 (merged design)

**Boards (PNG):** `design-handoff/boards/step4-ask-ai-phase1/` (32 images). States `nodataset`, `firstrun`, `thinking`, `clarify`, `answer`, `offline`, `error`, plus `answer-sql-open`, each in light, dark, ar and ar-dark. These are the **Phase 1** versions: build exactly these.

**Canvas:** page **"Ask AI — merged (A + B panel + C answer)"**.
- The rows "Phase 1" and "Phase 1 · Arabic" are what you build.
- The light, dark, Arabic and Arabic-dark rows show the full target.
- The reference board "Ask AI — fixes, handoff + backend gaps" lists the AN/AP/AB codes.

**Files:**
- `FE/pages/AskAI.tsx`
- `FE/pages/ask/*`: HistoryPanel, DataPicker, suggestions.ts, ask.css
- `FE/components/chat/*`: ChatPane, Composer, Pending, AnswerText, ResultView, ChoiceOptions, AddToDashboard
- Reuse `FE/components/report/suggestionTakeaway.ts`, plus `choiceLight` and `effectiveChoice` from `FE/components/LlmPicker.tsx`.

### Layout

| Region | Contents |
|---|---|
| Sidebar | v1, unchanged |
| History | 248 px. Groups Today / Earlier, **search titles** (AB8, client-side), rename/delete as v1. Replace the `window.confirm` delete (AskAI.tsx:166) with `ConfirmDialog`. |
| Thread | Max 820 px. Scope bar with the dataset chip (name · kind · rows · columns). Messages. Composer. |
| Column panel (new `ColumnPanel`) | 256 px, collapsible. The fold state goes in localStorage, the same way as the history fold. |

- **Column panel content:**
  - Columns grouped as Groups / Numbers / Dates / Other, with type tag, value count or range (from the dataset columns and the existing profile).
  - **Clicking a column inserts it into the composer** as a token. The panel shows a "Click a column to put it in your question" hint (AB11).
- **Mobile:** history and column panel become drawers, using the existing drawer pattern.

### Answer card (latest answer)

1. Header: "Answer · dataset · 2.4 s".
2. **Key numbers** (AB12): highest, lowest, gap, rows read → groups. Compute them from the result rows with `suggestionTakeaway.ts`. Rows read comes from the run steps.
3. The sentence, with step 1 applied (markdown, numbers, direction, traced numbers).
4. Chart (step 1d rules, axis from 0, v1 RTL).
5. Two columns: **Rows** and **"How it was worked out"** (AB6). The steps come from `GET /agent/runs/{id}` `steps[]`, which is already fetched lazily for SQL by `sqlFor`, ChatPane.tsx:281-294.
6. Show SQL toggle.
7. Source line.
8. Actions: Show SQL, Copy, Add to dashboard, Export, 👍 / 👎. After 👎, ask "What was wrong?" and send `comment` (AB10; the endpoint already accepts it).
9. "Ask next": 2 chips from `suggestions.ts`, built from unused columns (AB7).

Older answers in the thread are compact: sentence, chart and actions only.

### States

| State | Phase 1 behaviour |
|---|---|
| No dataset chosen | Chooser: search, "Recently asked about" (datasets list + conversations' `dataset_ids`, AB9), all datasets, connections. Composer locked with "Choose data above to start asking". |
| First run | Title, intro copy, 4 starters, 3 "how it works" tiles. The column panel is live. |
| Thinking | Elapsed seconds and a skeleton, with "Usually 5–20 s". **Remove v1's timer-driven fake stages** (Pending.tsx:198-203). No Stop button (AN2). |
| Clarification | Rendered text. Option buttons for **column names the reply mentions** (bold or quoted terms ∩ dataset columns, with the value count from the profile, AB3), plus "Or type your answer". Picking an option sends the reply. The backend already merges it with the original question (`clarified_question`). |
| Answer | The card above. |
| AI offline | Detect with `GET /llm/endpoints` through the **same query the top bar uses**. Don't add a second poller. `choiceLight(...) === 'down'` means offline (AB4). Show a banner: new questions paused, past answers, rows, SQL, export and add-to-dashboard still work, plus links "Explore <dataset> without AI" (dataset Data tab) and "Build a chart yourself" (builder). Composer disabled. |
| Error | Title, the server reason (rendered), "Try instead" chips (starters), Try again, Edit question, Technical details (`dir="ltr"`). |
| AI limit (429) | Keep v1's message, restyled. |

Hidden in Phase 1: Save answer (AN4), Stop (AN2), server-built options with previews (AN1), model-written next questions (AN3).

**Localize** the ~15 hardcoded English strings:
- "Thinking ·"
- "Designing dashboards"
- the 20 s note
- "Could not reach the agent"
- "Could not load this conversation"
- the result caption
- "No rows."
- "Tables considered"
- the Save-as-dataset prompts
- the delete confirm
- the aria-labels "Copy SQL", "Download CSV", "Good answer" and "Ways to continue"
- "Saving…"

**Must stay untouched:**
- all `agentApi` calls and payloads, conversation persistence, quotas and 429 handling
- evidence tracing, the AddToDashboard flow, Save as dataset (connections), exports
- the report-builder mount of ChatPane (`conversationId` omitted) and the page copilot (`CopilotChat.tsx`)
- the Ask AI refusal to edit dashboards (by design, see CLAUDE.md)

**Verify:**
- Tests: `AskAI.test.tsx`, `ChatPane.test.tsx`, `ChatPaneProgress.test.tsx`, `askComponents.test.tsx`, `AnswerEvidence.test.tsx`, plus new tests for:
  - ColumnPanel insert
  - clarification options from bold/quoted columns
  - the offline state from a mocked `/llm/endpoints`
  - the key numbers
- Browser:
  - Every state in English and Arabic, light and dark.
  - Clarification: ask "average final score by department" on a dataset with `faculty`.
  - Error: ask about a missing column ("grade").
  - Offline: point the LLM endpoint at a dead host. The top-bar dot goes red, the composer is disabled, and past answers still export.

---

## 5. Home and Viewer

**Boards (PNG):** `design-handoff/boards/step5-home-viewer/` (40 images). `home-*` and `viewer-*` in full / firstrun / empty / loading / error, each in light, dark, ar and ar-dark. These show the full design. The gap pass below decides what Phase 1 hides.

**Canvas:** page "Merged — v2 (C + v1 sidebar)": boards Home (`MHome`) and Viewer (`MViewer`), with full / first-run / empty / loading / error, light, dark and Arabic.

**Do a gap pass before coding.** Home and Viewer were designed before the N/P/B audit. Audit them the same way as Datasets, mark anything with no backend data, and apply the Phase 1 rule: hide it, don't stub it. Likely gaps to check:
- "Since you last looked (Friday)" changes
- a headline value + delta on each list row
- Pinned items
- answers in the Home list
- "shared with Sales (8 people)"
- per-option counts in the Viewer filters
- "Updated 4 min ago" for imported data

### Home (`FE/pages/Home.tsx`, `Home.test.tsx`)

- **Header:** "Home · Pick up where you left off". Type tabs: All / Dashboards / Datasets / Answers. A New button.
- **Left: "your work" list.** Filter, then groups Pinned / Today / This week. Each row: icon by type, name, meta with a status dot, headline value + delta.
- **Right: live preview of the selected item.**
  - Dashboard header with Present, Share, Open.
  - "Since you last looked".
  - 4 KPI tiles with deltas "vs Aug".
  - Revenue by month (columns + target line, axis from 0).
  - Revenue by region (bars + target ticks).
  - Footer with freshness and "used by".
- **States:**
  - Empty: no dashboards. Show the dataset preview with suggested charts and "Create with these".
  - First run: welcome + 3 starts.
  - Loading skeleton.
  - Error: KPI tiles show "—" with retry / open anyway / copy error.
- **Data:** `datasetsApi`, `reportsApi` (`RecentReport`), as Home uses today.

### Viewer (view mode of `FE/pages/ReportBuilder.tsx` when `editMode` is false; also `/dashboards/:id` → `DashboardAlias`, and `SharedReport.tsx`)

- **Header:** title, View mode / Explore toggle, freshness, Save view (BookmarksPane exists), Download, Share, Edit.
- **Filter pane:**
  - Period (Month / Quarter / Year), Region, Channel, Country.
  - Option counts, *if they exist*.
  - "n active · Clear".
  - Removable chips and a drill path ("All regions › Asia Pacific", "Drill into: Country").
- **Body:** KPI row, then charts that cross-filter the page ("Click a bar to filter everything; click again to clear"), using the existing `CrossFilterContext`. A chart/table toggle on the country breakdown.
- **States:**
  - Empty filter result: an explanation plus "Remove 'Wholesale'" / "Go to June 2026".
  - A facet that fails to load fails alone ("Countries didn't load — other filters still work").
  - Loading.
  - First-run coach marks.

**Must stay untouched:**
- `WidgetRenderer` and the chart renderers, widget-data calls
- `CrossFilterContext` logic, bookmarks logic, permissions, print and shared/embedded routes
- every `editMode` gate in ReportBuilder (about 60 references)

**Verify:**
- Tests: `Home.test.tsx`, `ReportBuilder.test.tsx`, `SharedReport.test.tsx`, `EmbeddedReport.test.tsx`, `CrossFilterContext.test.tsx`, `BookmarksPane.test.tsx`.
- Browser: Home and Viewer states in English and Arabic, light and dark. Cross-filtering, drill and clear behave as before.

---

## 6. Builder

**Boards (PNG):** `design-handoff/boards/step6-builder/` (24 images). `builder-*` in full / offline / firstrun / empty / loading / error, each in light, dark, ar and ar-dark. `builder-full-ar*` is the Arabic board with the copilot active. `builder-offline-*` shows every tool still working with the model down.

**Canvas:** page "Merged — v2", board Builder (`MBuilder`) with full / offline / first-run / empty / loading / error states, plus the Arabic copilot boards (light and dark).

**Files:**
- `FE/pages/ReportBuilder.tsx` (4,415 lines)
- `FE/pages/reportBuilder/*` (grid.ts, undo.ts, PageTemplateMenu, BookmarksConnected, SchedulePanel)
- `FE/components/report/*`: CopilotChat.tsx + copilot.css, OutlinePane, DataRolesList, PagePropertiesPanel, the widget config panels, SchemaBreakDialog in `components/dataset`

**Gap pass first**, same as step 5. Likely items:
- copilot "Added by copilot" with Keep / Undo per change
- the "renamed to 'goal' on 3 Oct" column-rename detection (check SchemaBreakDialog / ReconcileDialog)
- "Loading 7 blocks · 4 ready"

### Layout (restyle, don't rebuild)

- **Top bar of the page:**
  - title, Saved / Not published state
  - Edit / View, page tabs + Add page
  - Undo / Redo, Insert (Chart, Big number, Table, Text, Filter control, Image), Share, Publish
- **Left: Fields panel.**
  - Dataset name, "Find a field".
  - Groups Dimensions / Time / Measures with counts or aggregation badges. Calculated fields marked ƒx.
  - Hint: "Drag a field onto the page, or onto a chart to add it."
- **Canvas: 12-column grid.**
  - A text summary block, KPIs and charts.
  - **Manual drag and resize stay first-class:** a size tip ("6 of 12 columns · 4 rows") and drop zones ("Drop here, or press / to insert").
- **Right panel tabs: Inspector | Copilot.**
  - Inspector: chart type, width (columns) with "Or drag the chart's edge on the page", categories, value, target marker, colour rule, filters.
  - Copilot: optional. Starter prompts, and changes shown inline with Keep / Undo.
  - Copy: "Everything the copilot does is also in Insert, Fields and the Inspector."
- **States:**
  - **AI offline:** "Copilot is offline. Every editing tool still works." Nothing else is disabled.
  - A chart error shown inline with fix actions ("Use 'goal'" / "Remove target").
  - Empty page: drop targets + 3 layout templates.
  - Loading: blocks progress.
  - First-run coach marks.

**Must stay untouched:**
- `grid.ts` layout math, `undo.ts`
- `persistWidgetLayouts`, drag/resize handlers, autosave, conflict merge (ConflictMergeDialog, threeWayMerge)
- all `editMode` gates, widget config semantics, CopilotChat's API calls
- the Ask AI refusal to edit dashboards

The builder must stay **fully usable with the model server down**.

**Verify:**
- Tests: `ReportBuilder.test.tsx`, `undo.test.ts`, `CopilotChat.test.tsx`, `ConflictMergeDialog.test.tsx`, `dashboardLayout.test.ts`.
- Browser:
  - Build a page by hand with the LLM endpoint dead: drag, resize, Insert, Inspector, undo/redo, publish.
  - Then with the copilot on: Keep / Undo.
  - English and Arabic, light and dark.

---

## 7. Backend work (separate — not part of steps 1–6)

Order agreed with the owner:

| Phase | Items |
|---|---|
| Phase 2 | **P6 / KI-3 to KI-6 first** (a real bug), then P1, P4, N5. P2 and P3 moved to frontend (step 3). |
| Phase 3 | The other N items. |
| Not yet scheduled | AN1–AN4, AP1–AP3 (Ask AI). |

### Key influencers (P6)

| # | Where | Fix |
|---|---|---|
| KI-3 | ID heuristics copied in `FE/pages/DatasetDetail.tsx:628`, `FE/lib/columnRole.ts:14`, `FE/lib/semanticGuard.ts:17`, `BE/services/widget_data.py:406` (`^id$\|_id$\|_key$\|_uuid$\|^uuid$\|_code$`) | Make the backend role (`infer_semantic` + `column_meta`) the source of truth, expose it per column, and have the frontend read it. One shared suffix list including `_ref` and `_no`. |
| KI-4 | `BE/services/analysis/influencers.py:150-196` accepts an ID target | Return 422 with a clear message for identifier or near-unique targets. |
| KI-5 | `BE/routers/analysis.py:359-360` (`/key-influencers`) and `:681-682` (`/analysis/run`) don't pass `column_meta` | Pass `dataset.column_meta` in both. |
| KI-6 | `BE/services/metadata/infer_semantic.py:56`, `88-130`: the 0.98-uniqueness rule runs before the measure logic, so `cost` becomes an "identifier" | Apply uniqueness only to integer or string, non-measure-like columns. |

Also from P6: prefer `knowledge.targets()` first, and expose distinct counts (see N2).

### Datasets: partial (P)

| # | Work |
|---|---|
| P1 | `owner {id, name, email}` on `DatasetOut` (one join in `list_datasets`). Unlocks the owner name and Owner facet. |
| P4 | Return `period {column, from, to}` on detail (and list). It's computed today in `dataset_profile._date_range`. |
| P5 | Store Overview rules as `DataCheck` rules, run them on upload, return the latest result summary. |
| P7 | Run inference + P5 rules at upload and return findings (first-run "Check two columns"). |

### Datasets: new (N)

| # | Work |
|---|---|
| N1 | `GET /datasets/{id}/usage` covering dataflows, pins and Ask AI conversations, plus `used_by_count` on the list. Dashboards, derived datasets and alerts are already frontend (step 3). |
| N2 | Bins + numeric distinct counts in `analyze_numeric` or a `/profile` endpoint, ideally persisted at ingest. Unlocks histograms and the Distinct column. |
| N3 | `GET /datasets/{id}/activity` (entity-filtered, permission-checked, for non-admins) + audit calls for certify, description edits, column-meta edits and alert creation. Also fix `admin-audit` `q` substring matching. |
| N4 | Replace/append into an existing dataset + `dataset_versions` (or `RefreshRun` with `trigger=upload`). |
| N5 | Persist the original upload file name (Phase 2). |
| N6 | Thin `POST /datasets/{id}/suggest-descriptions` reusing `describe_with_llm` (from Connections), plus a consent rule for uploads. Results are proposals until accepted. |
| N7 | Editable grain for uploads (a `column_meta` key or a column). |
| N8 | Leakage / derived-column check before influencers and training. |
| N9 | Endpoint explaining effective readers (counts are enough), using the rules in `core/capability.py`. |
| N10 | Profile endpoint that accepts the data-preview filters (filtered column summaries). |

### Ask AI (AN / AP)

| # | Work |
|---|---|
| AN1 | Structured clarification options: `presentation: {kind:"clarify", options:[{label, column, values_count, sample}]}` from the schema, in place of free text only (`nodes/clarify.py:7-21`). Choosing an option must not need the text round-trip. No previews (dropped from the design). |
| AN2 | Stream run progress (SSE of node events from `run_agent`) + a cancel endpoint. Unlocks real stages and Stop. |
| AN3 | Return 2–3 `follow_ups` with each answer. |
| AN4 | Saved answers (snapshot) — a table and endpoints, or reuse pins. |
| AP1 | Distinct error code (e.g. `model_unreachable`) or 503 when the model is down mid-run. Today it's a generic `failed`, "could not classify the question" (`graph.py:327-330`). |
| AP2 | Error codes + the unknown identifier on failed runs, so the client can suggest the nearest real column (`steps[].validation_failures` exist). |
| AP3 | Localize server-written strings by the question's language: chart choices "Chart {y} by {x}", `_PRESENT_ANSWERS`, the refusal and fallback texts. |

---

## 8. Reference: canvas pages

| Page | PNG folder | Use for |
|---|---|---|
| Merged — v2 (C + v1 sidebar) | `design-handoff/boards/step5-home-viewer/`, `design-handoff/boards/step6-builder/` | Home, Builder, Viewer (steps 5–6), incl. the Arabic copilot boards |
| Merged — Datasets | — (full design, not a build target) | Full Datasets design, gaps-marked boards, the tab map + gap reference, the Key influencers handoff note |
| Phase 1 — Datasets (existing backend only) | `design-handoff/boards/step2-key-influencers/`, `design-handoff/boards/step3-datasets-phase1/` | **Build target for step 3** |
| Ask AI — merged (A + B panel + C answer) | `design-handoff/boards/step1-ask-ai-quick-fixes/`, `design-handoff/boards/step4-ask-ai-phase1/` | **Build target for step 4** (Phase 1 rows); reference board with step 1's findings |
| Ask AI — 3 variations | — | History only; not a build target |
| Shell + Home / Report Builder / Dashboard Viewer | — | Superseded exploration (some SVG chart labels render blank there); not a build target |

Note: on the canvas and in the PNGs, chart labels are HTML because the canvas runtime can't put templated text inside SVG. The product keeps its Recharts renderers.
