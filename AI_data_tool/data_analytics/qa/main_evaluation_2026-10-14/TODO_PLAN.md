# Datalytics — To-do plan: fix all Critical, High and Medium issues

| | |
|---|---|
| **Branch** | Written against `s_mostafa` @ `2926eb5` (same app code as `main` @ `0cb8f48`); the fixes are on the integration branch `fix/integ2`, not yet merged into `s_mostafa`. All file paths are relative to `AI_data_tool/data_analytics/`. |
| **Source** | `qa/main_evaluation_2026-10-14/EVALUATION.md`: 147 Critical/High/Medium findings from the exhaustive UI journey, the QA plan failures (DASH-04, INS-02, MAP-02, SEC-02) and the automated test results. Duplicates were merged into **122 tasks**, and each was traced to the code on this branch. |
| **Date** | 15 Oct 2026 |

## Progress

| Date | Done | Commits (integration branch `fix/integ2`; the first row is on `s_mostafa`) |
|---|---|---|
| 15 Oct 2026 | **F-01, E-01, E-02** (the three Critical issues) and **B-01** | `16a84654` F-01 · `55c6ac61` E-01/E-02 · `62a54a56` B-01 |
| 15 Oct 2026 | **Round 1:** the rest of the 122 tasks, by area (AD, B, C, E, F); 20 left partly done, 4 deferred/not started | merges `ef9755e2` (AD) · `79f30a91` (F) · `ed82a0e8` (E) · `ad612c52` (B) · `0810f9fa` (C); integration fixes `80706552` · `e38b4882` · `610bb057` |
| 15 Oct 2026 | **Round 2:** every remaining item (owner: "solve all") — B-35, B-21, E-08, C-21, C-07 and the partial leftovers | merges `9ed04374` (B) · `506ca75e` (E) + `9301cc48` (Alembic chain 0070 → 0071 → 0072) · `b239583a` (C); docs `e3f6c4d5` |
| 15 Oct 2026 | **Known-gap review** (release readiness): B-21, E-08, C-11, B-18 re-examined; 2 more defects found and fixed (AD-12 in a real browser, count-KPI caption); 2 backend failures of the final full run resolved | `71ff169c` E-08 layering · `ffa1c85c` B-36 test · `18c98c7f` AD-12 · `fb96b609` KPI caption · merges `f07a88d9` (B-21, `302279bc`) · `ddddd25f` (E-08, `f41a0730`) · docs `a9acecbb` |

**Status: 122 of 122 tasks ticked.** Schema changes: Alembic `0069_users_email_ci_unique`, `0070_roles_org_name_unique`, `0071_glossary_dataset_scope`, `0072_role_capabilities`, each mirrored in `app.main._migrate` for databases adopted without revisions.

### Release-readiness review of the known gaps (15 Oct 2026, evening)

| Gap | Classification | Status |
|---|---|---|
| B-21 — org-wide glossary terms could not be created from the Glossary page | Confirmed defect (missing plan step 1) | **Fixed and verified** |
| E-08 — permissions not enforced on every dataset/dashboard creation path; publishing | 7 confirmed bypasses + missing coverage; publishing = accepted limitation | **Fixed and verified** (bypasses); **accepted limitation** (publishing, UI buttons) |
| C-11 — DuckDB/DirectQuery path "not reproducible" | Reproduced on the unfixed code after all (DirectQuery); fixed by the shared server fix | **Fixed and verified** |
| B-18 — not reproduced in a real browser | Could not be reproduced on the unfixed or the fixed build | **Investigated but not reproduced** (protective change in place) |

- **B-21.**
  - *Root cause:* the model already allowed org-wide terms (`data_source_id` and `dataset_id` both NULL) and the AI context already read them, but no route created them and the page had no org-wide choice.
  - *Change:* `GET/POST /api/v1/glossary`, `PATCH/DELETE /api/v1/glossary/{id}` (new `routers/org_glossary.py`, sharing the per-connection validation helpers); "All data (org-wide)" first in the Glossary selector (en/ar); writes org-admin only, reads any member, other org → 404, a scoped term through these routes → 404. Side fix: the per-connection PATCH/DELETE could edit or delete an org-wide term; they now return 404.
  - *Tests:* 6 backend + 3 frontend tests, all failing before; related suites 374 + 14 + 171 passed.
  - *Real stack:* admin@example.invalid created a term in the browser → stored with both scopes NULL, survives a reload; demo-global sees it read-only (no Add/Edit/Delete); its POST /glossary → 403 "Admin privileges required". Final QA fix check: pass.
  - *Remaining risk:* low. Deleting a term asks no confirmation (cosmetic, seen in QA).
- **E-08.**
  - *Inventory* of every request or run that constructs a `Dataset`/`Report` (table in the `fix3/e8b` log and commit `f41a0730`). Already gated: upload, batch, new connection, new/duplicate dashboard, templates; admin-only by design: combine across connections, import from a connection, guided-setup import.
  - *Confirmed bypasses, now refused with the readable reason:* materialize, aggregates, dataflow run with a new output name, batch scoring (Add data); automated analysis — refused at start and its compose step re-checks the run owner's role at run time (Create dashboards); demo seed/unseed was open to any member → org-admin only (no screen calls it).
  - *Left by design:* re-running existing dataflows/refreshes (not new data); editing existing dashboards (copilot, pages) needs edit rights.
  - *Accepted limitation — publishing:* there is no publish permission in the 5-permission set; publishing stays author-or-org-admin and needs approval where the org requires it, now pinned by a test.
  - *Accepted limitation — UI:* the Materialize / Aggregate / new-output / Score / Start-analysis buttons are still shown to a role without the right; the server answers 403 with "Your role (…) is not allowed to add or upload data…".
  - *Tests:* 8 new (`test_role_permissions_gaps.py`), 7 failed before (materialize 200, aggregate 201, dataflow output 200, score-jobs 202, automation start 201, compose not stopped, demo seed 200); the publishing test passed before, as intended. Related suites ≈775 passed.
  - *Real stack:* a role with Add data and Create dashboards off → materialize 403 and new dashboard 403 with the reason; member demo seed 403. Final QA: the roles × permissions matrix is on Admin → Roles.
- **C-11.**
  - *Original reproduction:* Bar+line / dual-axis with margin_pct on the second axis summed it (0–12,000 %).
  - *Evidence (same request against the unfixed `main` backend and the fixed one, Demo — Sales, month × revenue | margin_pct, no aggregation2):* unfixed 2024-01 `value2 = 1654.7`; fixed `22.36` (average) — for dual_axis_line, dual_axis_bar, dual_axis_bar_line and dual_axis_time_series, with the DuckDB pushdown setting on (default). An explicit `aggregation2: "sum"` is still honoured (1654.7).
  - *DirectQuery:* a DirectQuery dataset over a SQLite table built for the check (`c11_sales`, known average 19.698 and sum 984.9 for 2024-01): unfixed `984.9` (summed), fixed `19.698`. So the DirectQuery path **was** affected on the unfixed code and is fixed by the shared server change (`shape_dual_series` default summary); the round-2 "not reproducible" note was wrong and is corrected here.
  - *Tests:* guard tests from round 2 (`test_dual_series_default_summary.py`, axis titles) plus the end-to-end API evidence above; final QA fix check: right axis avg(margin_pct) 0–28 %.
  - *Remaining risk:* axis titles still read "avg(margin_pct)" (wording, product-wide decision); the right axis tick labels are partly covered by the rotated title (cosmetic).
- **B-18.**
  - *Original report:* on `/ask?dataset=1` with the model offline, "typing in the disabled box and pressing Enter" reset the page to Step 1 and dropped the dataset; Ctrl+A selected the page. The original screenshot (B-44) shows a **keyboard focus ring on the sidebar "Ask AI" link**.
  - *Reproduction attempts on the unfixed `main` build, real Chromium:* (1) /ask?dataset=1 → click the box, type, Enter; (2) via the dataset page; (3) sidebar Ask AI → pick Demo — Sales → click box, type, Enter; (4) click box, type, Tab, Enter (opened the dataset picker); (5) then type + Enter in the picker; (6) the original driver path. The dataset stayed selected every time.
  - *Most likely cause (inferred, not proven):* Enter on a focused sidebar "Ask AI" link, which opens bare /ask by design; the disabled box could not take focus, so keys went to whatever had it.
  - *On the fixed build:* the box is read-only + aria-disabled and takes focus; click/type/Enter and Tab+Enter keep `dataset=1` (real browser, and the final QA fix check). Page test `askScopeOffline.test.tsx` fails with the old disabled box.
  - *Status:* investigated but not reproduced; not claimed as fixed.
- **Found during the review and fixed:**
  - **AD-12 (real browser):** a signed-out visit to /ask?dataset=1 went to /login with the target, but after signing in landed on Home. Root cause: `AuthContext.login` ended with `navigate('/')`, unmounting the sign-in page before it could read the target (the AD-12 page tests mock AuthContext). Fix `18c98c7f`; new `AuthContext.returnTo.test.tsx` with the real provider (failed before). Real browser: /ask?dataset=1 → sign in → /ask?dataset=1; plain sign-in → /.
  - **Count KPI caption:** B-36 (round 2) captioned a count KPI "Records", re-opening the live-QA finding that it did not say what was counted (full frontend run, 1 failure). Now "Count of {column}" / "عدد {column}" (`fb96b609`).

### Final verification (15 Oct 2026)

- **Frontend:** full vitest on the final integration code — 411 files, **5,015 passed**, 0 failed, no unhandled errors. `tsc --noEmit` clean.
- **Backend, final full run** (two halves run in parallel because of a 2-hour limit on one background job; the halves cover all 559 test files exactly once, checked):
  - first run on `a9acecbb`: 8,853 passed, 4 skipped, **2 failed** (half 1: 4,136 passed / 1 skipped / 0 failed; half 2: 4,717 passed / 3 skipped / 2 failed). A first single-process run was stopped at 60 % by the job limit and is not counted.
  - `test_layer_conformance::TestDocumentedInvariants::test_no_service_imports_fastapi` — **genuine regression** (architecture rule) from E-08: `services/quotas.enforce_ai_budget` raised `fastapi.HTTPException`. Reproduced alone. Fixed `71ff169c`: domain exception `quotas.AiNotAllowed` + handler in `app.main` (same 403 + reason on the wire); new regression test failed before; 582 related tests passed.
  - `test_suggest_catalogue::test_every_idea_draws_names_real_columns_and_says_why_it_fits` — **outdated test**, not a product defect: it expected a card of totals mixing a weight with two unit-less numbers, which B-36 deliberately stopped offering. Reproduced alone. The test now pins B-36 on both sides (`ffa1c85c`, no assertion weakened beyond the card, which got its own stricter test); 18 related tests passed.
  - re-run of the full suite after both fixes: on `ffa1c85c`, **8,857 passed, 4 skipped, 0 failed** (half 1: 4,136 passed / 1 skipped; half 2: 4,721 passed / 3 skipped; the 4 extra passes over the first run are the 2 fixed tests and the 2 new regression tests).
- **Migrations on Postgres:** fresh empty DB → `0072`; an existing DB at `0070` → `0072` (roles keep every right); downgrade to `0070` and upgrade again clean; a pre-Alembic DB and an `init.sql` DB start with health 200 and the new columns; `0069` refuses (and names the accounts) on case-duplicate emails, and after clean-up adds the index.
- **Browser QA re-run (57 high cases, real Chromium):** **50 pass / 0 fail / 7 blocked** (baseline 46 / 4 / 7). All 4 baseline failures (DASH-04, MAP-02, INS-02, SEC-02) pass; the 7 blocked need an AI model server, which this environment does not have. 7 of 7 fix checks pass. Report: `qa_rerun_2026-10-15_final/REPORT.md`.
- **Browser console** during the QA run: no page errors and no uncaught exceptions (only expected 401/403/404 responses and "tile still loading" warnings for off-screen tiles).
- **Blocked ≠ failed:** the 7 blocked cases (ASK-02, ASK-03, ASK-04, ASK-06, SEC-03, BUILD-10, BUILD-11) need a reachable AI model server; none exists in this environment, so the app correctly shows "The model server isn't reachable, so new questions are paused." and disables Send. They were not run and are **not** verified.
- **Not verified here:** a real `docker compose up` (container registries are blocked from this environment); every AI feature with a live model.

### Remaining work, by priority

1. **Before a release that relies on AI:** run the 7 AI-dependent cases (ASK-02/03/04/06, SEC-03, BUILD-10/11) against a reachable model server; and a real `docker compose up` once registry access exists.
2. **Medium (UX, permissions):** hide or disable the Materialize / Aggregate / dataflow new-output / Score / Start-analysis buttons for roles without "Add data" / "Create dashboards" (the server already refuses with a reason).
3. **Low (seen in the final QA, no case fails):** cramped dashboards list at phone width (/reports keeps its side panel); dual-axis roles both labelled "Line" (no left/right hint) and the right-axis title overlapping its ticks; the gauge formats "$ 8.632.597" with dots while other tiles use commas; deleting a glossary term asks no confirmation.
4. **Decisions left open:** human axis titles ("Average margin_pct" instead of "avg(margin_pct)") across the product; a publish permission in the role matrix; B-18 stays "not reproduced" (watch for it in real use).

Evidence: final QA report `qa/main_evaluation_2026-10-14/qa_rerun_2026-10-15_final/REPORT.md`, screenshots in `qa_rerun_2026-10-15_final/shots/` (86 files); the earlier re-run `qa_rerun_2026-10-15/`.

The notes below describe the first four fixes of the morning.

What each fix found and changed, and where it differs from the original task text:
- **F-01 — guest links and embeds on map dashboards.**
  - *Reproduced 3/3:* a logged-out guest of "Demo — World Sales Map" was sent to `/login`. The no-map control stayed on the shared view.
  - *Implemented as planned:* `map_settings` in the shared and embed payloads, plus new `GET /shared/{token}/boundary-sets/{id}` and `GET /embed/boundary-sets/{id}` routes.
  - The new routes serve a set only if the published report references it and it belongs to the report's org; anything else returns 404.
  - A 401 on `/shared/*` or `/embed` no longer triggers the login redirect.
  - One deviation: the boundary-set loader switch lives in a new `frontend/src/components/report/geo/boundarySource.ts`, so the world atlas stays lazily loaded (`atlasLazy.test.ts`).
- **E-01 — org admin could change or delete the platform admin.**
  - *Reproduced live:* PATCH returned 200 and demoted the super admin.
  - *Fix:* PATCH, DELETE and org-unit changes on a platform admin now return 403 unless the caller is a platform admin. `/admin/users` marks those rows, and the Users page hides Edit/Delete on them for org admins.
- **E-02 — case-variant super-admin email.**
  - *Reproduced live:* a Contoso admin created `ADMIN@datalytics.local`, signed in, and got 200 on `/platform/organizations` with all orgs visible.
  - *Fix:* emails are normalised (trim + lower) and duplicates are checked case-insensitively on create, rename, bulk import and new-org admin.
  - Giving any account an allowlisted address now returns 403 unless the caller is a platform admin.
  - Login matches the address exactly first, then case-insensitively when that is unambiguous.
  - *Added beyond the task:* the SSO callbacks (OIDC and SAML) now refuse platform admins, because an org admin configures their own org's identity provider.
  - *Not done:* step 2 of the task (a migration adding a unique index on `lower(email)`). It would fail on databases that already hold case-duplicates, so it needs a cleanup decision first. See "Open follow-ups".
- **B-01 — schema gap on databases first built from `init.sql`.** The root cause on this branch was worse than the task described.
  - Such a database (stamped at head) made the backend **fail to start**: `_migrate` created `ix_reports_org_published` before the statement that adds `reports.published`.
  - *Fix:* that index now comes after its column, and the 8 missing columns and their indexes are in `_migrate`.
  - The schema-coverage test is no longer xfail. A new test fails if `_migrate` ever indexes a column before adding it.
  - *Verified on Postgres:* a previously crashing stamped database, a new `init.sql` database and a fresh empty database all start, have 0 missing tables/columns and seed the demo. A second boot is clean.
  - Step 3 of the task (also editing `init.sql`) was **not** done on purpose: the file is no longer loaded by anything. README now says so.

Verification for these four:
- **Backend:** full suite, 8,599 tests. 8,594 passed, 4 skipped, 5 failed.
  - 4 failures were `test_architecture_doc.py`: the documented test-file counts were behind after adding the new test files. They are fixed by updating `ARCHITECTURE.md` / `.html`, and that test now passes 35/35.
  - The remaining failure, `test_widget_roles.py::...test_the_spec_file_was_actually_read` (expects 75 chart types, frontend has 77), is pre-existing: it fails the same way on `main` (task B-14).
- **Frontend:** 391 files, 4,704 tests passed; `tsc` clean. One unhandled timer error from `CopilotChat.tsx` during `ReportBuilder.test.tsx` makes the run exit non-zero. It is pre-existing: 2 of 4 runs on untouched `main` hit it.
- **Browser QA re-run (57 high cases):** 46 pass / 4 fail / 7 blocked, against 45 / 4 / 8 on `main`.
  - The only change is SHARE-02 (guest link on a map dashboard), blocked → pass.
  - The 4 fails are unchanged and are other tasks: DASH-04 → C-30, MAP-02 → C-29, INS-02 → AD-06, SEC-02 → E-12.
- Report: `qa_rerun_2026-10-15/REPORT.md`.
- **A real `docker compose up` could not be run.** This environment's network blocks every container registry (Docker Hub returns 403). The same code path was tested instead: an empty Postgres database followed by backend start-up.

### Open follow-ups from the first fixes (status at the end of 15 Oct)
- **E-02 data cleanup:** done in code — revision `0069_users_email_ci_unique` stops (and names the accounts) when two addresses differ only by letter case, and otherwise lower-cases every address and adds a unique index on `lower(email)`; databases adopted without revisions get the same check at start-up (health 503 until cleaned). Verified on Postgres. Each deployment still has to clean up any accounts it names.
- **E-02 config:** done — `docker-compose.yml` defaults `SUPER_ADMIN_EMAILS` to `admin@datalytics.local` only.
- **Flaky test:** fixed in round 1 (agent C): the CopilotChat timer no longer fires after teardown; later full runs had no unhandled errors.

## How to use this plan

- Work **phase by phase**. Inside a phase, the order shown is the recommended order.
- Every task in the detailed sections has the same parts:
  - **Problem**, and **Root cause / where** (file, function and line, marked *confirmed* or *unconfirmed*)
  - numbered **Fix** steps
  - **Tests**: an automated test to add, plus one manual check
  - **Effort**: S < 2 h, M ≈ half a day to 1 day, L > 1 day
  - **Depends on**
- Tick the box in the checklist when a task is merged. Run `pytest` (backend, Python 3.12) and `npm test` (frontend) before each merge, then re-run the matching browser check.
- Tasks marked **Decision needed** are product choices, not bugs. Decide them first, because some Phase 5 tasks depend on the answers.

### Summary

| | Tasks | Effort |
|---|---|---|
| Critical | 3 | ≈ 2 dev-days |
| High | 33 | ≈ 26 dev-days |
| Medium | 86 | ≈ 44 dev-days |
| **Total** | **122** | **≈ 73 dev-days** (rough, one developer; S = 1.5 h, M = 1 day, L = 2–3 days) |

> **Severity correction for B-01.** The evaluation rated the `init.sql` schema gap Critical. Since commit `5ffbb917`, `docker-compose.yml` no longer mounts `postgres/init.sql`, so a normal fresh Docker install on this branch is **not** affected. It is now **High**: it still breaks databases first built from `init.sql` (developer volumes created before that commit, or anyone following README / `first-stop.md`).

> **Two new Critical findings from tracing the code** (not visible in the UI test):
> - **E-01:** the server lets an org admin edit or delete the platform super admin, not just show the buttons.
> - **E-02:** user emails are checked case-sensitively, but the super-admin allowlist is compared lower-cased. Any org admin can therefore create `ADMIN@datalytics.local` and get platform super-admin rights.
>
> Fix both before anything else. *(Both fixed on 15 Oct: `55c6ac61`.)*

## Phase 1 — Security & access (do first)

Privilege escalation, data leaving the app against the share settings, guest links, row security, admin validation. 9 tasks, ≈ 5 dev-days.

- [x] **E-01** — Block org admins from editing or deleting platform super-admin accounts · *Critical, effort S* · ✅ **done** `55c6ac61`
- [x] **E-02** — Normalise emails case-insensitively and close the super-admin allowlist escalation · *Critical, effort M* · ✅ **done** `55c6ac61`
- [x] **F-01** — Serve map settings to guest/embed viewers and stop 401 → /login redirects on public pages · *Critical, effort M* · ✅ **done** `16a84654`
- [x] **F-02** — Enforce the "may download" right on the server for every export path (print, PPTX, widget CSV/Excel) · *High, effort M* · ✅ **done** `1cd6ca3d`
- [x] **E-03** — Expand MYSCOPE() during row-rule validation so org-chart rules can be saved · *High, effort S* · ✅ **done** `602cf081`
- [x] **E-04** — Validate email and password server-side for users and new org admins · *High, effort M* · ✅ **done** `5e79eea4` `b5f1a220`
- [x] **E-05** — Stop pre-selecting the Admin role and the first dataset in admin forms · *High, effort S* · ✅ **done** `5e79eea4`
- [x] **E-06** — Reject negative quota values (client and API) · *High, effort S* · ✅ **done** `e8a98b7e`
- [x] **E-07** — Connection rules: show why the table list is empty and link to sync · *High, effort S* · ✅ **done** `09b58690`

## Phase 2 — Broken behaviour & data safety

Hard errors, data that can be silently overwritten, stale or wrong results, and a red CI. 15 tasks, ≈ 8 dev-days.

- [x] **B-14** — Update the stale widget-type count in the backend parity test (CI red) · *Medium, effort S* · ✅ **done** `ee5d6cab`
- [x] **B-13** — Give the test suite its own DuckDB metadata cache path · *Medium, effort S* · ✅ **done** `5b5d97c7`
- [x] **B-01** — Close the fresh-install schema gap (8 columns missing on an init.sql-built database) · *High, effort S* · ✅ **done** `62a54a56`
- [x] **B-02** — Fix the ImportError behind "Warn me on every refresh" (guided setup step 3) · *High, effort S* · ✅ **done** `96f016a5`
- [x] **B-08** — Default Edit cells to a unique row key and say how many rows an edit changes · *High, effort M* · ✅ **done** `22dd7dfc`
- [x] **B-07** — Reload the data grid when the last filter is removed · *High, effort S* · ✅ **done** `77579bb9`
- [x] **AD-04** — Ignore stale scan responses on the Insights hub · *High, effort S* · ✅ **done** `b7b5ad04`
- [x] **B-06** — Show the sheet picker for multi-sheet XLSX uploads · *High, effort S* · ✅ **done** `fe201a16`
- [x] **B-09** — Explain why a dataflow cannot be built on a governed dataset · *High, effort M* · ✅ **done** `326a8c1e`
- [x] **B-05** — Save the derived fields the plain dashboard design uses (6/17 widgets broken) · *High, effort M* · ✅ **done** `4570c393`
- [x] **C-04** — Drop a stale widget selection when the page changes, so no 404 PATCH is sent to a widget on another page · *High, effort S* · ✅ **done** `fd2e2d0b`
- [x] **C-05** — Show the dataset chosen in "Create a dashboard" as soon as the builder opens · *High, effort S* · ✅ **done** `ea67a167`
- [x] **C-01** — Render tiles already on screen without needing a scroll, in View and in Present · *High, effort M* · ✅ **done** `9ba3e2dd`
- [x] **AD-05** — Remove "Pin finding", which promises a dashboard that doesn't exist · *High, effort S* · ✅ **done** `7c2f35c5`
- [x] **C-03** — Fix the seeded demo configs: the World Sales Map contour tile and the "Can I trust this data?" use case · *High, effort M* · ✅ **done** `f3b1d3de`

## Phase 3 — Fail fast without AI

One shared model-health gate and timeouts, then the features that hang when the model is down. Do AD-01 first; the rest build on it. 7 tasks, ≈ 9 dev-days.

- [x] **AD-01** — Add one shared model health gate and a per-step AI timeout (fail fast when the model is down) · *High, effort L* · ✅ **done** `a4c0795d` + round 2 `e5b954a4`
- [x] **AD-02** — Make Ask AI suggestion cards respect "new questions are paused" · *High, effort S* · ✅ **done** `8f3a1808`
- [x] **AD-03** — Time out stuck automation steps, watch for stale "running" steps, and notify on failure · *High, effort M* · ✅ **done** `3dde8572`
- [x] **F-03** — Make AI dashboard suggestions fail fast and fall back to the statistics engine when the model is unreachable · *High, effort M* · ✅ **done** (with B-10) `6967affb`
- [x] **B-10** — Make "Suggest dashboards" with a blank goal truly model-free · *High, effort S* · ✅ **done** (with F-03) `6967affb`
- [x] **B-03** — Stop guided setup swallowing sync errors and show the running read · *High, effort M* · ✅ **done** `3431145d`
- [x] **B-04** — Give a stuck metadata sync a timeout and a Cancel · *High, effort L* · ✅ **done** `03a8eb6c`

## Phase 4 — Charts & number formatting (High)

One shared formatter, then the broken chart types and map roles. 6 tasks, ≈ 4 dev-days.

- [x] **C-02** — One shared number formatter for every value in tables, crosstabs, matrices, KPIs and cards · *High, effort M* · ✅ **done** `8490df7f`
- [x] **C-06** — Make the Word cloud draw its words and reject a number as "Word text" · *High, effort S* · ✅ **done** (step 4 in 4f2830c6) `9b30ba55` `4f2830c6`
- [x] **C-07** — Give Scatter an X measure and a Y measure, and say so when nothing can be plotted · *High, effort M* · ✅ **done** `6b4541b7` `bdc56cfe` `e01c3821` + round 2 `24a97a46`
- [x] **C-08** — Label Sankey nodes and colour flows by their source · *High, effort S* · ✅ **done** `0e2a9b8f`
- [x] **C-09** — Put each clicked field into a role of the matching type and validate map coordinates · *High, effort M* · ✅ **done** `aa05f916` + round 2 `dd820ae2`
- [x] **C-10** — Make a map's lat/lon or country mode explicit, show a placeholder when it is unassigned, and hide the country-match note in lat/lon mode · *High, effort M* · ✅ **done** (mode hint in eccc0ced) `438c8ee6` `eccc0ced`

## Phase 5 — Medium issues

76 tasks, ≈ 38 dev-days. Grouped by area; do them in any order within an area.

### Admin, security & access control (10)

- [x] **E-09** — Audit connection (Ask AI) rule and custom connector changes · *Medium, effort S* · ✅ **done** `ef6bd2c2`
- [x] **E-10** — Validate connection rule columns against the table · *Medium, effort S* · ✅ **done** `d1e9c6ed`
- [x] **E-11** — Type-check custom connector fields (number port, TLS select) · *Medium, effort S* · ✅ **done** `d4c9527d`
- [x] **E-12** — Show a friendly message for a tile whose measure uses a hidden column (QA SEC-02) · *Medium, effort S* · ✅ **done** `2ac8a652`
- [x] **E-13** — Hide measures and calculated columns built on hidden columns from restricted roles · *Medium, effort M* · ✅ **done** `4bed887a`
- [x] **E-14** — Compute dataset row and column counts after row and column security · *Medium, effort M* · ✅ **done** `1118a825` `037da8a3`
- [x] **E-15** — Enforce unique role names per organization · *Medium, effort M* · ✅ **done** `a6e5466e`
- [x] **E-16** — Add search, filters and pagination to the Users list · *Medium, effort M* · ✅ **done** `6909fad8`
- [x] **E-17** — Make the LLM "Test connection" fail fast with a readable reason · *Medium, effort S* · ✅ **done** `68e57f0a`
- [x] **E-18** — Let admins set and see an org unit's "match value" · *Medium, effort S* · ✅ **done** `ee8f2705` + round 2 `5dd23346` `4757635d`

### Sharing, publishing, templates & suggestions (11)

- [x] **F-04** — Restore an archived dashboard as a draft (or ask before re-publishing) · *Medium, effort S* · ✅ **done** `1ca89f6b`
- [x] **F-05** — List team-shared dashboards under "My team" even when the reader is also named personally · *Medium, effort S* · ✅ **done** `9f3c2295`
- [x] **F-06** — Default a new person share to "Can view" · *Medium, effort S* · ✅ **done** `92fd8e7f`
- [x] **F-07** — Make the New-user role select start empty ("Select a role…") · *Medium, effort S* · ✅ **done** `3feb502c`
- [x] **F-08** — Confirm before publishing to (or unpublishing from) the whole organisation · *Medium, effort S* · ✅ **done** `125ae1be`
- [x] **F-09** — Guard the org-wide "Ask for approval before publishing" switch · *Medium, effort S* · ✅ **done** `c77b289f` + round 2 `24de856b`
- [x] **F-10** — Add a "Publish these changes" action to the Publishing tab · *Medium, effort S* · ✅ **done** `06d3cd9d`
- [x] **F-12** — Do not show row counts in the measure's currency format, and label the count donut correctly · *Medium, effort S* · ✅ **done** `c3c7c926`
- [x] **F-13** — Template mapping: prefer a country-level column for "place" and do not reuse the main split's column · *Medium, effort S* · ✅ **done** `bf60d815`
- [x] **F-14** — Stop cutting small-cardinality suggested bar charts at 12 categories · *Medium, effort S* · ✅ **done** `999c0249` + round 2 `858b3479`
- [x] **F-16** — Make model-widget display options (Key influencers) findable and stop accidental Duplicate · *Medium, effort M* · ✅ **done** `732a05f8` + round 2 `14138961`

### Data, upload, connections & guided setup (21)

- [x] **B-11** — Fail fast and say so when the AI model is unreachable · *Medium, effort L* · ✅ **done** `0dcc5586` `12cd8462`
- [x] **B-12** — Return the plain data checks first, add AI items later · *Medium, effort M* · ✅ **done** `c11ae02c`
- [x] **B-15** — Stop the 404 on every dataset page load (GET /datasets/{id}/analysis) · *Medium, effort S* · ✅ **done** `261bd9b9`
- [x] **B-16** — Let the "Add step" menu close on Esc and outside click · *Medium, effort S* · ✅ **done** `a296dbe4`
- [x] **B-17** — Draw the chart for insight cards about calculated columns (empty OUTLIER IMPACT tile) · *Medium, effort S* · ✅ **done** `2685a123`
- [x] **B-18** — Keep the preselected dataset on Ask when the AI is offline · *Medium, effort M* · ✅ **done** `1d4da9d0` + round 2 `9da68f35`
- [x] **B-19** — Make the DirectQuery Data tab stable and honest (paged ORDER BY, disabled tools) · *Medium, effort M* · ✅ **done** `1c049626`
- [x] **B-22** — Reject unsupported files when they are added to the upload queue · *Medium, effort S* · ✅ **done** `8aa2d25b`
- [x] **B-23** — Mark connection types whose driver is not installed in the type grid · *Medium, effort S* · ✅ **done** `60f7c218`
- [x] **B-24** — Make the import dataset name easy to replace and less collision-prone · *Medium, effort S* · ✅ **done** `673c0c8d`
- [x] **B-25** — Fix "We read 0 rows" on a new DirectQuery dataset · *Medium, effort S* · ✅ **done** `e3f06a11`
- [x] **B-27** — Do not hide a user's own datasets as "test-looking" in pickers · *Medium, effort S* · ✅ **done** `a15d2ab6`
- [x] **B-28** — Widen the Inspect outliers dialog so the inspected column is visible · *Medium, effort S* · ✅ **done** `f39b2a52`
- [x] **B-29** — Refresh the connection review page when a sync finishes · *Medium, effort M* · ✅ **done** `a9b65348`
- [x] **B-30** — Say "row count unknown" instead of "0 rows", and pluralise "tables" · *Medium, effort S* · ✅ **done** `9e531904`
- [x] **B-31** — Make "Show details" in setup step 1 not leave the wizard by surprise · *Medium, effort S* · ✅ **done** `ad99ed43`
- [x] **B-32** — Recount rows and columns after one-click fixes · *Medium, effort M* · ✅ **done** `a6dbbbca`
- [x] **B-33** — Confirm before one-click fixes change a dataset already in use · *Medium, effort S* · ✅ **done** `6e8f0bc6`
- [x] **B-34** — Add the two missed checks: numbers stored as text in the source, and end-before-start dates · *Medium, effort M* · ✅ **done** `169c8a8d`
- [x] **B-35** — Let the dashboard designer answer "by <entity>" through a linked key · *Medium, effort L* · ✅ **done** round 2 `41a9d5e7`
- [x] **B-36** — Stop proposing meaningless derived metrics and totals · *Medium, effort M* · ✅ **done** `d999762b` + round 2 `446237fb`

### Dashboards, builder & charts (18)

- [x] **C-11** — Default percentages and ratios to Average, never Sum, on every role and every aggregation path · *Medium, effort S* · ✅ **done** `3d28f12c` + round 2 `cc55316e`
- [x] **C-12** — Keep the hover toolbars inside their own tile, in View and Edit · *Medium, effort S* · ✅ **done** `fea8651f` + round 2 `408734be`
- [x] **C-13** — Fit KPI, card and gauge numbers inside their tiles · *Medium, effort S* · ✅ **done** `62cf9993` + round 2 `62be2d4c`
- [x] **C-14** — Show the "Needs Dimension" placeholder for a pie (or any category chart) given only a measure · *Medium, effort S* · ✅ **done** `a3621ca1`
- [x] **C-15** — Label sunburst segments and colour them by top-level branch · *Medium, effort S* · ✅ **done** `f01f3b28`
- [x] **C-16** — Make box-plot category labels readable · *Medium, effort S* · ✅ **done** `0ba650f2` + round 2 `3f90b9f8`
- [x] **C-17** — Stop the false "changed in another session" banner after my own classification or comment · *Medium, effort S* · ✅ **done** `da356a7a` + round 2 `3b5ee2ff`
- [x] **C-18** — Stop the Suggest pane counting distinct years as if they were identifiers · *Medium, effort S* · ✅ **done** `1dcb03ea` + round 2 `652c4291`
- [x] **C-19** — Make widget resize reliable, with no page text selected during the drag · *Medium, effort S* · ✅ **done** `f903ee26` + round 2 `7427ee4f`
- [x] **C-20** — Add "Duplicate" (Save as copy) to the dashboard card menu · *Medium, effort M* · ✅ **done** `dee483ec` + round 2 `c864dcfc`
- [x] **C-21** — Add width × height inputs for a Custom page size · *Medium, effort M* · ✅ **done** round 2 `cf6b5e41` `8a097419`
- [x] **C-22** — Give dual-axis charts enough width when added or auto-laid-out · *Medium, effort S* · ✅ **done** `b249eeee`
- [x] **C-23** — Make "Split into multiples by" a required data role for Small multiples · *Medium, effort S* · ✅ **done** `0e65e6c6` + round 2 `eca493f6`
- [x] **C-24** — Show the whole time range on a dual-axis time series by default · *Medium, effort S* · ✅ **done** `b3eb40ca` + round 2 `fed35edb` `28bd7c59`
- [x] **C-26** — Use one picker interaction everywhere: apply the choice on click in multi-field roles · *Medium, effort S* · ✅ **done** `10b256d1`
- [x] **C-27** — Accept a field dropped onto a role in the Properties panel · *Medium, effort S* · ✅ **done** `4f19426f`
- [x] **C-28** — Let the field picker take the single match on Enter, and give each option a distinct accessible name · *Medium, effort S* · ✅ **done** `ad84a293` + round 2 `d228e51a`
- [x] **C-29** — Show one readable count per bubble on the World Sales Map "Origin density" tile (QA MAP-02) · *Medium, effort S* · ✅ **done** `3e9be7bd` + round 2 `2fd968c2`

### Shell, Ask AI, Insights, automations & monitoring (16)

- [x] **AD-06** — Make "View full scan →" show the scan just seen, and stop the analysis 404s (INS-02) · *Medium, effort M* · ✅ **done** `c2cf8f19`
- [x] **AD-07** — Stop labelling non-significant per-row findings STANDOUT, and chart them the way they are stated · *Medium, effort M* · ✅ **done** `e0c175da`
- [x] **AD-08** — Keep the chosen dataset when an Insights filter chip hides it · *Medium, effort S* · ✅ **done** `121b9415`
- [x] **AD-09** — Fix the Ask AI composer draft: clear it on New chat, and disable "Edit question" while paused · *Medium, effort S* · ✅ **done** `e2eccfd6`
- [x] **AD-10** — Say "AI is not allowed for this dataset" before the first question · *Medium, effort S* · ✅ **done** `47cd8138`
- [x] **AD-11** — Stop suggesting SUM of latitude, percentages, body measures and per-row ID columns in Ask AI · *Medium, effort S* · ✅ **done** `46a66163` + round 2 `847c37cc`
- [x] **AD-12** — Keep the deep-link target through login · *Medium, effort S* · ✅ **done** (with AD-13) `35e2ad0a`
- [x] **AD-13** — Replace the bare "Loading…" during auth bootstrap with the app loader · *Medium, effort S* · ✅ **done** (with AD-12) `35e2ad0a`
- [x] **AD-14** — Close the notifications panel on Escape, on route change and when the command palette opens · *Medium, effort S* · ✅ **done** `696d002b`
- [x] **AD-15** — Lay out the Home stat cards 2×2 on phones · *Medium, effort S* · ✅ **done** `f14695c1`
- [x] **AD-16** — Show the demo weekly schedule (and paused or on-demand schedules) on Refresh & jobs, not "—" · *Medium, effort S* · ✅ **done** `a8346153`
- [x] **AD-17** — List automation runs and data-check runs in Monitoring · *Medium, effort M* · ✅ **done** `2687a49b`
- [x] **AD-18** — Write Activity details in plain words (no "key=None" or "grant:3:") · *Medium, effort M* · ✅ **done** `ae51a9f5`
- [x] **AD-19** — Add paging, filters and row detail to Activity; decide on logging Ask AI · *Medium, effort M* · ✅ **done** `b020e3d4`
- [x] **AD-20** — Stack the Monitoring tables (Activity, Jobs, Deliveries) as cards on phones · *Medium, effort S* · ✅ **done** `f126d9bd`
- [x] **AD-21** — Stop the automation row squeezing the dataset name to one letter per line on phones · *Medium, effort S* · ✅ **done** `ec8e8248`

## Decisions needed (product choices, not bugs)

Agree on these first. Each one has its options in the detailed section.

- [x] **E-08** — Define a per-role capability (permission) matrix · *High, effort L* · ✅ **done** round 2 `10865916` `574524a1`
- [x] **B-20** — Explain why data checks are not offered for live datasets · *Medium, effort S* · ✅ **done** `8e4b2565`
- [x] **B-21** — Decide on dataset-scoped glossary terms and a column link from the Columns tab · *Medium, effort L* · ✅ **done** round 2 `c1091381`
- [x] **B-26** — Decide whether the seeded demo connection is synced at seed time · *Medium, effort S* · ✅ **done** `70a708c6`
- [x] **C-25** — Decide how to present the negative revenue axis on daily time series · *Medium, effort S* · ✅ **done** (decision: keep data; cheap axis treatment) `b3821164`
- [x] **C-30** — Decide whether "Create a dashboard" may proceed with an empty name (QA DASH-04) · *Medium, effort S* · ✅ **done** (decision: require a name) `eade000f`
- [x] **F-11** — Add a per-user "AI off" choice to the top-bar model picker · *Medium, effort M* · ✅ **done** (decision: build it) `216869d9`
- [x] **F-15** — Add "Add all shown" to the builder's Suggestions pane · *Medium, effort M* · ✅ **done** (decision: build it) `a7abc97f`
- [x] **AD-22** — Decide on automation management (name, edit, delete, schedule/trigger), and allow delete/retry for stopped runs · *Medium, effort S* · ✅ **done** (decision: stopped runs only) `5194b095`

Several fix tasks also include a small decision step: B-03, E-02 (store super-admin as a DB flag?), F-02 (document what "no downloads" can and can't guarantee), AD-05 (Pinned section vs remove), AD-17 and AD-19 (what to log).

---

# Detailed tasks
## Admin, security & access control

### E-01 — Block org admins from editing or deleting platform super-admin accounts
- **Status:** ✅ Done on 15 Oct 2026 in `55c6ac61` (see Progress at the top for what changed vs this text).
- **Severity:** Critical
- **Evidence:** #24 · E-110..112 (E-111-example-admin-users.png), EVALUATION top issues "E-111"
- **Problem:** On a Default-org admin's Users page, the platform super admin admin@datalytics.local has working Edit and Delete buttons. The server lets that org admin change the account's email or password or demote it, which is a takeover of the whole platform. They can also delete it.
- **Root cause / where:** `backend/app/routers/admin.py:165` `update_user` (PATCH, not PUT) and `:202` `delete_user` only call `check_org(...)`, plus a self-delete check on delete. Neither checks `dependencies.is_super_admin(user)` (`backend/app/dependencies.py:139`). `list_users` (`admin.py:89`) also returns the super admin with no marker, and `UserOut.is_super_admin` (`schemas.py:785`) is only set by `/auth/me`. The seed puts the super admin in the Default org (`scripts/seed_dev_accounts.py` PLAN, `None` org), so every Default-org admin can reach it. **Confirmed from the code: the server allows it.** A password reset through PATCH also sets `tokens_valid_after`, which signs the real super admin out.
- **Fix:**
  1. Add a helper `_refuse_if_platform_admin(target, current_user)` in admin.py. It raises 403 "Platform administrators can only be changed by a platform administrator" when `is_super_admin(target) and not is_super_admin(current_user)`.
  2. Call it at the top of `update_user`, `delete_user` and `set_user_org_units` (`admin.py:903`), before any change is made.
  3. In `list_users`, set `u.is_super_admin = is_super_admin(u)` on each row, the same way auth.py:73 does.
  4. Frontend `frontend/src/pages/admin/AdminUsers.tsx:254-265`: when `u.is_super_admin && !me.is_super_admin`, show a "Platform admin" tag and hide Edit and Delete.
- **Tests:** automated: `backend/tests/test_admin_users.py` gets `test_org_admin_cannot_patch_super_admin` (403, email/password/role unchanged), `test_org_admin_cannot_delete_super_admin` (403, row still exists) and `test_super_admin_can_edit_super_admin` (200). Use `monkeypatch.setattr(settings, "super_admin_emails", ...)` as in test_platform.py. `frontend/src/pages/admin/AdminUsers.test.tsx` checks that a super-admin row shows no Edit or Delete for a non-super viewer. Manual: sign in as admin@example.invalid, open /admin/users, and confirm the super-admin row has no buttons. A curl PATCH to that row returns 403.
- **Effort:** S
- **Depends on / related:** E-02

### E-02 — Normalise emails case-insensitively and close the super-admin allowlist escalation
- **Status:** ✅ Done on 15 Oct 2026 in `55c6ac61` (see Progress at the top for what changed vs this text).
- **Severity:** Critical
- **Evidence:** #5, #18 · E-06/07/08, E-64..70 (E-65-settings-search-super.png)
- **Problem:** "DEMO-GLOBAL@example.invalid" was created next to demo-global@example.invalid. The super-admin allowlist shows "admin@datalytics.local,admin,admin@admin.com". Together these let any org admin in any tenant make themselves a platform super admin. Not executed, confirmed from the code.
- **Root cause / where:**
  - `backend/app/dependencies.py:139` `is_super_admin` compares **lower-cased** email against the allowlist.
  - `admin.py:102` `create_user`, `:172` `update_user` and `:131` `bulk_create_users` check duplicates with **exact-case** `User.email == body.email`. `models.py:603` `User.email unique=True` is also case-sensitive.
  - `auth.py:26` `login` matches the exact string.
  - Result: a Contoso admin can POST `/admin/users {"email":"ADMIN@datalytics.local", ...}`. The duplicate check passes, `is_super_admin` returns True, and that person signs in with the upper-case address and gets every `/platform/*` route across all orgs. Two allowlist entries that may not exist yet make it easier still: `docker-compose.yml:55` defaults `SUPER_ADMIN_EMAILS` to `admin@datalytics.local,admin,admin@admin.com`, and create_user does no email validation (see E-04).
  - Confirmed in code; not run.
- **Fix:**
  1. Add `normalize_email(s) -> str` (strip + lower) in `backend/app/core/security.py`. Use it in create_user, update_user, bulk_create_users, `auth.login`, `platform.create_org` (`platform.py:35`), SSO provisioning and `scripts/seed_dev_accounts.py`.
  2. Add Alembic migration `0069_users_email_ci_unique`. It lower-cases existing emails, fails loudly with the list of collisions if any exist, and creates a unique index on `lower(email)`. Postgres uses a functional index; SQLite tests use the lower-cased column.
  3. In create_user, update_user and bulk_create_users, refuse with 403 any target email that `is_super_admin` would accept unless the caller is a super admin.
  4. Change the compose default to `admin@datalytics.local` only. Drop the bare `admin` and `admin@admin.com`, and document the variable in `.env.example`.
  5. Follow-up, Decision needed: store super-admin status as a DB flag instead of keying it off an editable email.
- **Tests:** automated: `backend/tests/test_admin_users.py` gets `test_create_user_case_variant_of_existing_email_is_400`, `test_org_admin_cannot_create_user_with_allowlisted_email` (403 even in a different org and different case), `test_update_user_cannot_rename_to_allowlisted_email` and `test_login_is_case_insensitive`. `backend/tests/test_alembic_migrations.py` covers the new revision. Manual: as admin@contoso.invalid, try to create ADMIN@datalytics.local; the server refuses it. Settings › Platform admins shows only the real address.
- **Effort:** M
- **Depends on / related:** E-01, E-04

### E-03 — Expand MYSCOPE() during row-rule validation so org-chart rules can be saved
- **Severity:** High
- **Evidence:** #9 · E-24..31 (E-27-row-rule-myscope.png, E-28), EVALUATION top issue "E-28"
- **Problem:** The Quick setup option "Viewer's org-chart units (and below)" generates `region in MYSCOPE()`. Create fails with "Invalid filter expression: name 'MYSCOPE' is not defined", so the org-chart (hierarchical) row security feature can't be used from the UI.
- **Root cause / where:** `backend/app/routers/admin.py:229` `_validate_filter_expr` only calls `core/rls.py:116` `apply_user_context`. Its `_USER_TOKEN` regex (`rls.py:14`) covers USEREMAIL/USERID/USER/ORGID/ORGNAME, not MYSCOPE. `apply_scope` (`rls.py:52`) is never called on the validation path, so the raw `MYSCOPE()` reaches `apply_filter_expr` (import mode) or `translate_filter_expr` (DirectQuery) and raises a NameError. `rule_preflight` (`admin.py:413-433`) has the same gap. At query time `resolve_rls_expr` (`rls.py:196-203`) does expand it. **Confirmed.**
- **Fix:**
  1. In `_validate_filter_expr` and `rule_preflight`, after `apply_user_context`, run `expr = apply_scope(expr, ["__scope_validator__"])`. A one-element placeholder list keeps `col in [...]` valid for both the pandas evaluator and `sql_expr` (In/List are supported, `sql_expr.py:118`).
  2. Keep the stored `filter_expr` unchanged so the token is still saved.
  3. Optionally, when the RHS is MYSCOPE, warn if the column is not a string column.
- **Tests:** automated: `backend/tests/test_admin_row_security_rules.py` gets `test_create_rule_with_myscope_is_accepted` (200, stored expression still contains `MYSCOPE()`), `test_myscope_rule_with_unknown_column_is_400` and a DirectQuery variant (dataset with `mode="directquery"` and columns). `backend/tests/test_hierarchical_rls.py` gets an end-to-end test: save through the API, then `resolve_rls_expr` expands it for a placed user. Manual: on /admin/row-security-rules, pick Quick setup → org-chart units on Demo — Sales/region, click Create, and the rule saves.
- **Effort:** S
- **Depends on / related:** E-18

### E-04 — Validate email and password server-side for users and new org admins
- **Severity:** High
- **Evidence:** #3, #4, #20 · E-02/03 (E-03-new-user-invalid-email.png), E-75..81 (E-81-new-org-short-password.png)
- **Problem:** The New user dialog created "not-an-email" with password "x". New organization accepted a 1-character admin password.
- **Root cause / where:** `backend/app/schemas/schemas.py:808` `UserCreate` and `:814` `UserUpdate` have plain `str` email and password with no constraints. `admin.py:98` `create_user` and `:165` `update_user` do no checks. `bulk_create_users` (`admin.py:139`) only checks for `"@"`. `routers/platform.py:28` `OrgCreate.admin_password` has `Field(min_length=1)` and `:36` only checks for `"@"`. On the frontend, `AdminUsers.tsx:66` uses `type="email"`, but `handleSave` (`:33`) only checks that the field isn't empty. **Confirmed.**
- **Fix:**
  1. Add `validate_email(s)` to `core/security.py`: a `local@domain.tld` regex that allows `.local` and `.invalid`. Don't use EmailStr; see the `sso.py:41` comment.
  2. Add `validate_password(pw)`: at least 8 characters (configurable `password_min_length` in config.py) and not equal to the email.
  3. Apply both in create_user, update_user (only when the field is sent), bulk_create_users (per-row error) and `platform.create_org`. Return 422 with a readable detail.
  4. Frontend: in `AdminUsers.tsx` handleSave and `PlatformOrgs.tsx:45`, check the email format and the minimum length, and show the error inline under the field.
- **Tests:** automated: `backend/tests/test_admin_users.py` gets `test_create_user_invalid_email_is_422`, `test_create_user_short_password_is_422` and `test_bulk_import_reports_short_password_row`. `backend/tests/test_platform.py` gets `test_create_org_short_admin_password_is_422`. `frontend/src/pages/admin/AdminUsers.test.tsx` checks that an invalid email blocks submit. Manual: create "not-an-email"/"x", which is rejected with a clear message.
- **Effort:** M
- **Depends on / related:** E-02

### E-05 — Stop pre-selecting the Admin role and the first dataset in admin forms
- **Severity:** High
- **Evidence:** #2, #10 · E-02/03 (E-02-new-user-dialog.png), E-24..31 (E-25-new-row-rule-dialog.png)
- **Problem:** New user opens with "Admin (admin)" already selected, so clicking Create without looking makes a full org admin. New row rule and Auto-generate pre-fill the Admin role, which bypasses all rules, and the first dataset.
- **Root cause / where:** `frontend/src/pages/admin/AdminUsers.tsx:27` `useState(initial?.role.id ?? roles[0]?.id ?? '')`. The "Select a role…" placeholder option exists (`:81`) but is never the initial value. The same pattern appears in `AdminRowSecurityRules.tsx:59-60` (RuleModal), `:265-266` (Auto-generate) and `AdminColumnSecurityRules.tsx:38`. **Confirmed.**
- **Fix:**
  1. For new items, initialise `roleId` and `datasetId` to `''`. Keep the `initial?.…` value for edits.
  2. Make sure each select has a `<option value="">Select…</option>` placeholder (add one in the row and column rule modals if missing).
  3. In the row and column rule modals, leave org-admin roles out of the role list, or disable them with "Admins bypass row security", since a rule on them never applies (`rls.py:175`).
- **Tests:** automated: `frontend/src/pages/admin/AdminUsers.test.tsx` checks that the role select's initial value is "" and that Create without a role shows the roleRequired error. `AdminRowSecurityRules.test.tsx` checks that role and dataset start empty and org-admin roles are not offered. Manual: open each dialog; nothing is pre-selected.
- **Effort:** S
- **Depends on / related:** —

### E-06 — Reject negative quota values (client and API)
- **Severity:** High
- **Evidence:** #19 · E-75..81 (E-77-quota-negative.png, E-78-quota-negative-save.png)
- **Problem:** Northwind "Max queries/day" = -3 saved without any error and showed "Queries today: 0 / -3", which blocks every query for that org.
- **Root cause / where:** `backend/app/routers/platform.py:112` `OrgQuotaSet`: `max_queries_per_day`, `max_agent_asks_per_day`, `max_storage_mb` and `max_concurrent_asks` are `int | None` with no `ge`. Only the two AI-token fields have `ge=0`. On the frontend, `PlatformOrgs.tsx:101` `toNullableInt` uses `Number(v)`, which accepts negatives and NaN, and the inputs at `:242-256` are free text. **Confirmed.**
- **Fix:**
  1. Add `Field(default=None, ge=0)` to the four fields. Use `ge=1` for `max_concurrent_asks` if 0 is meaningless; decide that with whoever owns quotas.
  2. Frontend: use `type="number" min=0 step=1 inputMode="numeric"`. Validate in `toNullableInt` (an integer ≥ 0 or empty) and show an inline error instead of submitting.
- **Tests:** automated: `backend/tests/test_platform.py` gets `test_negative_quota_is_422` (parametrised over all six fields). `frontend/src/pages/admin/PlatformOrgs.test.tsx` checks that -3 shows an inline error and the API is not called. Manual: enter -3, which is refused; leaving the field empty means unlimited.
- **Effort:** S
- **Depends on / related:** —

### E-07 — Connection rules: show why the table list is empty and link to sync
- **Severity:** High
- **Evidence:** #11 · E-35..38 (E-38-connection-rules-nile.png)
- **Problem:** For the Postgres connection "QA B Nile Express", the TABLE dropdown is empty, so no Ask AI rule can be added. Meanwhile the page says in red "Every role … sees every row".
- **Root cause / where:** `frontend/src/pages/admin/ConnectionRowPolicies.tsx:45-53` fills TABLE from `metadataApi.review(sourceId).datasets`, which are the source-catalog `SourceObject` rows (`backend/app/routers/metadata.py:171` `review_queue`). That list is empty until the connection's metadata sync has finished. The E-38 screenshot was taken at 20:17. Area B's notes show the Nile sync had failed earlier ("Interrupted by a server restart", 0 tables) and only finished at 20:29 (B2-54). So the empty list comes from sync state; the defect is that the page gives no explanation and no way forward. `create_row_policy` (`backend/app/routers/agent.py:500`) needs a `source_object_id`, so a sync is required. Partly confirmed: code path confirmed, sync state inferred from area B's notes.
- **Fix:**
  1. When `objects.length === 0`, replace the add form with a notice using `review.source.sync_status` and `last_synced_at`: "Datalytics hasn't read this connection's tables yet", with a "Read the database now" link to `/connections/{id}/review` or `/setup/{id}`.
  2. Reword `pg.adminSecurity.crp.noRules` (`frontend/src/i18n/pages/adminSecurity.ts:176`) so it is accurate whether or not tables exist.
  3. Add the page to the Admin rail (Low item from the same notes).
- **Tests:** automated: `frontend/src/pages/admin/ConnectionRowPolicies.test.tsx` checks that review returning `datasets: []` with `sync_status: 'failed'` shows the sync notice and link and hides the add button. Manual: on an unsynced connection, the notice appears; after a sync, its tables are listed.
- **Effort:** S
- **Depends on / related:** E-10; area B sync tasks

### E-08 — Define a per-role capability (permission) matrix
- **Severity:** High
- **Evidence:** #6 · E-14..18 (E-15-new-role-dialog.png), E-84..90 notes (analysts see Upload / New connection / New dashboard)
- **Problem:** A role is only a name plus an "Org admin" checkbox. There is no way to stop a role from uploading data, creating connections or creating dashboards.
- **Root cause / where:** `backend/app/models/models.py:585` `Role` has only `name` and `is_org_admin`. Creation endpoints check only `get_current_user`: `routers/datasets.py:561` `upload_dataset`, `routers/data_sources.py:124` `create_data_source` and `routers/reports.py:289` `create_report`. Per-report and per-dataset capability exists (`core/capability.py`), but nothing exists per role. **Confirmed (missing feature).**
- **Fix:** **Decision needed.** This is a new feature rather than a regression, and product has to choose the capability set first.
  1. Add `Role.permissions` (JSON) with a fixed set such as `upload_data`, `create_connection`, `create_dashboard`, `use_ask_ai`, `export`. Write a migration that defaults existing roles to all true so nothing breaks.
  2. Add `require_role_permission(name)` in `dependencies.py` and apply it to the creation endpoints.
  3. Add a matrix of checkboxes to the role dialog in `AdminRoles.tsx`, and expose the permissions in `/auth/me` so the UI can hide actions.
- **Tests:** automated: `backend/tests/test_admin_roles.py` covers permissions round-tripping. A new `backend/tests/test_role_permissions.py` checks that a role without `upload_data` gets 403 on POST /datasets. `AdminRoles.test.tsx` covers the matrix. Manual: turn off Upload for Analyst; the button disappears and the API returns 403.
- **Effort:** L
- **Depends on / related:** —

### E-09 — Audit connection (Ask AI) rule and custom connector changes
- **Severity:** Medium
- **Evidence:** #13, #15, #16 · E-35..38, E-47..51, E-60..63
- **Problem:** Adding or removing an Ask AI row rule, and creating, editing or deleting a custom connector preset, leaves nothing in the Audit trail, even though both are security changes.
- **Root cause / where:** `backend/app/routers/agent.py:500` `create_row_policy` and `:544` `delete_row_policy`, and `backend/app/routers/custom_connectors.py:39` create, `:62` update and `:114` delete, never call `services/admin_audit.record`. **Confirmed.**
- **Fix:**
  1. Call `admin_audit.record` before each commit:
     - `connection_rule.create` and `connection_rule.delete`, target `table:{obj.name}`, detail `role:{role.name} {predicate}`.
     - `custom_connector.create`, `custom_connector.update` and `custom_connector.delete`, target `connector:{key}`, detail `base_type` and the names of the locked fields. Never include config values or secrets.
  2. Add readable names for the new actions in `activityActionName` (`frontend/src/i18n/pages/dataPages.ts:692`), in en and ar.
- **Tests:** automated: `backend/tests/test_admin_audit.py` gets `test_connection_rule_create_and_delete_write_audit_rows` and `test_custom_connector_crud_writes_audit_rows`; the second also asserts that no secret value appears in `detail`. Manual: add and remove a connection rule, and both show in /admin/audit.
- **Effort:** S
- **Depends on / related:** E-10, E-11

### E-10 — Validate connection rule columns against the table
- **Severity:** Medium
- **Evidence:** #12 · E-35..38 (E-37-connection-rule-bad-col.png)
- **Problem:** `nonexistent_col = 'x'` was saved. It will fail or deny rows when a user asks a question, without telling anyone.
- **Root cause / where:** `backend/app/routers/agent.py:500` `create_row_policy` only checks that the predicate parses with sqlglot in the source's dialect. It never compares the predicate's column references with the table's columns (`SourceColumn`). **Confirmed.**
- **Fix:**
  1. After parsing, collect `{c.name for c in parsed.find_all(exp.Column)}`, ignoring USERID()/USEREMAIL()-style function tokens.
  2. Load the `SourceColumn` names for `source_object_id` and compare case-insensitively.
  3. Return 422 "Unknown column 'x' in <table>. Columns: …" for any unknown name.
  4. Show the error inline. The page already renders `detail` (`ConnectionRowPolicies.tsx:75-79`).
- **Tests:** automated: a new `backend/tests/test_agent_row_policies.py` (or extend `test_agent_api.py`, which already exercises /row-policies) gets `test_row_policy_unknown_column_is_422` and `test_row_policy_known_column_and_userid_token_ok`. Manual: enter `nonexistent_col = 'x'`; it is rejected with the list of columns.
- **Effort:** S
- **Depends on / related:** E-07, E-09

### E-11 — Type-check custom connector fields (number port, TLS select)
- **Severity:** Medium
- **Evidence:** #14 · E-47..51 (E-50-custom-connector-created.png, E-51-custom-connector-edit.png)
- **Problem:** A preset with Port = "abc" was saved. TLS is a free-text box although only five modes are valid. The bad values only fail later, when a connection uses the preset.
- **Root cause / where:** `backend/app/services/custom_connectors.py:20` `validate_custom_connector_def` checks field names only, not `ConfigField.kind` or `options` (`services/connectors.py:52`; TLS options `TLS_MODES` at `:118`). On the frontend, `AdminCustomConnectors.tsx:94` renders every field as a text `<input>` and ignores `f.kind`, while `pages/connections/ConnectionModal.tsx:282-291` already handles `select` and `number`. **Confirmed.**
- **Fix:**
  1. In `validate_custom_connector_def`, for each base_config value:
     - `kind=="number"` must be an integer (port 1–65535).
     - `kind=="select"` must be one of `options`.
     - Raise `CustomConnectorError` with the field label.
  2. In `AdminCustomConnectors.tsx`, render `<select>` for `select` and `type="number"` for `number`, the same way ConnectionModal does.
  3. Fix the "0 locked field(s)" plural wording (Low).
- **Tests:** automated: `backend/tests/test_custom_connectors.py` `TestValidateCustomConnectorDef` gets `test_non_numeric_port_is_rejected` and `test_unknown_tls_mode_is_rejected`. `AdminCustomConnectors.test.tsx` checks that TLS renders as a select. Manual: Port "abc" is refused.
- **Effort:** S
- **Depends on / related:** E-09

### E-12 — Show a friendly message for a tile whose measure uses a hidden column (QA SEC-02)
- **Severity:** Medium
- **Evidence:** #22 · E-91..103 (E-92-emea-usecase-regional.png), QA plan **SEC-02** (QA/REPORT.md, EVALUATION §2 #21)
- **Problem:** For demo-emea, the "Margin % by region" tile on /reports/8 shows the raw text "Unknown column or function in measure expression: name 'cost' is not defined". Column security looks like a broken dashboard and confirms the hidden column's name.
- **Root cause / where:**
  - Import path in `backend/app/routers/widget_data.py:758-830` (`_resolve_widget_data`): the denied columns are passed as `drop_columns`, and `services/widget_data.py:5702-5709` drops `cost` before measures are evaluated.
  - The measure `(SUM(revenue) - SUM(cost))…` then raises a NameError in `services/measure_eval.py:284-285`, which is caught at `services/widget_data.py:4684` and returned as `{"type":"error","code":"measure_error","message": str(e)}`.
  - `frontend/src/components/report/WidgetBody.tsx:352` shows `data.message` as written.
  - The DirectQuery branch already refuses such a widget cleanly with `forbidden_column` (`widget_data.py:592-599`, using `measure_sql.referenced_names`); the import branch has no such check.
  - The frontend `FetchErrorState` (`WidgetBody.tsx:108`) has no translation for `forbidden_column`.
  - **Confirmed.**
- **Fix:**
  1. Move the DirectQuery measure check (`widget_data.py:592-599`) into a helper `_refuse_denied_measures(req.config, measure_defs, calc_cols, denied)`. Call it on both paths right after `denied` is computed (import path: after line 762). Also cover calc columns whose expression reads a denied column.
  2. Frontend: in `FetchErrorState` map `code === 'forbidden_column'` to a new i18n key, e.g. `widget.err.restricted`: "This tile uses data your role can't see." Add it in en and ar, and give it a lock icon and no retry button.
  3. Also map `data.type==='error' && data.code==='measure_error'` to a generic "This measure could not be calculated" for viewers, and keep the raw message for editors.
- **Tests:** automated: `backend/tests/test_column_security.py` gets `test_import_widget_with_measure_over_denied_column_is_403_forbidden_column` (body code == "forbidden_column", detail does not contain "cost"). Add `frontend/src/components/report/WidgetBody.test.tsx` (new, vitest): fetchError `{code:'forbidden_column'}` renders the restricted message. Manual: as demo-emea, open Use case — Regional; the Margin tile shows the restricted message and the other tiles are unchanged.
- **Effort:** S
- **Depends on / related:** E-13, E-14

### E-13 — Hide measures and calculated columns built on hidden columns from restricted roles
- **Severity:** Medium
- **Evidence:** #21 · E-91..103 (E-96-emea-measures.png)
- **Problem:** demo-emea sees the formula "Margin % = (SUM(revenue) - SUM(cost)) / SUM(revenue) * 100" in Data › Measures, with edit and delete icons. It names the hidden column and shows how it is used.
- **Root cause / where:** `backend/app/routers/datasets.py:1570` `list_measures` returns `ds.measures` unfiltered (it only calls `require_dataset_read`). `_without_denied_columns` (`datasets.py:57`) filters `columns` but not `calculated_columns` or measures. `frontend/src/components/report/MeasuresPanel.tsx:240` always renders the edit and delete buttons. The server enforces `require_dataset_capability(..., "data")` on save and delete (`datasets.py:1577`, `:1677`); whether EMEA would actually pass it is unconfirmed, because authoring "defaults OPEN" (`core/capability.py:414`). **Confirmed for the read leak.**
- **Fix:**
  1. In `list_measures`, and in `_without_denied_columns` for `item.calculated_columns`, drop entries where `measure_sql.referenced_names(expr) & denied` is non-empty, with `denied = resolve_denied_columns(...)`.
  2. Expose the viewer's dataset capability (e.g. `can_model: bool` on DatasetOut, from `max_dataset_capability`). Have `MeasuresPanel` hide edit and delete when it is false.
- **Tests:** automated: `backend/tests/test_measures_api.py` gets `test_list_measures_hides_measures_over_denied_columns` (a role with a ColumnSecurityRule on `cost` does not see Margin %). `backend/tests/test_column_security.py` checks that the dataset GET omits calc columns over denied columns. `frontend/src/components/report/MeasuresPanel.test.tsx` checks that `can_model=false` shows no edit or delete. Manual: as demo-emea, Measures no longer lists Margin %.
- **Effort:** M
- **Depends on / related:** E-12, E-14

### E-14 — Compute dataset row and column counts after row and column security
- **Severity:** Medium
- **Evidence:** #23 · E-91..103 (E-93-emea-sales-dataset.png, E-94, E-95, E-100-emea-ask-ai-sales-picked.png)
- **Problem:** EMEA's Overview says "Columns 13 / Rows 2,000" while the Columns tab shows 12 and the Data tab 514. The Ask AI picker shows "2,000 rows · 13 columns" and the Data tab footer says "filtered from 2,000". This reveals that a column is hidden and how many rows exist in total.
- **Root cause / where:** `backend/app/routers/datasets.py:57` `_without_denied_columns` removes denied entries from `item.columns` but leaves the stored `col_count` and `row_count` (`schemas.py:261-262`) unchanged. It is used by both the list (`:134`) and the detail (`:181`). The frontend reads `ds.col_count` and `ds.row_count` in `pages/datasetDetail/Overview.tsx:92,215-216,247,270`, in `pages/DatasetDetail.tsx:1830-1831` ("filtered from") and in the Ask picker (`pages/ask/DataPicker.tsx:394`). **Confirmed.**
- **Fix:**
  1. In `_without_denied_columns`, set `item.col_count = len(item.columns)` (excluding prep-added columns) when `denied` is non-empty.
  2. When `resolve_rls_expr(...)` is not None:
     - Set a new transient flag `row_count_restricted=True`.
     - Either compute the visible count (one DuckDB `COUNT(*)` with the RLS filter, cached per file mtime and expression) or set `row_count` to the visible count and leave the total out.
  3. In `DatasetDetail.tsx:1830`, hide "filtered from N" when `row_count_restricted`.
- **Tests:** automated: `backend/tests/test_column_security.py` gets `test_dataset_out_col_count_excludes_denied_columns`. `backend/tests/test_get_widget_data_rls.py` (or the existing `test_analysis_rls.py`) gets `test_dataset_out_row_count_is_rls_filtered`. `frontend/src/pages/datasetDetail/Overview.test.tsx` checks that the counts render from the payload. Manual: as demo-emea, Overview shows 12 columns and 514 rows, and the picker matches.
- **Effort:** M
- **Depends on / related:** E-12, E-13

### E-15 — Enforce unique role names per organization
- **Severity:** Medium
- **Evidence:** #7 · E-14..18 (E-16-duplicate-role-name.png)
- **Problem:** "QA E Role" was created twice, which makes role pickers, bulk import ("role by name") and rule lists ambiguous.
- **Root cause / where:** `backend/app/routers/admin.py:37` `create_role` and `:50` `update_role` don't check for duplicates. `models.py:585` `Role` has no `UniqueConstraint("org_id","name")`. `bulk_create_users` (`admin.py:126`) already admits the problem with "first wins on a name clash". **Confirmed.**
- **Fix:**
  1. In create_role and update_role, check case-insensitively for another role in the same org with the same name, and return 409 "A role with this name already exists".
  2. Add Alembic migration `0070_roles_org_name_unique`: a unique index on `(org_id, lower(name))`. Before creating the index, rename existing duplicates with a " (2)" suffix.
  3. Strip whitespace from names, and reject empty names with 422, not only through the frontend toast.
- **Tests:** automated: `backend/tests/test_admin_roles.py` gets `test_duplicate_role_name_is_409` (including a case variant), `test_rename_to_existing_name_is_409` and `test_same_name_in_other_org_is_ok`. Manual: create "QA E Role" twice; the second is refused.
- **Effort:** M
- **Depends on / related:** —

### E-16 — Add search, filters and pagination to the Users list
- **Severity:** Medium
- **Evidence:** #1 · E-01 (E-01-admin-users.png)
- **Problem:** /admin/users is one flat list with no search, role or status filter, and no pagination. It becomes unusable once an org has hundreds of users.
- **Root cause / where:** `frontend/src/pages/admin/AdminUsers.tsx:179-267` renders `users.map` without any filtering. `backend/app/routers/admin.py:89` `list_users` returns every user in the org, unordered, which is why the list re-sorts after a bulk import. **Confirmed.**
- **Fix:**
  1. Backend: add optional `q`, `role_id`, `active`, `limit` (default 50) and `offset` to `list_users`. Order by `User.email`. Return `X-Total-Count`, or wrap the response as `{items,total}` behind a new param so existing callers keep working.
  2. Frontend: add a search box (email contains), a role select, an Active/Inactive/All filter and page controls, and make the Inactive tag a chip.
- **Tests:** automated: `backend/tests/test_admin_users.py` gets `test_list_users_filters_by_q_role_and_active` and `test_list_users_paginates_sorted_by_email`. `frontend/src/pages/admin/AdminUsers.test.tsx` checks that typing in search narrows the rows. Manual: search for "demo"; only the demo users remain.
- **Effort:** M
- **Depends on / related:** —

### E-17 — Make the LLM "Test connection" fail fast with a readable reason
- **Severity:** Medium
- **Evidence:** #17 · E-64..70 (E-66-llm-test-5s.png, E-67-llm-test-result.png)
- **Problem:** Test connection waits about 34 s, then shows "Could not reach the model: ConnectTimeout:" with nothing after the colon.
- **Root cause / where:** `backend/app/routers/platform_settings.py:80` `test_llm` builds `LLMClient(timeout=min(settings.llm_timeout_s, 30.0))`, a single 30 s budget that also covers the connect phase. `backend/app/services/llm.py:396` formats errors as `f"{type(exc).__name__}: {exc}"`, and `httpx.ConnectTimeout` has an empty `str()`, which leaves the trailing colon. The frontend shows it through `settings.testFail` (`frontend/src/i18n/en.ts:4612`). **Confirmed.**
- **Fix:**
  1. In `test_llm`, pass `httpx.Timeout(30.0, connect=5.0)`. Make `LLMClient` accept an `httpx.Timeout`, or add a `connect_timeout` argument.
  2. In `llm.py:396` and `:484`, add `_describe(exc, base)`. It returns `str(exc)` when there is text; otherwise it maps by type, e.g. ConnectTimeout → "no answer from {base} within 5 s (is the model server running?)", ConnectError → "connection refused by {base}".
- **Tests:** automated: `backend/tests/test_app_settings.py` (where test-llm is already covered, lines 173-184) gets `test_test_llm_connect_timeout_has_readable_detail`. Use an `httpx.MockTransport` that raises `httpx.ConnectTimeout("")` and assert that `detail` doesn't end with ":" and names the URL. Manual: with no model running, Test connection fails within about 5 s with a full sentence.
- **Effort:** S
- **Depends on / related:** area D (AI fails fast)

### E-18 — Let admins set and see an org unit's "match value"
- **Severity:** Medium
- **Evidence:** #8 · E-19..23 (E-20-add-unit-dialog.png, E-21-add-unit-step2.png)
- **Problem:** Row security tells admins that "a unit's match value must equal the values in this column", but the Add unit flow never shows or asks for a match value. Admins can't tell what MYSCOPE() will produce.
- **Root cause / where:** `frontend/src/pages/admin/AdminOrgUnits.tsx:76-89` prompts only for name and level, and calls `orgUnitsApi.create({name,parent_id,level_name})`. The tree shows `= match_value` only when it differs from the name (`:157-160`). The backend already accepts it: `admin.py:808` (`match_value` defaults to name) and the PATCH update at `admin.py:820` (match_value branch). **Confirmed (UI gap only).**
- **Fix:**
  1. Add an optional third step or field "Value in your data (defaults to the name)" when adding a unit, and send `match_value`.
  2. Add an "Edit value" action on each node that uses the existing PATCH.
  3. Always show the match value on the node, muted when it equals the name.
  4. In the Row security MYSCOPE hint (`AdminRowSecurityRules.tsx:186-188`), list a few of the current users' scope values as an example.
- **Tests:** automated: `frontend/src/pages/admin/AdminOrgUnits.test.tsx` checks that create sends `match_value` and that editing it calls PATCH. `backend/tests/test_hierarchical_rls.py` checks that a unit with a custom match_value expands to that value. Manual: add unit "Cairo Branch" with value "Cairo", place a user, and the MYSCOPE rule filters to Cairo.
- **Effort:** S
- **Depends on / related:** E-03

Coverage: worklist items 1..24 all mapped. Merged: #2+#10 → E-05; #3+#4+#20 → E-04; #5+#18 → E-02; #13+#15+#16 → E-09. QA SEC-02 is included in E-12. Decision needed: #6 (E-08, the permission matrix is a new feature). E-07 (#11) is partly an environment artifact: the connection had not finished syncing when tested. The fix is the missing empty-state guidance.


## Sharing, publishing, templates & suggestions

### F-01 — Serve map settings to guest/embed viewers and stop 401 → /login redirects on public pages
- **Status:** ✅ Done on 15 Oct 2026 in `16a84654` (see Progress at the top for what changed vs this text).
- **Severity:** Critical
- **Evidence:** #17 · F2-48..55 (F2-55), F2 top issue "F2-55"; F-101 not exercised
- **Problem:** When a logged-out visitor opens a guest link (`/shared/<token>`) to a dashboard with a map, they are sent to the sign-in page, so guest links to any map dashboard do not work. The backend serves the link itself (`GET /api/v1/shared/<token>` → 200). The `/embed` view hits the same problem.
- **Root cause / where:**
  - `frontend/src/components/report/geo/tiles.ts:24-36` `loadTileSettings` (called by `useTileSettings` ← `geo/MapFrame.tsx:95`, i.e. every map renderer) calls `mapSettingsApi.get()` → `frontend/src/services/api.ts:993` `GET /map-settings`. That route needs authentication (`backend/app/routers/map_settings.py:48-54` `get_map_settings`, `Depends(get_current_user)`), so it returns 401. `handleResponseError` (`frontend/src/services/api.ts:98-109`) only skips the redirect for `quiet401`. It calls `onUnauthorized`, which `AuthContext.tsx:30-36` sets to `navigate('/login')`. `AuthProvider` wraps `/shared/:token` and `/embed` too (`App.tsx:84-96`). The `.catch(() => null)` in tiles.ts runs too late, because the interceptor has already navigated. (confirmed)
  - Same bug, second path: a choropleth or point map whose column has a boundary set (`config.boundary_set_id`, or the `geography` map that `shared.py:253` `_published_geography` / `embed.py:139` publishes) loads its shapes through `geo/regionSetCache.ts:20-35` `loadRegionSet` → `boundarySetsApi.get` → `GET /boundary-sets/{id}` (`backend/app/routers/boundary_sets.py:122-127`, authenticated). That also gives a 401 and a redirect, both on guest links and in embed mode. (confirmed by code; not reproduced in the browser)
  - Embed: `pages/EmbeddedReport.tsx:176` renders the same `WidgetRenderer` and map components, so tiles and boundary sets cause the same 401 → `/login`. Inside an iframe, the host page shows our login screen. (confirmed by code)
- **Fix:**
  1. Backend: in `shared.py:375` `shared_report` and `embed.py:250` `embed_report`, add `"map_settings": map_settings._out(row)` for `report.org_id`. Factor out a helper such as `async def org_map_settings(db, org_id)` in `routers/map_settings.py` and reuse it in `get_map_settings`.
  2. Backend: add `GET /shared/{token}/boundary-sets/{set_id}` and `GET /embed/boundary-sets/{set_id}` (embed authenticates with `embed_session_token`, like `embed_widget_data`). Serve a set only if the published payload references it: a widget `config.boundary_set_id`, a geo layer's `boundary_set_id`, or a value in `_published_geography`. Answer 404 for anything else.
  3. Frontend: in `SharedReport.tsx:72` and `EmbeddedReport.tsx:79`, before setting `report`, call `setTileSettings(r.map_settings ?? null)` (already exported from `tiles.ts:39`). This sets `loaded`, so `loadTileSettings` never calls the authenticated API.
  4. Frontend: add `setRegionSetLoader(fn)` to `regionSetCache.ts` (the default stays `boundarySetsApi.get`). SharedReport and EmbeddedReport install a loader that calls the new guest or embed route. Add these to `sharedApi` and `embedApi` in `api.ts:2046-2081`.
  5. Defence in depth: in `handleResponseError` (`api.ts:105`), do not call `onUnauthorized` when `window.location.pathname` starts with `/shared/` or `/embed`. The guest page then shows the widget's own error instead of losing the whole page.
- **Tests:** automated: `frontend/src/test/authInterceptor.test.ts` checks that a 401 while the path is `/shared/x` or `/embed` does not call the handler. `frontend/src/pages/SharedReport.test.tsx` and `EmbeddedReport.test.tsx` render a payload with a `geo_choropleth` widget and `map_settings`, then assert that `mapSettingsApi.get` and `boundarySetsApi.get` are never called and that no navigation to `/login` happens. `backend/tests/test_share_links.py` checks that `GET /shared/{token}` without a cookie includes `map_settings`, that a referenced boundary set returns 200 through the guest route, and that an unreferenced set returns 404. `backend/tests/test_embed.py` covers the same for `/embed/report` and `/embed/boundary-sets/{id}`. Manual: turn guest links on, create a link for "QA F Exec summary" (country map), open it in a private window, and confirm the map draws and no `/login` appears. Repeat in an embed iframe, and with a governorate boundary-set map.
- **Effort:** M
- **Depends on / related:** F-02 (both concern guest and embed surfaces)

### F-02 — Enforce the "may download" right on the server for every export path (print, PPTX, widget CSV/Excel)
- **Severity:** High
- **Evidence:** #12 · F-93..96 (F-95, F-96), F top issue "F-95/96"
- **Problem:** A reader whose share has "May download and export" turned off still gets **Print / Save as PDF** and **Download PowerPoint** through Export → Print. They can also download each chart's data as CSV/Excel from the widget ⋮ menu. "No downloads" therefore does not stop the data leaving the app.
- **Root cause / where:** The right is stored as `ReportUserGrant.can_export` (`backend/app/models/models.py:1062`; the Share dialog sets it at `ShareDashboardDialog.tsx:147` `body.can_export = false`) and `Report.viewers_may_export` (`models.py:248`). `core/capability.py:350` `export_refusal` / `:372` `require_export` read it, and `routers/shared.py:293` `download_gate` calls them. Only `reports.py:1598` `/pdf`, `:1653` `/xlsx` and `:1707` `/package` call `download_gate`. Gaps (confirmed):
  1. Print and PPTX are entirely client-side. `pages/ReportPrint.tsx:34-48` loads with the normal `reportsApi.get` and widget queries, and `:94-102` offers `window.print()` and `exportPrintViewToPptx` (`lib/pptExport.ts`) with no permission check. `ExportDialog.tsx:66-70` even switches to `print` when downloads are blocked ("Print stays"), and the ⋮ menu offers Print unconditionally (`ReportBuilder.tsx:3736`).
  2. Widget CSV/XLSX: `WidgetRenderer.tsx:1062` `handleExport` → `api.ts:3029` `widgetDataApi.export`, whose request body has **no `report_id`**. So `widget_data.py:1041` `export_widget` calls `download_gate(report=None)`, which skips `require_export` entirely. `require_dataset_read` still passes because `readable_dataset_ids` includes datasets reached through visible dashboards (`capability.py:628-646`). `WidgetRenderer` defaults `allowExport = true` (`:258`) and `ReportBuilder` never passes it, so the menu items are shown (`:1551`, `:1944`).
  3. Widget image export / copy image (`WidgetRenderer.tsx:1074` `handleExportImage`, `ReportBuilder.tsx:4229` `copyChartImage`) is also client-side and not gated.
  Guest (`SharedReport.tsx:209`) and embed (`EmbeddedReport.tsx:176`) pass `allowExport={false}`, and `/shared` and `/embed` have no export routes. Those surfaces are fine today but have no regression tests.
- **Fix:**
  1. Backend print gate: in `reports.py:371` `get_report`, when `view == "print"`, call `download_gate(db, current_user, report=report)`. It returns 403 with the refusal and writes the existing `report.export_denied` audit entry. Also write a `report.export` audit entry ("print") on success.
  2. Frontend print: `ReportPrint.tsx` loads with `reportsApi.get(reportId, { view: 'print' })`. On 403 it shows the server's reason with only a "Back" link, so no Print or PowerPoint buttons appear. Because PPTX is built from the print page, it is covered by the same gate.
  3. Backend widget export: send `report_id` from `widgetDataApi.export` (add `reportId` to its signature; `WidgetRenderer.handleExport` passes its `reportId` prop). In `export_widget`, if `req.report_id` is missing and the dataset is not directly readable (`_directly_readable_ids`), return 403 "Export this chart from its dashboard". Otherwise call `download_gate` with the report as now.
  4. Frontend gating, so the UI matches the server: remove the "force print" effect (`ExportDialog.tsx:70`) and grey Print with the same reason. In `ReportBuilder.tsx:3736`, hide ⋮ Print when `access.download?.allowed === false`. Pass `allowExport={access.download?.allowed !== false}` to every `WidgetRenderer` in `ReportBuilder` and to the print page. Hide the copy-image and export-image buttons under the same condition.
  5. Decision needed (one line in the product docs): a reader can always screenshot or use the browser's own Ctrl+P on the live view. The guarantee is "no app-provided download", not "no copy".
- **Tests:** automated: `backend/tests/test_pdf_export.py` checks that a viewer grant with `can_export=False` gets 403 on `GET /reports/{id}?view=print` and 200 on a plain GET; an editor gets 200 with `view=print`. `backend/tests/test_widget_export.py` checks that the same viewer gets 403 on `POST /datasets/{ds}/widget-data/export` with `report_id`, and 403 without `report_id` when the dataset is reachable only through the dashboard; an owner gets 200. `backend/tests/test_share_links.py` and `test_embed.py` assert that no export route exists under `/shared` or `/embed` (404/405). `frontend/src/pages/ReportPrint.test.tsx` checks that a 403 on load shows the reason and no `prt.print`/`prt.pptx` buttons. `frontend/src/components/report/share/ExportDialog.test.tsx` checks that Print is disabled when the decision is blocked. Manual: share with "May download" off, sign in as the reader, and confirm Export → Print, ⋮ → Print, the widget ⋮ CSV/Excel and `/reports/14/print` are all refused with the reason.
- **Effort:** M
- **Depends on / related:** F-01

### F-03 — Make AI dashboard suggestions fail fast and fall back to the statistics engine when the model is unreachable
- **Severity:** High
- **Evidence:** #2, #3 · F-14..19 (F-14, F-15, F-16, F-17, F-18), F top issue "F-14..18"
- **Problem:** When a goal is typed and the AI model is unreachable, "Suggest dashboards" spins for more than 2 minutes with no error and no fallback. After 25 s it says "Still going. Large datasets take longer…", which wrongly blames a 2,000-row dataset. The top bar already shows the model is down ("ConnectTimeout").
- **Root cause / where:** `backend/app/routers/datasets.py:2403` `suggest_dashboards`: with a goal and the default `selection_mode()=="cards"` (`analyst_panel.py:1996`), it calls `sug.panel(inputs, goal, 24)`. That uses `get_client()` (`suggest_inputs.py:276-281`) and then makes sequential model calls in `run_panel`: `person_questions` (`analyst_panel.py:2034`) and `pick_cards` (`:1967`). Each goes through `LLMClient._post` (`services/llm.py:351-401`) with `httpx.AsyncClient(timeout=self.timeout)`, and `settings.llm_timeout_s` is 180 s (`core/config.py:103`). One scalar timeout also caps the TCP connect, so each unreachable call can block for up to 180 s. Nothing checks `llm_endpoints.is_up` (`services/llm_endpoints.py:238`) before calling. The front end allows 300 s (`api.ts:592-597`), and `SuggestDashboardsDialog.tsx:391-394` shows `sdd.slow` (`i18n/en.ts:704`) after 25 s whatever the cause. (confirmed by code)
- **Fix:**
  1. `services/llm.py` `_post`: use `httpx.Timeout(self.timeout, connect=min(5.0, self.timeout))`, so an unreachable host fails in seconds while slow generations still get the full read timeout.
  2. `datasets.py` `suggest_dashboards`: before the model path, call `llm_endpoints.candidates()`. If every candidate `is_up(...) is False`, or `get_client().enabled` is false, run the no-goal statistics branch (`sug.panel(inputs, None, 24, client=None)`) and return `source: "insights"` with `reason: "ai_unreachable"` (plus a `reason_i18n` key).
  3. Also fall back after a failure: if `run_panel` returns no picks and `client.last_error` is set, return the statistics result with `reason: "ai_unreachable"` instead of an empty answer.
  4. `SuggestDashboardsDialog.tsx`: when the answer has `reason === 'ai_unreachable'`, show a banner: "The AI model could not be reached — these charts were picked from your data without AI." Replace `sdd.slow` with neutral wording ("Still working — this can take a minute while every chart is drawn and checked; you can cancel.") and do not mention dataset size.
- **Tests:** automated: `backend/tests/test_suggest_dashboards_endpoint.py`. With a goal and an LLM transport that raises `ConnectTimeout` (or endpoints marked down via `llm_endpoints.mark`), the endpoint returns within a few seconds with `source == "insights"`, `reason == "ai_unreachable"` and non-empty proposals. `backend/tests/test_llm*.py` (existing LLM client test file) checks that the `httpx.Timeout` passed has a short `connect`. `frontend/src/components/dataset/SuggestDashboardsDialog.test.tsx` checks that the banner renders for `reason: 'ai_unreachable'` and that the slow hint no longer contains "Large datasets". Manual: point the default endpoint at an unreachable host, type a goal, click Suggest, and confirm a result with the banner appears in under 15 s.
- **Effort:** M
- **Depends on / related:** F-11

### F-04 — Restore an archived dashboard as a draft (or ask before re-publishing)
- **Severity:** Medium
- **Evidence:** #15 · F2-25..33 (F2-33), F2 top issue "F2-33"
- **Problem:** Restoring an archived dashboard silently brings it back **Published** to the whole organisation, so readers see it again at once. The guide (and the UI's own `onStateChange('draft')`) say it comes back as a draft.
- **Root cause / where:** `backend/app/routers/publishing.py:373-383` `restore` only clears `report.archived_at`. `report.published` stays `True` from before archiving, so `publication_state` (`:294`) returns "published". The front end contradicts this: `components/report/share/PublishingPanel.tsx:77-80` `restore` calls `onStateChange?.('draft')`. (confirmed)
- **Fix:**
  1. In `restore`, also set `report.published = False` (keep `published_at` for history). Leave grants, links and schedules as they are, and mention the change in the audit detail ("restored as draft").
  2. Optional, if product prefers: accept `{"publish": true}` in the body to restore and re-publish in one step. `PublishingPanel.restore` then asks with `confirm` ("Restore as a draft" / "Restore and publish to everyone"). The publish branch must run the same approval gate as `setPublished` (409 when approval is required).
  3. Make `onStateChange` use the `state` the server returns instead of the hard-coded `'draft'`.
- **Tests:** automated: `backend/tests/test_publishing.py` publishes, archives and restores, then asserts `state == "draft"`, that a viewer who had access only through publication gets 404, and that a named grantee still opens it. `frontend/src/components/report/share/PublishingPanel.test.tsx` checks that Restore calls `publishingApi.restore` and that the pill shows Draft. Manual: archive a published dashboard, restore it, and confirm the org reader cannot see it until you publish again.
- **Effort:** S
- **Depends on / related:** F-08

### F-05 — List team-shared dashboards under "My team" even when the reader is also named personally
- **Severity:** Medium
- **Evidence:** #11 · F-88..92 (F-92), F top issue "F-92"
- **Problem:** A dashboard shared with "QA F Team" does not appear under My dashboards → My team for a member of that team. The count shows 0 and "Nothing has been shared with you yet."
- **Root cause / where:** `backend/app/routers/publishing.py:505-537` `_catalogue` gives each row a single `via` taken from `report_grants`. `core/capability.py:56-97` `report_grants` makes a personal grant decide alone (`named` set) and skips team rows for that report, so `via == "user"`. `_in_section` (`publishing.py:543-550`) puts a row in `team` only when `via == "team"`. The reader had both a personal and a team share, so the row went to Shared with me only. (confirmed; a member with only the team share would be listed)
- **Fix:**
  1. In `_catalogue`, compute a separate `via_team: bool`, true when any unexpired `ReportUserGrant` with `org_unit_id in _my_unit_ids(...)` exists for the report. Use one extra query for all ids, or return the set of team-reached report ids from a small helper in `capability.py`.
  2. `_in_section`: `"team": row["via"] == "team" or row.get("via_team")`. Keep `via` unchanged for "how it reached you".
  3. Front end (`pages/Portal.tsx`): make the My team empty state specific ("Nothing has been shared with your team yet").
- **Tests:** automated: `backend/tests/test_publish_and_grants.py` shares a report with a user and with that user's team, then asserts `/portal/catalog?section=team` lists it and `counts.team == 1`. Also cover a parent-unit share reaching a sub-unit member. Manual: repeat F-88..92 and check My team = 1.
- **Effort:** S
- **Depends on / related:** —

### F-06 — Default a new person share to "Can view"
- **Severity:** Medium
- **Evidence:** #10 · F-79..82 (F-79), F2-01..06 (Low repeat), F-97..100 (resets to Can edit)
- **Problem:** The level for a new person defaults to **Can edit**, and resets to it after every removal. Least privilege would be Can view.
- **Root cause / where:** `frontend/src/components/report/share/ShareDashboardDialog.tsx:81` `useState<'view'|'edit'|'data'>('edit')`. Only the role/team tab switches to `'view'` (`:206`). (confirmed)
- **Fix:**
  1. Change the initial state to `'view'`, and reset to `'view'` after a successful invite or a kind change.
  2. Check the backend grant-create default too (`reportGrantsApi.create` → `routers/publishing.py` grant schema). If the body has no level, the server should also default to `view`.
- **Tests:** automated: `frontend/src/components/report/share/ShareDashboardDialog.test.tsx` checks the level select starts at "view" and that the invite body has `level: 'view'`. Manual: open Share, type an email, and check the select reads "Can view".
- **Effort:** S
- **Depends on / related:** —

### F-07 — Make the New-user role select start empty ("Select a role…")
- **Severity:** Medium
- **Evidence:** #1 · F-03..06 (F-05), F top issue "F-05"
- **Problem:** The New user dialog pre-selects the first role, "Admin (admin)". An administrator who does not change it creates another administrator.
- **Root cause / where:** `frontend/src/pages/admin/AdminUsers.tsx:26` `useState(initial?.role.id ?? roles[0]?.id ?? '')`. The empty option already exists (`:81`, `pg.adminSecurity.c.selectRole`) and the `roleRequired` check exists (`:36`). (confirmed)
- **Fix:**
  1. For a new user, initialise to `''` (`initial?.role.id ?? ''`). The existing required check then blocks Save until a role is chosen.
  2. Optional: list non-admin roles first, or mark admin roles in the option label (already done via `roleOptionAdmin`).
- **Tests:** automated: `frontend/src/pages/admin/AdminUsers.test.tsx` checks that a new dialog's role select has value `''` and that Save without a role shows `roleRequired` and does not call `adminUsersApi.create`. Manual: Admin → Users → New user and check the role reads "Select a role…".
- **Effort:** S
- **Depends on / related:** —

### F-08 — Confirm before publishing to (or unpublishing from) the whole organisation
- **Severity:** Medium
- **Evidence:** #13 · F2-01..06 (F2-04), F2-34..39 (unpublish Low), F2 top issue "F2-04"
- **Problem:** One click on the "Everyone in your organisation" radio card publishes the dashboard immediately, with no confirmation. A team share asks first, so this is inconsistent and easy to misclick. Unpublishing works the same way.
- **Root cause / where:** `frontend/src/components/report/share/ShareDashboardDialog.tsx:179-190` `setAccess` calls `reportsApi.setPublished` straight from the radio `onClick` (`:307-314`). Compare with `invite` (`:131-136`), which uses `confirm` for groups. (confirmed)
- **Fix:**
  1. In `setAccess(next)`, call `confirm(...)` first. Publish: "Publish '{name}' to everyone in {org}? Everyone can open it, view only." Unpublish: "Make '{name}' private? People who reach it only because it is published lose access." Add i18n keys in `en.ts`/`ar.ts`.
  2. Leave the radio state unchanged when the dialog is cancelled.
- **Tests:** automated: `frontend/src/components/report/share/ShareDashboardDialog.test.tsx` checks that clicking the workspace radio opens the confirm, that Cancel means `setPublished` is not called, and that Confirm calls it with `true`. The same for Restricted. Manual: click Everyone and check the dialog appears.
- **Effort:** S
- **Depends on / related:** F-04, F-09

### F-09 — Guard the org-wide "Ask for approval before publishing" switch
- **Severity:** Medium
- **Evidence:** #16 · F2-40..47 (F2-41), F-101, F2 top issue "F2-41"
- **Problem:** A plain checkbox inside one dashboard's Share → Publishing tab turns approval on or off for the **whole organisation** in one click, with no confirmation.
- **Root cause / where:** `frontend/src/components/report/share/PublishingPanel.tsx:115-120` checkbox `onChange` → `reviewApi.setApproval` (`api.ts:2358`) → `PUT /review-settings` (`backend/app/routers/review.py:126-145`, org-wide row). There is no confirmation, and the panel is per-dashboard. (confirmed)
- **Fix:**
  1. Short term: wrap the `onChange` in `confirm({ title: t('pub.review.confirmOn'|'confirmOff'), body: 'This applies to every dashboard in the organisation…' })`.
  2. Preferred: move the switch to Platform/Admin settings (next to `ReviewPane`'s publish-gate switch, `components/report/ReviewPane.tsx:280-302`). In the Publishing tab, show a read-only line: "Your organisation asks for approval — change in Admin settings" (link for admins).
- **Tests:** automated: `frontend/src/components/report/share/PublishingPanel.test.tsx` checks that toggling `approval-switch` shows a confirm and that Cancel means `reviewApi.setApproval` is not called. If the switch is moved, an admin-settings test asserts it renders there. Manual: as admin, tick the box and check the confirm names the org-wide effect.
- **Effort:** S
- **Depends on / related:** F-08

### F-10 — Add a "Publish these changes" action to the Publishing tab
- **Severity:** Medium
- **Evidence:** #14 · F2-07..19 (F2-09), F2 top issue "F2-09"
- **Problem:** The Publishing tab says "You have changes readers do not see yet" but has no button to publish them. The only action is the small "Release changes" button in the builder header.
- **Root cause / where:** `frontend/src/components/report/share/PublishingPanel.tsx:105` only renders `t('pub.unreleased')` text. The action exists in `components/report/ReleaseControl.tsx:48-62` `doRelease` → `reportsApi.release` (`api.ts:1533` → `reports.py:697` `release_report`). (confirmed)
- **Fix:**
  1. Next to the `pub.unreleased` line, render a primary button "Publish these changes" when `pub.unreleased_changes && !archived && pub.state === 'published'`. It runs `run(() => reportsApi.release(report.id), t('release.done'))` and shows the `missing` warning the way `ReleaseControl` does. Refactor that into a shared helper `releaseReport(id)`.
  2. Refresh the builder's release status afterwards via a callback prop (`onReleased`), so the header chip updates.
- **Tests:** automated: `frontend/src/components/report/share/PublishingPanel.test.tsx` checks that with `unreleased_changes: true` the button renders and clicking it calls `reportsApi.release`; with false it is absent. Manual: edit a published dashboard, open Share → Publishing → Publish these changes, and confirm the reader sees the edit.
- **Effort:** S
- **Depends on / related:** —

### F-11 — Add a per-user "AI off" choice to the top-bar model picker
- **Severity:** Medium
- **Evidence:** #4 · F-20..23 (F-20), F top issue "F-20"
- **Problem:** The test guide (§5.4) says AI can be turned off from the top-bar picker, but the picker lists only Auto and the configured models. A user whose model is unreachable can only get no-AI suggestions by clearing their goal and "About you". Decision needed: implement the entry, or correct the guide.
- **Root cause / where:** `frontend/src/components/LlmPicker.tsx:170` `pick` and `:251` rows cover only `'auto'` and endpoint ids. `setLlmChoice` (`api.ts:121`) sends the choice as `X-LLM-Endpoint`, read by `main.py:650-671` and `services/llm_endpoints.py:255` `candidates`, which has no "off" value (an unknown id falls through to every enabled endpoint). (confirmed: feature absent)
- **Fix:**
  1. Backend: add `OFF = "off"` in `llm_endpoints.py`. In `services/llm.py:594` `get_client`, return `LLMClient(..., enabled=False)` when the request choice is `off`. Existing callers already treat a disabled client as "no AI" (`deny_ai`/`enabled` paths). In `suggest_dashboards`, treat `off` like the no-goal branch, so the statistics engine runs with a note "AI is off for you".
  2. Frontend: add an "Off — no AI" row to `LlmPicker` (`setLlmChoice('off')`), and show the top-bar chip as "AI off".
  3. If product decides not to build this: update the guide's §5.4 wording instead.
- **Tests:** automated: `frontend/src/components/LlmPicker.test.tsx` checks the Off row exists and that choosing it calls `setLlmChoice('off')`. `backend/tests/test_suggest_dashboards_endpoint.py` checks that a request with header `X-LLM-Endpoint: off` and a goal returns `source == "insights"` without calling the transport. Manual: pick Off, run Suggest with a goal, and check the result is immediate with the no-AI note.
- **Effort:** M
- **Depends on / related:** F-03

### F-12 — Do not show row counts in the measure's currency format, and label the count donut correctly
- **Severity:** Medium
- **Evidence:** #8 · F-62..69 (F-62/63), F top issue "F-63"
- **Problem:** In the "What is in the data" template, the **Rows** KPI shows "$ 2,000", and the donut's centre says "$ 2,000 Total revenue". Both are row counts.
- **Root cause / where:** The template sets the count on the measure (`backend/app/services/dashboard_templates/builtin.py:361` `_w("kpi","Rows",…, measure="$value", aggregation="count")`, `:366` donut `measure="$value", aggregation="count"`). `frontend/src/components/report/WidgetBody.tsx:150` sets `measureFmt = allFormats?.[cfg.measure]` regardless of `cfg.aggregation`, so the revenue `$` format is applied to a count. `chartRenderers/DonutChartRenderer.tsx:37-38` builds the caption as `Total ${cfg.measure}`, ignoring the aggregation. (confirmed)
- **Fix:**
  1. `WidgetBody.tsx:150`: when `cfg.aggregation` (or `aggregation2` for `measure2Fmt`) is `count`/`countd`/`distinct`, use a plain integer format (no prefix, suffix or currency), and keep only grouping. Apply the same rule wherever renderers derive `measureFmt` for KPI, bar and donut.
  2. `DonutChartRenderer.tsx:37`: when the aggregation is a count, caption "Rows" ("Distinct {measure}" for countd); otherwise keep `Total {measure}`.
  3. Template: in `builtin.py:361/366/368`, drop `measure="$value"` for the count widgets, or set `donut_total_label: "Rows"`. Add the Arabic string to `words.py`.
- **Tests:** automated: `frontend/src/components/report/chartRenderers/PieDonutFunnelTreemapFormatting.test.tsx` checks that a donut with `aggregation: 'count'` and a `$` format on the measure shows "2,000" and "Rows". Add a KPI case in an existing `WidgetBody` test (e.g. `components/report/WidgetBody.fit.test.ts` or a new `WidgetBody.format.test.tsx`). `backend/tests/test_dashboard_templates.py` checks the "What is in the data" count widgets carry no money-formatted measure. Manual: create "What is in the data" on Demo — Sales and check Rows = "2,000".
- **Effort:** S
- **Depends on / related:** —

### F-13 — Template mapping: prefer a country-level column for "place" and do not reuse the main split's column
- **Severity:** Medium
- **Evidence:** #7 · F-46..52 (F-47/48), F top issue "F-47/48"; related Low F-53..61 (`topic` in two slots)
- **Problem:** In Executive summary, the mapping dialog suggests `region` as both "The main way to split it" and "The place of each row". The place should be `country`.
- **Root cause / where:** `backend/app/services/dashboard_templates/mapping.py:122-140` `suggest` keys `taken` by `(dataset, slot["kind"])`. A `category` slot and a `geography` slot therefore do not share a used-set, and the same column can fill both. `score` (`:73-74`) gives every geo column 3.0 regardless of `geo_level`, so a tie falls back to column order (`region` before `country`). (confirmed by code; the exact `geo_level` values in Demo — Sales are unconfirmed)
- **Fix:**
  1. In `suggest`, share one used-set across the label-like kinds (`category`, `geography`, `stage`, `flag`) per dataset, and process required slots and `geography` before `category`, so a place column is not taken first as a split.
  2. In `score` for `geography`, rank by level: `country`/`state`/`governorate`/`city` 3.0 > generic `region` 2.5 (`latitude`/`longitude` stay 0).
  3. Apply the same used-set rule to the "What goes together" label slots (Low: `topic` suggested twice).
- **Tests:** automated: `backend/tests/test_dashboard_templates.py` describes columns `region` (geo region, 5 values) and `country` (geo country, 14 values) and checks that `suggest(exec_spec)` gives `place == ["country"]`, `group == ["region"]`, and no column in two slots. Manual: Executive summary → Use template on Demo — Sales, and check place = country.
- **Effort:** S
- **Depends on / related:** —

### F-14 — Stop cutting small-cardinality suggested bar charts at 12 categories
- **Severity:** Medium
- **Evidence:** #6 · F-32..41 (F-33/34), F top-issues row "F-33"
- **Problem:** On the suggested Composition page, "Rows by country" shows "Showing 12 of 14 country values (row limit)" and draws barely visible stubs, with labels crowded at the top and a range slider.
- **Root cause / where:** `backend/app/services/suggest_dataset_dashboard.py:1019-1027` `polish_widget` (used by `analyst_panel.py:2011`) sets `config["limit"] = READABLE_CATEGORIES` (12, `:223`) on any `_CATEGORY_AXIS` widget with more than 12 distinct values. That covers 14 countries, and `TruncationNote.tsx:96` then shows "(row limit)". The cut is confirmed. The stub and slider rendering (bar renderer at this tile size with 12+ bars) is unconfirmed.
- **Fix:**
  1. In `polish_widget`, only cap when `distinct > 20`. For 13–20 categories on a `bar`, set `orientation: "horizontal"` (labels fit) and no limit, so a 14-value column is drawn whole.
  2. Give the suggested tile enough height for the bar count, e.g. `h >= ceil(n/3)+2` in the panel's layout step.
  3. Check the bar renderer at the reported size (thin bars plus slider) and file a separate bug if it reproduces with the full 14 bars.
- **Tests:** automated: `backend/tests/test_suggest_dataset_dashboard.py` checks that `polish_widget` on a bar over a 14-value column sets no `limit` and uses horizontal orientation, and that over 30 values the limit stays 20. Manual: Suggest without AI on Demo — Sales → Composition, and check all 14 countries are readable.
- **Effort:** S
- **Depends on / related:** —

### F-15 — Add "Add all shown" to the builder's Suggestions pane
- **Severity:** Medium
- **Evidence:** #5 · F-28..31 (F-30), F top issue "F-30"
- **Problem:** The builder's Suggestions pane (rail → AI → Suggest) has only a per-card "+ Add", although the guide (§5.5) describes adding them all. The workaround is the Suggest dialog's "Create one dashboard". Decision needed: build it, or align the guide.
- **Root cause / where:** `frontend/src/components/report/SuggestionsPane.tsx:438-442` `add` handles a single view, and the header (`:463-475`) has only "More". `onAdd` → `ReportBuilder.tsx:1452` `addSuggestedWidget` places each widget at `maxY` computed from the `activePage.widgets` snapshot, so calling it in a loop would stack every widget at the same `y`. (confirmed: feature absent)
- **Fix:**
  1. Add an `onAddMany?: (s: Suggestion[]) => void` prop and an "Add all shown ({n})" button that adds the `shown` list (respecting the current chip filter), with a confirm when `n > 8`.
  2. In `ReportBuilder`, implement `addSuggestedWidgets(list)`. It adds the widgets sequentially and carries a running `y` (or uses a bulk `reportsApi.addWidgets` if one exists), runs auto-pack once at the end, and records one undo entry for the batch.
- **Tests:** automated: `frontend/src/components/report/SuggestionsPane.test.tsx` checks the button calls `onAddMany` with the filtered list and that every item then shows as added. A `ReportBuilder` test (`pages/ReportBuilder.test.tsx`) checks that adding 3 suggestions gives 3 widgets with non-overlapping layouts. Manual: Edit → AI → Suggest → Add all, then check the widgets are placed in order and Ctrl+Z removes them all.
- **Effort:** M
- **Depends on / related:** —

### F-16 — Make model-widget display options (Key influencers) findable and stop accidental Duplicate
- **Severity:** Medium
- **Evidence:** #9 · F-70..78 (F-70, F-71, F-72, F-74), F top issue "F-70..74"
- **Problem:** Key influencers options (Drawn as bubbles/bars, Higher/Lower/Both, details) are only under Properties → Data → Fields. The widget ⋮ menu offers only Duplicate and Delete. In testing, a first click on ⋮ landed on Duplicate and copied the widget by accident.
- **Root cause / where:** `frontend/src/components/report/WidgetConfigPanel.tsx:1774-1785` renders `ModelSettings` (`components/report/ModelSettings.tsx`, `ModelOpts` ki fields at `:22-28`) inside the "Fields" `ExpandableGroup`. The edit-mode ⋮ menu `WidgetRenderer.tsx:1567-1580` lists only `duplicate` and `delete`, with Duplicate first. (confirmed; the "opens with Duplicate under the cursor" part is an `ActionMenu` positioning issue, unconfirmed)
- **Fix:**
  1. Also render the display part of `ModelSettings` (ki drawn-as, direction, count, details) in the Format tab, as a "Display" group shown when `isModel`. Keep the specification (event level, depth) in Fields.
  2. Add "Edit options…" as the first ⋮ item. It selects the widget and opens the properties panel on that group (reuse `setRightPanelMode`/`onSelect`).
  3. In `ActionMenu`, open the menu so no item sits under the trigger (offset below the trigger), and do not activate an item on the same pointer-up that opened the menu.
- **Tests:** automated: `frontend/src/components/report/WidgetConfigPanel.test.tsx` checks that a `key_influencers` widget shows the "Drawn as" control in the Format tab. A `WidgetRenderer` menu test (existing `components/report/*WidgetRenderer*.test.tsx`) checks that the ⋮ items start with "Edit options" and that a single click on the trigger does not fire Duplicate. Manual: select the Key influencers widget, open ⋮ → Edit options, and switch to Bars.
- **Effort:** M
- **Depends on / related:** —

Coverage: worklist items 1..17 all mapped (merged: #2+#3 → F-03. Marked "Decision needed" inside the task: #4 → F-11 and #5 → F-15, where the feature is promised by the test guide but absent in the product. F-02 also carries a one-line decision on screenshots/browser print).


## Data, upload, connections & guided setup

### B-01 — Close the fresh-install schema gap (8 columns missing on an init.sql-built database)
- **Status:** ✅ Done on 15 Oct 2026 in `62a54a56` (see Progress at the top for what changed vs this text).
- **Severity:** High (downgraded from Critical: since commit `5ffbb917`, `docker-compose.yml` no longer mounts `postgres/init.sql`, so a normal fresh Docker install is not affected. It still breaks any database first built from `init.sql`, which covers developer volumes created before that commit and anyone following README / `first-stop.md`, which still mention the file.)
- **Evidence:** cross-cutting (EVALUATION.md §2 #1; schema check "fails: 8 columns missing")
- **Problem:** A database whose tables were first created from `postgres/init.sql` is stamped at Alembic head without running revisions, so 8 ORM columns never exist and "Load demo content" (POST /api/v1/demo/seed) returns 500 on a new install.
- **Root cause / where:** `backend/app/main.py:311` `_run_alembic` stamps HEAD when app tables exist without `alembic_version`, trusting `create_all` + `_migrate` (`backend/app/main.py:30`) to reach head-equivalence. `create_all` only adds tables; `_migrate` has no ALTER for `datasets.aggregate_of_dataset_id` / `datasets.aggregate_spec` (rev 0029), `dataset_columns.source_column_id` (rev 0033), `analysis_results.run_id` / `params` / `created_by` (rev 0032), `reports.origin` (rev 0031), `report_pages.background_url` (rev 0026). None are in `postgres/init.sql` either (confirmed by `backend/tests/test_init_sql_schema_coverage.py`). Note: `docker-compose.yml` stopped mounting init.sql in commit 5ffbb917, so today the path is hit by any volume/DB that was initialised from init.sql (older volumes, manual `psql -f init.sql`, other deploy scripts). The fix is still needed because `_run_alembic` will stamp head on such a DB.
- **Fix:**
  1. Append to the `stmts` list in `_migrate` (`backend/app/main.py:32`), matching the ORM in `backend/app/models/models.py` (lines 63-65, 170, 185-187, 233, 284):
     `ALTER TABLE datasets ADD COLUMN IF NOT EXISTS aggregate_of_dataset_id INTEGER REFERENCES datasets(id) ON DELETE CASCADE`,
     `ALTER TABLE datasets ADD COLUMN IF NOT EXISTS aggregate_spec JSON`,
     `ALTER TABLE dataset_columns ADD COLUMN IF NOT EXISTS source_column_id INTEGER REFERENCES source_columns(id) ON DELETE SET NULL`,
     `ALTER TABLE analysis_results ADD COLUMN IF NOT EXISTS run_id INTEGER REFERENCES automation_runs(id) ON DELETE SET NULL`,
     `ALTER TABLE analysis_results ADD COLUMN IF NOT EXISTS params JSON`,
     `ALTER TABLE analysis_results ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(id) ON DELETE SET NULL`,
     `ALTER TABLE reports ADD COLUMN IF NOT EXISTS origin VARCHAR(20) NOT NULL DEFAULT 'user'`,
     `ALTER TABLE report_pages ADD COLUMN IF NOT EXISTS background_url VARCHAR(1000)`.
     These must come AFTER `create_all` (already the case in `lifespan`, main.py:472-475) so `source_columns` and `automation_runs` exist for the FKs.
  2. Add the matching `CREATE INDEX IF NOT EXISTS` lines for the indexed ones (`ix_datasets_aggregate_of_dataset_id`, `ix_dataset_columns_source_column_id`, `ix_analysis_results_run_id`, `ix_reports_origin`) using the names the Alembic revisions use.
  3. Also add the columns to `postgres/init.sql` (and the byte-identical root `init.sql`, or delete that duplicate) so both paths agree.
  4. Remove the `@pytest.mark.xfail(strict=True, ...)` marker from `test_every_orm_column_reachable_from_init_sql_path` in `backend/tests/test_init_sql_schema_coverage.py:94`.
- **Tests:** automated: `backend/tests/test_init_sql_schema_coverage.py` — the now un-xfailed test passes (every ORM column reachable from init.sql + `_migrate`). Manual: fresh Postgres volume, `psql -f postgres/init.sql`, start backend, click "Load demo content" → 200 and demo dashboards open.
- **Effort:** S
- **Depends on / related:** —

### B-02 — Fix the ImportError behind "Warn me on every refresh" (guided setup step 3)
- **Severity:** High
- **Evidence:** #33 · B2-34..45 (B2-1)
- **Problem:** Clicking "Warn me on every refresh" on any finding returns 500 every time; no check is saved.
- **Root cause / where:** `backend/app/routers/guided_setup.py:1577` `fix_item` does `from ..schemas.schemas import DataCheckIn`, but `DataCheckIn` is defined in `backend/app/routers/datasets.py:1934` (confirmed; not in schemas.py). The `how == "check"` branch therefore raises ImportError → 500. The frontend `CheckStep.tsx:71-77` `fix()` does call `failure(e, t('setup.c.fixFailed'))`, so a generic toast should appear; the tester saw nothing (unconfirmed why — possibly the toast was missed).
- **Fix:**
  1. Replace the import with `from .datasets import DataCheckIn, create_data_check` (guided_setup.py:1577-1578).
  2. Keep the call `create_data_check(ds.id, DataCheckIn(kind="rule", params={"expression": rule}, severity="warn"), db, user)`; note `create_data_check` refuses DirectQuery datasets (datasets.py:1991) — catch that HTTPException and return its 400 detail so the UI can say why.
  3. In `CheckStep.tsx` show the failure inline next to the button (not only a toast) so a failed fix is visible.
- **Tests:** automated: `backend/tests/test_guided_setup_health.py` (or a new `test_guided_setup_fix.py`) — POST `/api/v1/setup/{src}/check/{ds}/fix` with `how="check"` on a finding that has `action.rule` returns 200 and a `DataCheck` row with severity `warn` exists. Frontend `frontend/src/pages/setup/CheckStep.test.tsx` — a rejected `setupApi.fix` renders the inline error. Manual: in step 3 click "Warn me on every refresh" → "Check saved", and the dataset's Rules & alerts tab lists it.
- **Effort:** S
- **Depends on / related:** B-33

### B-03 — Stop guided setup swallowing sync errors and show the running read
- **Severity:** High
- **Evidence:** #15, #19, #42 · B-104..108, B-119/120, B2-60/61 (B2-2)
- **Problem:** "Read the database now" swallows every error (403, 500, 409) and just reloads, so the user clicks and nothing happens; step 1 can say "nothing is reading it now" while the review page shows a running sync.
- **Root cause / where:** `frontend/src/pages/setup/UnderstandStep.tsx:93` `readNow` — `try { await metadataApi.sync(sourceId) } catch { /* 409 … */ }` (confirmed). The "nothing is reading it now" copy is a client heuristic at `UnderstandStep.tsx:88` (`neverRead = status==='syncing' && sync.status==='pending' && !last_synced_at`) that does not look at the actual latest SyncRun; the summary endpoint `backend/app/routers/guided_setup.py:542-551` only exposes `source.sync_status`, not the run. Review page Run sync (`frontend/src/pages/SourceReview.tsx:231-244` `runSync`) already toasts on failure (fixed since wave 1; only code-verified). Environment note (Decision needed for that part only): the wave-1 409/500/"0/6 forever" were caused by the DuckDB metadata cache `/app/uploads/metadata_cache.duckdb` (`backend/app/core/config.py:173` `duckdb_cache_path`) being locked by a concurrent pytest run — not a product bug; see B-13.
- **Fix:**
  1. In `readNow`, catch the error: on 409 call `metadataApi.latestSync(sourceId)` and show "A read is already running (started hh:mm) — step x of n" with a link to `/connections/{id}/review`; on any other status show `toast.error(detail ?? t('setup.u.readFailed'))` and an inline error line; never just reload.
  2. Add `latest_run: {id, status, started_at, stages_done, stages_total, error}` to the `_summary` payload (`guided_setup.py:533`), read from `SyncRun` like `metadata.latest_sync` (`backend/app/routers/metadata.py:128`).
  3. Replace the `neverRead` heuristic with `latest_run == null`; when `latest_run.status === 'running'` show progress; when `failed` show its `error` and a "Read again" button.
- **Tests:** automated: `frontend/src/pages/setup/UnderstandStepStuck.test.tsx` — (a) `metadataApi.sync` rejecting with 500 shows an error message, (b) rejecting with 409 shows the running-read text and the review link, (c) summary with `latest_run.status='running'` never shows "nothing is reading it now". `frontend/src/pages/SourceReview.test.tsx` — 500 from sync shows `sr.syncStartFailed` toast (regression guard). `backend/tests/test_guided_setup_understand.py` — summary includes `latest_run`. Manual: start a sync from the review page, open `/setup/{id}`, click Read → message names the running read.
- **Effort:** M
- **Depends on / related:** B-04, B-13

### B-04 — Give a stuck metadata sync a timeout and a Cancel
- **Severity:** High
- **Evidence:** #16, #29 · B-104..108, B2-19..21
- **Problem:** A sync that stalls (0/6 in wave 1, 4/6 waiting on the unreachable LLM in wave 2) shows "Last run: running" with no timeout, no skip and no cancel while the server stays up; only a restart reaps it.
- **Root cause / where:** `backend/app/routers/metadata.py:115-123` starts the run with a bare `asyncio.create_task(...)` and keeps no handle, so nothing can cancel it. `backend/app/services/metadata/sync.py:783` `STALE_RUN_MINUTES = 60` only lets `find_active_run` ignore old runs; the row still says running. `reap_stuck_sync_runs` (`backend/app/services/refresh_scheduler.py:134`) only runs at startup. The LLM stages (`stage_describe` `backend/app/services/metadata/catalog_sync.py:599`, `stage_entities` :806) await model calls bounded only by `llm_timeout_s=180` per call (config.py:103), many calls in sequence (confirmed).
- **Fix:**
  1. Keep a module-level `dict[run_id, asyncio.Task]` in `sync.py` filled by the trigger route; add `POST /data-sources/{id}/sync/{run_id}/cancel` (admin) that cancels the task, marks the run `failed` with error "Cancelled by <user>" and resets `source.sync_status`.
  2. In `run_sync_background` wrap the whole run in `asyncio.wait_for(..., settings.metadata_sync_timeout_s)` (new setting, default e.g. 30 min) and record "Timed out after N min" on timeout; additionally give each LLM stage its own budget (`asyncio.wait_for` in `_run_stage` for `describe`/`entities`) and record `skipped` with reason when exceeded.
  3. Frontend `SourceReview.tsx`: while `run.status==='running'`, show "Running for mm:ss — current step: <name>" and a Cancel button calling the new endpoint; same button in guided setup step 1 (B-03).
  4. Replace the hard-coded `total: 6` in `SourceReview.tsx:328` with the real number of stages (catalog sync has 8).
- **Tests:** automated: `backend/tests/test_metadata_api.py` — cancel endpoint marks a running run failed and a new sync is then accepted (not 409); `backend/tests/test_catalog_sync.py` — a stage that exceeds its budget is recorded `skipped` and the run finishes. `frontend/src/pages/SourceReview.test.tsx` — Cancel button appears for a running run and calls the API. Manual: point the LLM at an unreachable host, run sync, press Cancel → status "failed — Cancelled", Run sync works again.
- **Effort:** L
- **Depends on / related:** B-03, B-11

### B-05 — Save the derived fields the plain dashboard design uses (6/17 widgets broken)
- **Severity:** High
- **Evidence:** #38 · B2-46..53 (B2-3)
- **Problem:** The dashboard created in guided setup step 4 opens with 6 of 17 widgets showing "'late_pct_vs_promised' is not a column or measure on this dataset" (also `delivery_attempts_pct_of_delivery_fee_egp`, `days_created_to_delivered`, `days_created_to_updated`, `days_late_vs_promised`).
- **Root cause / where:** With no reachable model, `write_designs` (`backend/app/routers/guided_setup.py:1705`) gets no proposals from `answer.design` and falls back to `_plain_design` (`guided_setup.py:1687-1702`), which calls `suggest_dashboards(goal=None)` → `sug.panel(...)` (`backend/app/services/suggest_inputs.py:251,293`) — that response carries `"derived"` (measures + calculated columns from `backend/app/services/derived_fields.py` `rate_measures`/`durations`, names built at lines 91, 144, 178-179), but `_plain_design` returns only the proposals and drops `derived`, so `derived` stays `{}` in the stored design item (guided_setup.py:1788-1789). `buildPages` (`frontend/src/lib/buildDashboard.ts:191`) then creates nothing and `withoutFields` only removes widgets whose field creation FAILED, not ones never listed. Confirmed by reading; not reproduced.
- **Fix:**
  1. Make `_plain_design` return `(proposals, derived)` using `got.get("derived")`, and assign it in `one_dataset` when the fallback is used.
  2. In `answer.derived_for` (`backend/app/services/guided_setup/answer.py:1912`) also include measures (it hard-codes `"measures": []`) when a page uses a derived measure.
  3. Defensive check in `buildPages`: before `fillPage`, drop (or flag) any widget whose config names a field that is neither a dataset column, a dataset measure/calculated column, nor in `derived` — so a missing definition can never ship a broken widget.
- **Tests:** automated: `backend/tests/test_guided_setup_dashboard.py` — with the client disabled, `write_designs` stores items whose `derived` lists every derived name used by the proposal widgets; `frontend/src/lib/buildDashboard.test.ts` — `buildPages` with a widget referencing an unknown field leaves it out. Manual: guided setup on the Nile shipments data with no LLM → created dashboard has no "is not a column or measure" widgets.
- **Effort:** M
- **Depends on / related:** B-36

### B-06 — Show the sheet picker for multi-sheet XLSX uploads
- **Severity:** High
- **Evidence:** #13 · B-80..82
- **Problem:** Importing a 2-sheet workbook fails with a generic error card; "Try again" repeats the failure and no sheet picker ever appears, so neither sheet can be imported.
- **Root cause / where:** Backend `_pick_sheet` (`backend/app/routers/datasets.py:288-318`) correctly raises 400 with `detail={"message", "sheets": [...]}`. But the axios interceptor `handleResponseError` → `sanitizeErrorDetail` (`frontend/src/lib/friendlyError.ts:58-67`) turns every object `detail` into a string and moves the object to `detail_raw`, so `Upload.tsx:166` `Array.isArray(detail?.sheets)` is always false and the code goes to the failure branch (confirmed). `frontend/src/pages/Upload.test.tsx:206-219` passes only because it mocks below the interceptor.
- **Fix:**
  1. In `Upload.tsx` `submit` (line 160-170) read the structured detail with `structuredDetail(e)` (friendlyError.ts:84) for both `items` and `sheets`.
  2. When `sheets` is returned, keep the stage on review (already coded) and move the sheet `<select>` (Upload.tsx:281-291) to the top of the review card with the message, not under Technical details.
  3. Optional: list sheets before import (POST a small "inspect" call or read the workbook client-side) so the picker shows on add.
- **Tests:** automated: `frontend/src/pages/Upload.test.tsx` — reject with `{response:{data:{detail: 'The workbook has 2 sheets…', detail_raw:{message, sheets:['Sales','Costs']}}}}` (the shape after the real interceptor) → the sheet select appears; better, run the rejection through `handleResponseError`. Manual: upload `B_data/two_sheets.xlsx` → picker with Sales / Costs / All sheets; each choice imports.
- **Effort:** S
- **Depends on / related:** B-22

### B-07 — Reload the data grid when the last filter is removed
- **Severity:** High
- **Evidence:** #2 · B-12..15
- **Problem:** Removing a filter with the × inside the Filters panel leaves the grid filtered ("of 514 (filtered from 2,000)") although the panel says "No filters".
- **Root cause / where:** `frontend/src/pages/DatasetDetail.tsx:1553` the panel's × calls only `removeFilter(f.id)` (line 444, state-only); it does not call `loadPreview`. Once the list is empty the "Apply" button is hidden (`filterRows.length > 0`, line 1567), so nothing can re-query. The chip × in the toolbar (line 1490-1496) does reload (confirmed).
- **Fix:**
  1. Make `removeFilter` compute the remaining rows and, if the removed row was active (`column && value !== ''`), call `setPage(0); loadPreview(0, rest, calcCols, sortBy, sortDir, search)`; use it from both the panel × and the chip ×.
  2. Keep a "Clear all filters" action visible whenever the preview is filtered.
- **Tests:** automated: `frontend/src/pages/DatasetDetail.test.tsx` — apply a filter, remove it via the panel ×, assert `dataPreviewApi.query` was called again with `[]` filters. Manual: Data tab, filter region = Europe, remove in panel → 2,000 rows.
- **Effort:** S
- **Depends on / related:** —

### B-08 — Default Edit cells to a unique row key and say how many rows an edit changes
- **Severity:** High
- **Evidence:** #3 · B-16/17
- **Problem:** Edit cells identifies rows by the first column (`date` on Demo — Sales, 633 distinct values over 2,000 rows), so one edit silently rewrites every row with that date.
- **Root cause / where:** `frontend/src/pages/DatasetDetail.tsx:1705` `if (!keyColumn) setKeyColumn(preview.columns[0])` and the select default at line 1716; `saveCellEdit` (line 355-382) writes an `edit_cells` prep step keyed on that value (`backend/app/services/prep.py:380,898`) with no uniqueness check (confirmed).
- **Fix:**
  1. Choose the default key as the first column whose distinct count equals the row count (from the analysis profile `n_unique`, or a `widgetDataApi` countd query); if none is unique, default to no key and require the user to choose.
  2. In the key select, mark non-unique columns "(not unique — edits change several rows)".
  3. Before saving, count rows matching the key value (from the loaded page or a count query) and, if > 1, confirm "This changes N rows with date = …".
  4. Backend guard in prep validation: reject an `edit_cells` step whose key is not unique unless the step carries `allow_many: true`.
- **Tests:** automated: `frontend/src/pages/DatasetDetail.test.tsx` — with a profile where `id` is unique, the key select defaults to `id`; editing with a non-unique key opens the confirm with the row count. `backend/tests/test_prep*.py` (e.g. a new `test_prep_edit_cells.py`) — non-unique key without `allow_many` is refused 400. Manual: Demo — Sales → Edit cells → key is not `date`; picking `date` and editing asks for confirmation.
- **Effort:** M
- **Depends on / related:** —

### B-09 — Explain why a dataflow cannot be built on a governed dataset
- **Severity:** High
- **Evidence:** #21 · B-121..127
- **Problem:** Creating a dataflow from Demo — Sales returns 403 and the form just stays; the user does not learn why.
- **Root cause / where:** The 403 is not the capability check the tester guessed (an org admin gets 'data' in `backend/app/core/capability.py:396`); it is `_refuse_if_ungovernable` (`backend/app/routers/datasets.py:3808-3838`, called from `create_dataflow` `backend/app/routers/dataflows.py:207`), because the demo seeds a row rule and a column rule on Sales (`backend/app/services/demo_use_cases.py:609-631`) — confirmed. The frontend `Dataflows.tsx:99-101` does `toast.error(detail(e, …))`, so a toast should show; why the tester saw nothing is unconfirmed (toast may be missed at bottom-right).
- **Fix:**
  1. Show the refusal inline under the New dataflow form (`frontend/src/pages/Dataflows.tsx:120-143`) as well as the toast.
  2. Add `has_security_rules` to the dataset list payload (the per-dataset value already exists, see `api.ts:2541`) and in the Source dataset select disable governed datasets with the suffix "has row/column rules — cannot feed a dataflow".
  3. Reword the backend message for dataflows ("A dataflow cannot read a dataset with row- or column-security rules …") via `refused(...)` so it is translated.
- **Tests:** automated: `frontend/src/pages/Dataflows.test.tsx` — `dataflowsApi.create` rejecting 403 with a detail renders that text inline; governed datasets are disabled in the select. `backend/tests/test_dataflow_permissions.py` — creating from a dataset with a RowSecurityRule returns 403 with the dataflow wording. Manual: as admin pick Demo — Sales → option disabled with the reason.
- **Effort:** M
- **Depends on / related:** B-27

### B-10 — Make "Suggest dashboards" with a blank goal truly model-free
- **Severity:** High
- **Evidence:** #23 · B-143..149
- **Problem:** With the goal left blank (copy: "no AI involved"), a 5-row dataset still showed "Reading the data…" after 102 s while the backend tried to reach the LLM.
- **Root cause / where:** `SuggestDashboardsRequest.use_profile` defaults to `True` (`backend/app/schemas/schemas.py:62`); `suggest_dashboards` (`backend/app/routers/datasets.py:2455-2457`) then calls `ai_context.for_dataset`, and `compose` (`backend/app/services/ai_context.py:47-61`) substitutes the user's "about" text for the empty goal when `llm_enabled`, so `goal` is non-empty and the model path runs. Independently, `suggest_inputs.prepare` → `column_classes.ensure` (`backend/app/services/column_classes.py:479-503`) asks the model to classify columns (`classify_columns_with_model=True`) and waits for the connect timeout. Partly confirmed (code); the dialog (`frontend/src/components/dataset/SuggestDashboardsDialog.tsx:222`) does not send `use_profile`.
- **Fix:**
  1. Dialog: send `use_profile: false` when the goal box is blank (and say "your profile text is not used").
  2. Backend: in `suggest_dashboards`, treat `req.goal` blank as the statistics engine regardless of `use_profile` unless the user explicitly ticked "use my profile".
  3. In `column_classes.hints_for`, skip the model when the endpoint is known down (`llm_endpoints.is_up(...) is False`), see B-11.
- **Tests:** automated: `backend/tests/test_suggest_dashboards_endpoint.py` — blank goal with a user `about` set and a fake client that records calls → zero model calls and `source == "insights"`. `frontend/src/components/dataset/SuggestDashboardsDialog.test.tsx` — blank goal sends `use_profile: false`. Manual: LLM unreachable, Suggest dashboards with blank goal on a 5-row dataset → proposals in a few seconds.
- **Effort:** S
- **Depends on / related:** B-11

### B-11 — Fail fast and say so when the AI model is unreachable
- **Severity:** Medium
- **Evidence:** #27, #30, #32, #41 · B2-15..18, B2-22..26, B2-27..33, B2-54..59 (B2-4)
- **Problem:** With no model, step 1 spinners never stop, "Suggest datasets" runs 1:40+, checking one dataset takes ~7 min, and the sync's describe/entities stages take 9 min and are reported "ok" while producing nothing — although the header already says "AI model: not reachable".
- **Root cause / where:** `LLMClient._post` (`backend/app/services/llm.py:351-409`) always tries every target with the full `llm_timeout_s=180` (`backend/app/core/config.py:103`) even when `llm_endpoints.is_up(eid)` is already False from the prober (`backend/app/services/llm_endpoints.py:238`, `run_prober` :430). Callers (`stage_describe` `catalog_sync.py:649`, `stage_entities` :823, `health.model_rules`/`plain_insights` via `_check_one` `guided_setup.py:1393,1437`, the datasets-step proposals and understand words) cannot tell "no answer" from "answered nothing", so stages return `{"llm_used": True, "drafted": 0}` and `_run_stage` records `ok`. Confirmed from code.
- **Fix:**
  1. Add a fast path in `LLMClient._post`: skip targets whose `is_up()` is False and whose last check is < PROBE_SECONDS old; if all are skipped set `last_error = "model unreachable"` and return None immediately. Use a short connect timeout (`httpx.Timeout(llm_timeout_s, connect=5)`).
  2. Expose `client.available()`; in `stage_describe`/`stage_entities` return `_skip(context, name, "AI unavailable")` when unavailable or when every call failed, so the run log shows "skipped — AI unavailable".
  3. Guided setup: in the summary/datasets/check/design endpoints include `ai: {available: false, reason}`; the frontend (`UnderstandStep.tsx`, `ChooseDataStep.tsx:179`, `CheckStep.tsx:172`, `DashboardStep.tsx:178`) replaces the spinner with "AI is not available — <the working path>" (pick an existing dataset / build it yourself).
- **Tests:** automated: `backend/tests/test_llm_client.py` — with the endpoint marked down, `complete_json` returns None without opening a connection (transport records no request); `backend/tests/test_catalog_sync.py` — describe/entities recorded `skipped` with reason when the client is unavailable; `frontend/src/pages/setup/ChooseDataStep.test.tsx` — `ai.available=false` shows the message and no spinner. Manual: stop the LLM, run guided setup → each AI step says unavailable within seconds; sync log shows "skipped".
- **Effort:** L
- **Depends on / related:** B-04, B-10, B-12

### B-12 — Return the plain data checks first, add AI items later
- **Severity:** Medium
- **Evidence:** #31 · B2-27..33 (B2-5)
- **Problem:** Step 3 says "The facts below are complete" with nothing below; the deterministic findings (duplicates, spaces, -1, negative fees) only appear after the slow AI calls finish.
- **Root cause / where:** `_check_one` (`backend/app/routers/guided_setup.py:1358-1441`) computes `column_items` + `generic_rules`, then awaits `health.model_rules` (line 1393) and later `health.plain_insights` (line 1437) before returning; `write_findings` (line 1444) writes nothing until all of it is done (confirmed). The copy key is `setup.u.aiSlow` (`frontend/src/i18n/en.ts:4748`).
- **Fix:**
  1. Split `_check_one` into a deterministic phase (quality report, column/generic items, automatic cleaning) and an AI phase (model_rules, insights). In `write_findings`, commit the deterministic result with `ai_pending: true` first, then run the AI phase and merge.
  2. `_finding_out` returns `ai_pending`; `CheckStep.tsx` renders findings while showing "AI ideas are still coming" only for the AI part.
  3. Only show the "facts below are complete" sentence when findings exist; otherwise "Still checking…".
- **Tests:** automated: `backend/tests/test_guided_setup_health.py` (or `test_guided_setup_cleaning.py`) — with a model client that blocks, GET check returns the deterministic items while `ai_pending` is true. `frontend/src/pages/setup/CheckStep.test.tsx` — findings render with `ai_pending`. Manual: no LLM → findings appear within seconds of entering step 3.
- **Effort:** M
- **Depends on / related:** B-11

### B-13 — Give the test suite its own DuckDB metadata cache path
- **Severity:** Medium
- **Evidence:** cross-cutting (NOTES.md B-104..108/B-119/120 environment cause; EVALUATION.md environment notes)
- **Problem:** pytest and a live backend on the same machine both open `/app/uploads/metadata_cache.duckdb`; the lock made live syncs 500/409/hang during the evaluation (wave 1 blockers).
- **Root cause / where:** `backend/app/core/config.py:173` `duckdb_cache_path` default; `backend/app/services/metadata/cache.py:392-427` `get_cache`/`get_object_cache` open it lazily once per process; `backend/tests/conftest.py` never overrides it (confirmed). This is an environment/test-isolation issue, not a product bug.
- **Fix:**
  1. In `backend/tests/conftest.py` add a session-scoped autouse fixture that sets `settings.duckdb_cache_path` to `tmp_path_factory.mktemp("duckdb") / "metadata_cache.duckdb"` before any test, and resets `cache._default` / `cache._object_cache` (closing them) at session end.
  2. Optionally make the backend fail with a clear message ("metadata cache is locked by another process") instead of a 500 when DuckDB raises a lock error in `SampleCache.__init__`.
- **Tests:** automated: `backend/tests/test_conftest_smoke.py` — asserts `settings.duckdb_cache_path` is under the pytest temp dir and differs from the config default. Manual: run pytest while the dev backend runs a sync → sync completes.
- **Effort:** S
- **Depends on / related:** B-03

### B-14 — Update the stale widget-type count in the backend parity test (CI red)
- **Severity:** Medium
- **Evidence:** cross-cutting (EVALUATION.md "The one failing backend test")
- **Problem:** `tests/test_widget_roles.py::TestParityWithTheFrontend::test_the_spec_file_was_actually_read` fails: it expects 75 chart types, the frontend `ROLE_SPECS` now has 77.
- **Root cause / where:** `backend/tests/test_widget_roles.py:60` hard-codes `== 75`; `frontend/src/types/report.ts` `ROLE_SPECS` parses to 77 entries and all 77 exist in `backend/app/services/widget_roles.py` `REQUIRED_ROLES` (checked: none missing). Confirmed.
- **Fix:**
  1. Replace the exact count with a floor that still catches a broken parser: `assert len(frontend_required()) >= 70`, and fix the docstring ("65 types").
  2. Or keep the exact count at 77 and add a comment pointing to report.ts; the floor is preferred so adding a chart type does not turn CI red.
- **Tests:** automated: the test itself passes; `test_every_widget_type_is_covered` keeps guarding real parity. Manual: `pytest backend/tests/test_widget_roles.py`.
- **Effort:** S
- **Depends on / related:** —

### B-15 — Stop the 404 on every dataset page load (GET /datasets/{id}/analysis)
- **Severity:** Medium
- **Evidence:** #1, #10 · B-06..09, B-55..60, B-110..114
- **Problem:** Every dataset detail load logs 2-4 × 404 for `/api/v1/datasets/{id}/analysis` in the console.
- **Root cause / where:** `backend/app/routers/analysis.py:208-241` `get_analysis` raises 404 when no profile has been run (and for restricted callers); `frontend/src/pages/DatasetDetail.tsx:288` calls it on every load and relies on the catch; StrictMode doubles it (confirmed). `ReportBuilder.tsx:796` does the same.
- **Fix:**
  1. Return `204 No Content` (or 200 `null`) from `get_analysis` when no result exists; keep 404 only for a missing dataset.
  2. `analysisApi.get` (`frontend/src/services/api.ts:1255`) maps 204 to `null`; update `DatasetDetail.tsx` to branch on null (auto-run after import stays as is) and `ReportBuilder.tsx:796`.
  3. For restricted callers keep the current behaviour but return 204 with a header/flag "run POST for your view" instead of 404.
- **Tests:** automated: `backend/tests/test_analysis_run_endpoint.py` — GET on a dataset with no analysis returns 204; on an unknown dataset 404. `frontend/src/pages/DatasetDetail.test.tsx` — null analysis renders the "Profile the columns" state without error. Manual: open `/datasets/2` with devtools → no 404.
- **Effort:** S
- **Depends on / related:** —

### B-16 — Let the "Add step" menu close on Esc and outside click
- **Severity:** Medium
- **Evidence:** #4 · B-25..29
- **Problem:** The pipeline "+ Add step" menu can only be closed by choosing an item.
- **Root cause / where:** `frontend/src/components/report/PrepPipelinePanel.tsx:288-306` renders a plain absolutely-positioned div toggled by `addMenuOpen` with no keydown or outside-pointer handler and non-focusable `<div onClick>` items (confirmed).
- **Fix:**
  1. Replace it with the shared `ActionMenu` component (`frontend/src/components/ActionMenu.tsx`, already used elsewhere with Esc/outside-click/focus handling), or add a `useEffect` that listens for `keydown Escape` and `pointerdown` outside a ref while open.
  2. Make items `<button role="menuitem">` so they are keyboard reachable.
- **Tests:** automated: `frontend/src/components/report/PrepPipelinePanel.test.tsx` — open menu, press Escape → menu gone; open, click outside → gone. Manual: Data → Steps → + Add step → Esc closes.
- **Effort:** S
- **Depends on / related:** —

### B-17 — Draw the chart for insight cards about calculated columns (empty OUTLIER IMPACT tile)
- **Severity:** Medium
- **Evidence:** #5 · B-30/31
- **Problem:** The second OUTLIER IMPACT card ("85 outlying rows move the average profit") has an empty body, leaving a large blank tile.
- **Root cause / where:** `frontend/src/components/insights/FindingChart.tsx:34-58` picks the chart from `columnTypes`, built in `DatasetDetail.tsx:1325-1326` from `ds.columns` only; `profit` is a calculated column (`backend/app/services/demo_content.py:1164-1172`), so it has no type and `config` stays null → the component renders nothing; even with a type, `widgetDataApi.query(datasetId, config, [], …)` passes no calculated columns. Likely cause, unconfirmed live.
- **Fix:**
  1. Pass `calculatedColumns={calcCols}` into `FindingChart`; add their `dtype` to `columnTypes` and pass them as the third argument of `widgetDataApi.query`.
  2. When no chart can be drawn, let the card collapse to its text (no reserved chart height), so no blank tile appears.
- **Tests:** automated: `frontend/src/components/insights/FindingChart.test.tsx` — a finding on a calculated numeric column issues a histogram query including that calculated column. Manual: Demo — Sales → Analysis → Insights → profit card shows a histogram.
- **Effort:** S
- **Depends on / related:** —

### B-18 — Keep the preselected dataset on Ask when the AI is offline
- **Severity:** Medium
- **Evidence:** #6 · B-39..44
- **Problem:** On `/ask?dataset=1` with the model offline, typing in the disabled box and pressing Enter reset the page to "Step 1 Choose your data" and dropped the dataset; Ctrl+A selected the whole page.
- **Root cause / where:** Unconfirmed. The composer is rendered `disabled` when locked (`frontend/src/components/chat/Composer.tsx:48`, locked from `ChatPane.tsx:673`), so focus/keys go to the page; the scope lives only in the URL and is cleared by `choose('')` → `setParams({})` (`frontend/src/pages/AskAI.tsx:184`). The most likely path is Enter activating a focused control that clears the scope (the compact `DataPicker` at `AskAI.tsx:345` or a "change data" button). Needs a reproduction in the browser.
- **Fix:**
  1. Reproduce and identify the control that receives Enter; make clearing the scope an explicit action only (no `choose('')` from keyboard Enter on an empty search).
  2. Render the locked composer as `readOnly` + `aria-disabled` instead of `disabled`, so it keeps focus and Ctrl+A/Enter stay inside it; Enter while locked shows the offline hint.
- **Tests:** automated: `frontend/src/pages/AskAI.test.tsx` — with `?dataset=1` and AI offline, focusing the composer and pressing Enter keeps `dataset=1` in the URL. Manual: same steps as B-44 → dataset stays selected.
- **Effort:** M
- **Depends on / related:** —

### B-19 — Make the DirectQuery Data tab stable and honest (paged ORDER BY, disabled tools)
- **Severity:** Medium
- **Evidence:** #7, #8 · B-45..54
- **Problem:** On a live dataset, rows reshuffle between Next/Prev (first row 1615 then 9687), and Filter / Row filter / ƒx Column / Group & bin / Search / sort arrows open editors that do nothing.
- **Root cause / where:** `data_preview` DQ branch (`backend/app/routers/datasets.py:4441-4465`) calls `run_direct_query(..., {}, widget_type="table")` with no `page`, so `run_direct_query` skips `_run_table_page` (`backend/app/services/direct_query.py:1266`, stable ORDER BY + exact total) and uses the row-capped fetch; 12,000 rows > `DEFAULT_ROW_CAP=10_000` (direct_query.py:704) means `sampled=True` → `ORDER BY RANDOM()` (direct_query.py:768-769) — confirmed. It also ignores offset (frontend slices, `DatasetDetail.tsx:327-334`). The toolbar buttons are only hidden for Steps/Edit cells (`DatasetDetail.tsx:1500-1528`).
- **Fix:**
  1. In the DQ branch pass `{"page": {"offset": req.offset, "size": req.limit}}` (and `sort_by`/`filters` when supported) so `_run_table_page` serves a stable, exact page; drop the frontend slice and send the real offset.
  2. Disable (with a tooltip "Not available for live data yet") Filter, Row filter, ƒx Column, Group & bin, Search and header sort for `ds.mode === 'directquery'`, or push filter/sort down via the same paged query (simple ops are already supported by `_build_where`).
- **Tests:** automated: `backend/tests/test_data_preview_directquery_router.py` — two calls with offset 0 and 100 on a >10k-row SQLite table return disjoint, repeatable rows and `total` = real count. `frontend/src/pages/DatasetDetail.test.tsx` — DQ dataset renders the tools disabled. Manual: Demo — Live Orders → Next → Prev → same first row.
- **Effort:** M
- **Depends on / related:** B-20

### B-20 — Explain why data checks are not offered for live datasets
- **Severity:** Medium
- **Evidence:** #9 · B-45..54
- **Problem:** Rules & alerts on a DirectQuery dataset shows only Alerts and Freshness; the new data checks are missing with no explanation.
- **Root cause / where:** Intentional: `create_data_check` refuses DQ ("never refreshed into a file, so there is no new data to check before it is published", `backend/app/routers/datasets.py:1991-1993`) and `DatasetDetail.tsx:1388` hides `ChecksPanel` for DQ — but says nothing (confirmed). Decision needed on whether live checks (scheduled SQL checks) are in scope; the explanation is needed either way.
- **Fix:**
  1. In place of `ChecksPanel` for DQ datasets render a short card: "Data checks run when a dataset is refreshed. A live dataset is queried directly, so use an Alert to be told when a value crosses a limit." with a link to the Alerts panel.
  2. (Decision) If live checks are wanted, schedule the existing check kinds as SQL against the source; out of scope for this fix.
- **Tests:** automated: `frontend/src/pages/DatasetDetail.test.tsx` — DQ dataset Rules tab shows the explanation text. Manual: `/datasets/6` → Rules & alerts shows the note.
- **Effort:** S
- **Depends on / related:** B-19

### B-21 — Decide on dataset-scoped glossary terms and a column link from the Columns tab
- **Severity:** Medium
- **Evidence:** #11 · B-61..66
- **Problem:** The Glossary only works per connection; uploaded datasets (e.g. Demo — Sales) cannot get terms, and a term cannot be linked from a dataset's Columns tab.
- **Root cause / where:** Decision needed — feature gap, not a defect: the model already supports org-wide terms (`GlossaryTerm.data_source_id` nullable, `backend/app/models/models.py:1859-1873`, consumed by `backend/app/services/knowledge.py:461-467`), but the only create route is per source (`backend/app/routers/metadata.py:495` sets `data_source_id=source.id`) and `frontend/src/pages/Glossary.tsx:21-63` requires choosing a connection.
- **Fix:**
  1. (If accepted) Add `POST/GET /glossary` for org-wide terms (data_source_id NULL) and an "All data (org-wide)" option in the Glossary connection selector.
  2. Add optional `maps_to_dataset_id` (migration + `_migrate` line, see B-01) and a "Link a business term" action per column in the dataset Columns tab.
  3. Replace free-text Table/Column with pickers from the source catalog / dataset columns.
- **Tests:** automated: `backend/tests/test_glossary_rules.py` — an org-wide term is returned in the knowledge context of an uploaded dataset. Manual: create an org-wide term, ask about Demo — Sales using its synonym.
- **Effort:** L
- **Depends on / related:** B-01

### B-22 — Reject unsupported files when they are added to the upload queue
- **Severity:** Medium
- **Evidence:** #12 · B-67..79
- **Problem:** A .txt file is accepted by the picker and labelled "CSV · Read"; it fails only after Import, with the reason hidden under Technical details.
- **Root cause / where:** `frontend/src/pages/Upload.tsx:39` `ACCEPT` lists `.tsv` and `.txt`, and `frontend/src/pages/upload/readFile.ts:34-36` `kindOf` maps them to `'csv'`; the backend accepts only `ingest.SUPPORTED` + Access (`backend/app/services/ingest.py:27-41`, `backend/app/services/upload_store.py:54-75`) — no `.tsv`/`.txt` (confirmed; `.tsv` would fail too).
- **Fix:**
  1. Either add `.tsv`/`.txt` to the backend (rename to `.csv` before `_canonical_csv`, which already detects tab/semicolon dialects), or drop them from `ACCEPT` and from `kindOf`.
  2. In `Upload.tsx` add-files handler, mark files whose kind is `other` (or not allowed) as rejected immediately with "This file type cannot be imported (CSV, XLSX, JSON, XML, Parquet, Access)", and exclude them from Import.
  3. Put the backend `detail` text in the failure card headline instead of only "Upload failed".
- **Tests:** automated: `frontend/src/pages/upload/readFile.test.ts` + `frontend/src/pages/Upload.test.tsx` — adding `notes.txt` shows the rejection and the Import button ignores it. If `.tsv` is supported: `backend/tests/test_csv_dialect.py` — a .tsv upload imports. Manual: add a .txt → rejected on add.
- **Effort:** S
- **Depends on / related:** B-06

### B-23 — Mark connection types whose driver is not installed in the type grid
- **Severity:** Medium
- **Evidence:** #14 · B-84..100
- **Problem:** Access, Snowflake, BigQuery, Databricks, ClickHouse, Trino and ODBC are offered like any other type; the user learns the driver is missing only after picking one.
- **Root cause / where:** `frontend/src/pages/connections/ConnectionModal.tsx:189-197` renders type cards without reading `spec.driver_installed`; the notice exists only on step 2 (line 268-270) (confirmed).
- **Fix:**
  1. On each card, when `!c.driver_installed`, add a "Driver not installed" badge, `aria-describedby` text, and sort these to the end of their category (or behind a "Show unavailable types" toggle).
  2. Keep them selectable for admins who will install the driver, but disable "Create connection" with the notice.
- **Tests:** automated: `frontend/src/pages/connections/connectionsList.test.tsx` (or a new `ConnectionModal.test.tsx`) — a spec with `driver_installed:false` renders the badge on step 1. Manual: New connection → Snowflake card shows the badge.
- **Effort:** S
- **Depends on / related:** —

### B-24 — Make the import dataset name easy to replace and less collision-prone
- **Severity:** Medium
- **Evidence:** #17 · B-110..114
- **Problem:** The name field is pre-filled with the table name and clicking into it appends ("complaintsQA B complaints DQ"); a bare "shipments" default invites name collisions across connections.
- **Root cause / where:** `frontend/src/pages/connections/SchemaBrowser.tsx:134-138` `handleSelect` sets `dsName` to the bare table name; the input at line 392 has no select-on-focus and no duplicate-name check (confirmed).
- **Fix:**
  1. Default to `"<connection name> — <table>"`; add `onFocus={e => e.currentTarget.select()}` to the input.
  2. Warn inline when a dataset with that name already exists (same check the Upload page uses, `upload.nameTaken`).
- **Tests:** automated: `frontend/src/pages/connections/SchemaBrowser.queries.test.tsx` — selecting `shipments` on connection "Nile" pre-fills "Nile — shipments"; an existing name shows the warning. Manual: Browse → pick table → click name → whole text selected.
- **Effort:** S
- **Depends on / related:** —

### B-25 — Fix "We read 0 rows" on a new DirectQuery dataset
- **Severity:** Medium
- **Evidence:** #18 · B-110..114
- **Problem:** A new live dataset's onboarding strip says "We read 0 rows and 10 columns" and Rows shows "—".
- **Root cause / where:** `frontend/src/pages/datasetDetail/Overview.tsx:92` always uses `ds.row_count` (0 for DirectQuery, which stores no rows); line 215 then shows "—" (confirmed).
- **Fix:**
  1. For `live` datasets use a dedicated sentence: "This dataset is queried live from <source> — {cols} columns; rows are counted at the source" and, if available, fetch a `countd`/`count` via widget data (or the source catalog `row_count_estimate`) to show "~N rows at the source".
- **Tests:** automated: `frontend/src/pages/datasetDetail/Overview.test.tsx` — first-run strip for a DQ dataset does not contain "0 rows". Manual: create a DQ dataset → strip wording.
- **Effort:** S
- **Depends on / related:** B-30

### B-26 — Decide whether the seeded demo connection is synced at seed time
- **Severity:** Medium
- **Evidence:** #20 · B-119/120
- **Problem:** "Demo — Live SQLite" has never been synced, so its review page and glossary-linked metadata are empty for every new user.
- **Root cause / where:** Decision needed — product choice, not a defect: `seed_demo_directquery` (`backend/app/services/demo_content.py:~2282-2330`, creates `DataSource(...)` at ~2308) creates the source with the default `sync_status="pending"` (`models.py:406`) and no SyncRun; `backend/app/routers/demo.py:61` does not trigger a sync.
- **Fix:**
  1. (If accepted) After the demo commit in `seed_demo` (`backend/app/routers/demo.py:74`), start a background catalog sync for the demo source (same `run_sync_background` call as `metadata.trigger_sync`, `allow_llm=False`) — the SQLite file is local, so it takes seconds.
  2. Otherwise show "Not synced yet — Run sync" as the empty state on the review page (already partly there).
- **Tests:** automated: `backend/tests/test_demo_directquery.py` — after seeding, a SyncRun exists for the demo source (or, with the background task awaited, source objects exist). Manual: Load demo content → `/connections/1/review` shows 1 table / 8 columns.
- **Effort:** S
- **Depends on / related:** B-30

### B-27 — Do not hide a user's own datasets as "test-looking" in pickers
- **Severity:** Medium
- **Evidence:** #22 · B-121..127
- **Problem:** The dataflow source list hides "QA B upload", "Qa sample", "QA B complaints DQ" behind "Show 3 test-looking" purely by name.
- **Root cause / where:** `frontend/src/lib/testData.ts:10` `TEST_NAME` matches any name starting with `qa` followed by a space/underscore/digit; `frontend/src/lib/cleanDatasets.ts:27-28` hides every match that is not certified, including the current user's own datasets (confirmed).
- **Fix:**
  1. In `cleanDatasets`, never hide datasets created by the current user or updated in the last N days; hide only others' stale test-looking names.
  2. Narrow `TEST_NAME`: drop bare `qa` as a prefix (keep `qa_sample`, `test`, `tmp`, …).
- **Tests:** automated: `frontend/src/lib/cleanDatasets.test.ts` — own dataset "QA B upload" stays visible; another user's "tmp_orders" is hidden; `frontend/src/lib/testData.test.ts` — "QA B upload" is not test-looking. Manual: Dataflows source list shows own QA uploads.
- **Effort:** S
- **Depends on / related:** B-09

### B-28 — Widen the Inspect outliers dialog so the inspected column is visible
- **Severity:** Medium
- **Evidence:** #24 · B-150..152
- **Problem:** The 560 px modal cuts off columns after "category" — including the inspected `revenue` column — and wraps dates/product names onto 2-3 lines.
- **Root cause / where:** `frontend/src/components/report/OutlierDetailsDialog.tsx:61` fixed `width: 560`; the rows table (line 117-133) renders columns in dataset order with wrapping cells (confirmed).
- **Fix:**
  1. Use `width: min(960px, 94vw)`; set `white-space: nowrap` on cells and make the table scroll horizontally with a visible scrollbar.
  2. Put the inspected column first (and sticky) in `outliers.columns`/rows.
- **Tests:** automated: `frontend/src/components/report/OutlierDetailsDialog.test.tsx` — the inspected column is the first header. Manual: Analysis → Anomalies → Inspect outliers on revenue → revenue is first and visible.
- **Effort:** S
- **Depends on / related:** —

### B-29 — Refresh the connection review page when a sync finishes
- **Severity:** Medium
- **Evidence:** #25 · B2-02..05
- **Problem:** After Run sync completed, the header stayed "0 tables · 0 columns", "Columns (0)", "No tables yet …" until a manual reload.
- **Root cause / where:** Partly unconfirmed. `SourceReview.tsx:180-198` `pollUntilDone` does `await load()` after the run ends, which should refetch `metadataApi.review`; why the header stayed stale is not proven from code. Confirmed part: `frontend/src/components/setup/SourceSummary.tsx:18-22` fetches the summary once on mount and never again, so "What this database holds" is always stale after a sync started on the page.
- **Fix:**
  1. Reproduce with network logging to see whether `/review` is refetched after the run and what it returns (possible race: the run row flips to finished before `link_datasets`' writes are committed — check `run_sync_background` commit order, `backend/app/services/metadata/sync.py:804-859`).
  2. Pass a `refreshKey` (incremented on run completion) to `SourceSummary` and include it in its effect deps.
  3. If a race is found, set `run.status` only after the final commit (commit the objects first, then the run status).
- **Tests:** automated: `frontend/src/pages/SourceReview.test.tsx` — after the poll returns `ok`, `metadataApi.review` and `setupApi.summary` are called again and the header shows the new counts. Manual: Demo — Live SQLite → Run sync → counts update without reload.
- **Effort:** M
- **Depends on / related:** B-04, B-26

### B-30 — Say "row count unknown" instead of "0 rows", and pluralise "tables"
- **Severity:** Medium
- **Evidence:** #26, #43 · B2-02..05, B2-60/61
- **Problem:** "Demo — Live SQLite has 1 tables with 0 rows in total" for a 12,000-row table, next to a "Rows not counted" pill.
- **Root cause / where:** `backend/app/services/guided_setup/understand.py:395-398` returns `rows: 0` with `rows_known: false` (SQLite has no statistics; `introspect.py:268`). The sentence `setup.u.factsSentence` ("{tables} tables with {rows} rows", `frontend/src/i18n/en.ts:4707`) is used regardless of `rows_known` in `frontend/src/pages/setup/UnderstandStep.tsx:197` and `frontend/src/components/setup/SourceSummary.tsx:26` (confirmed); the string has no plural form.
- **Fix:**
  1. Add `setup.u.factsSentenceNoRows` ("{name} has {tables, plural, one{# table} other{# tables}}; this database does not keep row counts") and use it when `totals.rows_known === false` in both places.
  2. Convert `factsSentence` to ICU plural for tables and rows (en + ar).
  3. Optional: for small SQLite/DuckDB sources, run `COUNT(*)` per table in introspect when cheap.
- **Tests:** automated: `frontend/src/pages/setup/UnderstandStep*.test.tsx` and a `SourceSummary` test — `rows_known:false` never renders "0 rows"; 1 table renders "1 table". Manual: `/setup/1` sentence wording.
- **Effort:** S
- **Depends on / related:** B-25

### B-31 — Make "Show details" in setup step 1 not leave the wizard by surprise
- **Severity:** Medium
- **Evidence:** #28 · B2-19..21
- **Problem:** "Show details" looks like an expander (chevron) but navigates to `/connections/{id}/review`, losing the user's place.
- **Root cause / where:** `frontend/src/pages/setup/UnderstandStep.tsx:170-172` is a `<Link>` with a `ChevronDown` icon (confirmed).
- **Fix:**
  1. Either open the review page in a new tab with an external-link icon and the label "Open full review (new tab)", or render the details inline in a collapsible section; and add "Back to guided setup" on the review page when arrived from setup (`?from=setup`).
- **Tests:** automated: `frontend/src/pages/Setup.test.tsx` — the details link has `target="_blank"` (or toggles an inline section). Manual: step 1 → Show details keeps the wizard.
- **Effort:** S
- **Depends on / related:** —

### B-32 — Recount rows and columns after one-click fixes
- **Severity:** Medium
- **Evidence:** #34 · B2-34..45
- **Problem:** After fixes the wizard still says "64,420 rows · 26 columns" and lists all 9 items (also after reload); the dataset's Data tab says 64,420 while the real output is 62,662 × 24.
- **Root cause / where:** `fix_item` (`backend/app/routers/guided_setup.py:1562-1597`) adds prep steps through `set_prep_steps` (`backend/app/routers/datasets.py:3327-3368`), which saves the pipeline but never recomputes `ds.row_count`/`col_count`; the stored finding keeps its original `rows`/`columns` and only appends to `fixed` (confirmed).
- **Fix:**
  1. After `set_prep_steps`, recompute the shape (reuse the prep preview's shape-after or `alerts.alert_frame`) and update `ds.row_count`/`col_count`.
  2. In `fix_item`, update the finding's `rows`/`columns`, and mark the fixed item as done so the summary bullets drop it (`CheckStep.tsx:150-195` already reads `rows_after` for automatic cleaning — extend that to manual fixes).
- **Tests:** automated: `backend/tests/test_guided_setup_cleaning.py` — after a "remove duplicates" fix, the check endpoint reports the reduced row count and `datasets.row_count` matches. Manual: apply fixes in step 3 → header shows 62,662 · 24.
- **Effort:** M
- **Depends on / related:** B-33

### B-33 — Confirm before one-click fixes change a dataset already in use
- **Severity:** Medium
- **Evidence:** #35 · B2-34..45
- **Problem:** The step says "This dataset was already in use, so nothing was changed in it automatically", yet each one-click fix permanently changes that dataset's pipeline with no warning about other users and dashboards.
- **Root cause / where:** `frontend/src/pages/setup/CheckStep.tsx:71-78` `fix()` calls `setupApi.fix` directly; copy `setup.k.notAuto` (`en.ts:4881`) shown at `CheckStep.tsx:195`. Backend already knows dashboards per dataset (`_dashboards_using`, `backend/app/routers/guided_setup.py:991`) (confirmed).
- **Fix:**
  1. Return `used_by: {dashboards: n, names: [...]}` per dataset in the check step payload.
  2. When `!d.auto_clean` and `used_by.dashboards > 0`, open `useConfirm()` before the first fix: "This changes 'shipments' for everyone — N dashboards use it", with an alternative "Make a copy for this analysis".
- **Tests:** automated: `frontend/src/pages/setup/CheckStep.test.tsx` — fix on a non-auto dataset with dashboards opens the confirm; cancelling makes no API call. Manual: step 3 on an existing dataset → confirm appears.
- **Effort:** S
- **Depends on / related:** B-32, B-02

### B-34 — Add the two missed checks: numbers stored as text in the source, and end-before-start dates
- **Severity:** Medium
- **Evidence:** #36, #37 · B2-34..45 (B2-6)
- **Problem:** `declared_value` (TEXT in the source, TXT in the grid) is summed as a number with no "stored as text" finding; 55 rows with `delivered_at < created_at` are not detected.
- **Root cause / where:** (a) The "numbers stored as text" check (`backend/app/services/data_quality.py:129-134`, item at `backend/app/services/guided_setup/health.py:362-366`) only fires when the pandas column is `object`; the imported CSV is re-inferred as numeric by `load_file`, so the source's text type is lost while `DatasetColumn.dtype` (grid) keeps text — likely, unconfirmed. (b) `generic_rules` (`health.py:399-470`) has negative-amount, future-date and stray-date rules but no cross-column date-order rule (confirmed).
- **Fix:**
  1. In `column_items`, compare the dataset's stored column dtype (or the source column type) with the frame dtype; when the source says text and values parse as numbers, emit the `textnum` item with the `retype` action; make the grid and checks agree on the type.
  2. Add a date-order rule to `generic_rules`: for date pairs ordered by `insights.order_event_dates` (start first), count rows where a later event date < the start date; emit a warning with an `exclude` action and a rule `"<end> >= <start>"`.
- **Tests:** automated: `backend/tests/test_guided_setup_health.py` — a frame with `created_at`/`delivered_at` where 5 rows are reversed yields one date-order item with rows=5; a dataset whose column meta is text but values are numeric yields a `textnum` item. Manual: re-run step 3 on Nile shipments → 9/9 planted problems found.
- **Effort:** M
- **Depends on / related:** —

### B-35 — Let the dashboard designer answer "by <entity>" through a linked key
- **Severity:** Medium
- **Evidence:** #39 · B2-46..53
- **Problem:** The stated question is "late deliveries and delivery fees by branch", but every suggested breakdown is by `service_type`, although shipments links to branches via `origin_branch_id` (the app admits "not answered").
- **Root cause / where:** Unconfirmed in detail. The design gate works on one dataset's columns (`backend/app/services/guided_setup/answer.py` `prepare` :1605, `validated_cards` :2128) and has no lookup/join to the related `branches` table; `origin_branch_id` is classed as an identifier, so it is not offered as a dimension. Partly a product decision (joins in guided setup).
- **Fix:**
  1. When the demand names an entity that maps to a confirmed source relationship (`SourceRelationship`), allow the FK column as a dimension, labelled by the related table's name column via a join prep step or a lookup (`prep` join step already exists).
  2. Minimum fix: allow `<entity>_id` columns as a dimension when the question names that entity, with the caption "by branch id".
- **Tests:** automated: `backend/tests/test_guided_setup_answer.py` — demand "fees by branch" with an `origin_branch_id` column and a confirmed relationship to `branches` yields at least one widget with that dimension. Manual: rerun step 4 → a "by branch" chart exists.
- **Effort:** L
- **Depends on / related:** B-36

### B-36 — Stop proposing meaningless derived metrics and totals
- **Severity:** Medium
- **Evidence:** #40 · B2-46..53 (B2-10)
- **Problem:** Suggestions include "Delivery attempts pct of delivery fee egp" (a count as a % of money), "Total weight kg by service type", "Total of 5 numbers" (weight + value + fees + COD + attempts), and a KPI caption "countd(shipment_id)".
- **Root cause / where:** `rate_measures` (`backend/app/services/derived_fields.py:60-102`) pairs part/whole when they share any non-generic word — "delivery" links `delivery_attempts` and `delivery_fee_egp`; it never checks that both are the same kind (count vs amount) though `column_classes` knows it (confirmed). The source of "Total of 5 numbers" and the raw `countd(...)` caption is unconfirmed (likely a multi-measure card from `analyst_panel` and a missing `readback` label).
- **Fix:**
  1. In `rate_measures`, require `column_classes` kind of part == kind of whole (both counts or both the same currency); add `delivery`, `fee`, `egp` style unit words to a unit-check rather than the shared-noun test.
  2. Find the widget producing "Total of N numbers" (grep the panel's multi-measure KPI) and refuse to sum measures with different kinds/units (`semantic_guard.non_additive_kind`).
  3. Ensure KPI captions go through `readback` labels ("Shipments (distinct)") rather than the raw aggregation string.
- **Tests:** automated: `backend/tests/test_derived_fields*.py` (new) or `test_suggest_gap_review.py` — a frame with `delivery_attempts` (count) and `delivery_fee_egp` (money) yields no rate measure; a multi-measure total across different units is refused. Manual: rerun step 4 on Nile shipments → none of the three nonsense widgets.
- **Effort:** M
- **Depends on / related:** B-05, B-35

Coverage: worklist items 1..43 all mapped (merged: #1+#10 → B-15; #7+#8 → B-19; #15+#19+#42 → B-03; #16+#29 → B-04; #26+#43 → B-30; #27+#30+#32+#41 → B-11; #36+#37 → B-34. Decision needed: #11 → B-21 (feature gap), #20 → B-26 (seed-time sync), part of #9 → B-20 (live checks scope); environment-only DuckDB lock part of #15/#16/#19 noted in B-03 and handled by B-13. Cross-cutting additions: B-01 (init.sql schema gap), B-13 (test DuckDB cache path), B-14 (widget-type count test)).


## Dashboards, builder & charts

### C-01 — Render tiles already on screen without needing a scroll, in View and in Present
- **Severity:** High
- **Evidence:** #12, #17 · C-50..66 (C-55, C-56, C-57), C-74; EVALUATION §2 item 9
- **Problem:** When a seeded dashboard first opens, its tiles stay as blank white boxes or "Loading…", even after 12 s. One wheel scroll makes all of them render at once. Present mode cannot be scrolled, so every data tile stays on "Loading…". This affects how every demo looks on first open.
- **Root cause / where:** `frontend/src/components/report/WidgetRenderer.tsx:711-737` (viewport-lazy fetch). Fetching is gated on `hasBeenVisible`, and only an `IntersectionObserver` callback (`rootMargin: '300px'`) sets it. There is no synchronous "already in view" check and no fallback, so a tile whose first IO entry reports `isIntersecting=false` waits until a scroll causes a new intersection. That first entry can be false because of layout that has not settled yet: `datasetsReady` gating, `useMeasuredWidth`'s 900 px fallback width, `transform: scale(canvasScale)` at `pages/ReportBuilder.tsx:4146`. Present mode passes `eagerFetch={kiosk}` (`ReportBuilder.tsx:4288`), which skips the IO. Its tiles still stayed on "Loading…", so a second gate is also involved. Candidates are `loading` never being cleared when a fetch is aborted and replaced (`finally { if (!signal.aborted) setLoading(false) }`, line 692) and requests waiting in the `widgetDataApi` concurrency queue (`services/api.ts:2905-2930`). (unconfirmed: the code path is clear, but I could not reproduce the exact trigger without running the app)
- **Fix:**
  1. In the lazy-fetch effect (WidgetRenderer.tsx ~714), call `el.getBoundingClientRect()` right after `io.observe(el)`. If the rect is within `window.innerHeight + 300` and has a non-zero size, `setHasBeenVisible(true)` immediately.
  2. Add a safety net: a `setTimeout(…, 1500)` that re-runs the same rect check, plus a `resize` listener on the canvas `ResizeObserver` that re-checks while `!hasBeenVisible`.
  3. In Present (`kiosk`) and print, keep `eagerFetch`. Also make `fetchData` always clear `loading` when it is superseded: set `loading` from the newest call, or move `setLoading(false)` into the effect cleanup of the superseded request.
  4. Add a dev-only console warning when a tile has been "loading" for more than 20 s, naming the widget id and whether it is queued in `wdQueue` or in flight. This identifies the second gate if the cause is not one of the above.
- **Tests:** automated: `frontend/src/components/report/WidgetRenderer.test.tsx`. Stub `IntersectionObserver` so it never fires and mock `getBoundingClientRect` to be inside the viewport, then assert `widgetDataApi.query` is called on mount. A second case aborts the first fetch with a config change and asserts "Loading…" disappears after the second resolves. Add a Playwright journey `frontend/e2e/journeys/view_present_journey.mjs`: open Demo — Sales Overview and Time & Change in View and in Present, wait 5 s, and assert no tile text equals "Loading…", without scrolling. Manual: open each seeded demo, and Present, with no mouse movement. All charts should draw within a few seconds.
- **Effort:** M
- **Depends on / related:** —

### C-02 — One shared number formatter for every value in tables, crosstabs, matrices, KPIs and cards
- **Severity:** High
- **Evidence:** #28, #11, #14 (part: "Rows"/"Missing cost" shown as "$ 2,000") · C3-20, C-35, C-37..41 (Crosstab), C-65; area tables C3-1, C-35/41
- **Problem:** Matrix, Crosstab and grouped Table cells show raw floats such as "700019.84", "2221091.66" and "795152.7", with no currency, no thousands separators and inconsistent decimals, while every chart shows "$ 700,020". A count of a currency column, such as the KPI "Rows" (count of revenue), is shown as "$ 2,000".
- **Root cause / where:** (confirmed)
  - `frontend/src/components/report/WidgetBody.tsx` `WindowedTable` (~lines 864 and 921) formats each cell with `formatValue(v, allFormats?.[cols[j]])`, keyed by the column name. For a grouped table the columns are `name`/`value`. For a crosstab or matrix they are the column-dimension values ("Hardware", "Software", `__total__`). None of these is a dataset column, so no format is found and `formatValue` (`components/report/chartUtils.tsx:189`) falls back to `String(Number(v.toPrecision(15)))`, which is ungrouped and raw.
  - `WidgetBody.tsx:150` picks `measureFmt = allFormats[cfg.measure]` regardless of `cfg.aggregation`, so `count`/`countd` of a currency column inherits "$".
  - `PivotTable.tsx:~101` has the right idea (`fmtStr(v, formats?.[mn])` keyed by measure), but only covers the nested-pivot path.
- **Fix:**
  1. Add `formatMeasure(value, { column, aggregation, formats, quantity=true })` in `frontend/src/lib/displayNumber.ts`, or as a wrapper next to `fmtStr` in `chartUtils.tsx`. For `count|countd|distinct|frequency` it returns a grouped integer with no symbol. For `pct` it returns a percent. Otherwise it applies the column's `CalcColumnFormat`. With no format it falls back to `formatTableCell(v, quantity)`, which is grouped and gives at most 2 dp.
  2. `WindowedTable`: work out a per-column format map before rendering. For a `grouped` table, `value` maps to the measure's format. For a crosstab or matrix (`data.type === 'crosstab'`), every column after the first, including `__total__` and the totals row, maps to the measure's format (`data.measure ?? cfg.measure`). Raw-table columns keep their own name. Right-align numeric cells.
  3. KPI (`WidgetBody.tsx:449-560`), Card (`:568`), List (`WindowedList`), `show_as_table` (`:644`) and Gauge (`chartRenderers/GaugeRenderer.tsx:128`) call `formatMeasure` with the widget's aggregation instead of `fmtStr(val, measureFmt)`.
  4. Axis ticks: route `valueTick` in `chartRenderers/axisOptions.ts` through the same helper, so that "$ 600,000" next to "1.2M" (C-10, C3-11) gets the currency symbol on the abbreviated tick too.
  5. Remove ad-hoc formatting from `PivotTable.tsx` and `HierPivot.tsx` in favour of the helper.
- **Tests:** automated: `frontend/src/lib/displayNumber.test.ts`. The helper should return: currency format with 700019.84 → "$ 700,020"; count of a currency column → "2,000"; a `none` format with 795152.7 → "795,152.7"; the Arabic digits path still works. `frontend/src/components/report/tablePaging.test.tsx` (or a new `WidgetBody.table.test.tsx`): a crosstab payload `{type:'crosstab', columns:['region','Hardware','__total__'], rows:[['Asia',700019.84,1.2e6]]}` with `allFormats.revenue` currency renders "$ 700,020", and the grouped table `value` column is formatted. `WidgetRenderer.test.tsx`: KPI `{measure:'revenue', aggregation:'count'}` shows no "$". Manual: on Demo — Sales, add a Matrix (region × category, revenue), a Table (region, revenue) and a KPI "count of revenue". Each should match the formatting the charts use.
- **Effort:** M
- **Depends on / related:** C-03 (trust dashboard KPIs), C-11 (summed percentages are an aggregation-default problem, not a formatting one)

### C-03 — Fix the seeded demo configs: the World Sales Map contour tile and the "Can I trust this data?" use case
- **Severity:** High
- **Evidence:** #13, #14 · C-54/C-61 (World Sales Map "Where shipments concentrate" shows "SAMPLE Needs Latitude · Longitude"), C-65 (Use case — Can I trust this data?); EVALUATION area table C-54/65
- **Problem:** One World Sales Map tile shows the "author has not finished this widget" placeholder. In the trust dashboard, "Rows" and "Missing cost" both show "$ 2,000" (and "Missing cost" actually counts non-missing values), the "Prepared" card shows "Needs Fields", and the "as loaded" and "prepared" charts are identical, so the story the demo tells does not work.
- **Root cause / where:** (confirmed)
  - `backend/app/services/demo_content.py:939-941` seeds `map_contour` with only a nested `roles` dict. `frontend/src/components/report/WidgetPlaceholder.tsx:45` `missingRequiredRoles` reads only flat keys (`cfg['lat']`), so the tile counts as unfinished. `WidgetBody.tsx:324` decides whether there is something to draw from `rows|matrix|cells|bars|links|forecast|points|series|value`. The contour result carries `grid` (`widget_data.py:3084 shape_geo_contour`), so `nothingToDraw` is true and the placeholder wins. The other roles-only map tiles (clusters, lines, network) escape only because they return `rows`.
  - `backend/app/services/demo_use_cases.py:147-158` `_quality_specs` has three problems. "Rows" is `count(revenue)`, which inherits revenue's currency format (see C-02). "Missing cost" is `count(cost)`, which counts NON-missing values; there is no `nmiss` aggregation in `widget_data.AGGREGATION_NAMES` (line 342), and the demo cost column has no nulls at all (`demo_content.py:203`). The "Prepared" `card` sets `measure`, but the card role is `measures` (`types/report.ts:443`), hence "Needs Fields".
  - `_apply_quality_features` (`demo_use_cases.py:441-447`) filters `cost > 0`, but cost is always positive, so the prepared chart equals the raw one.
- **Fix:**
  1. `demo_content.py` `_maps_specs`: write flat keys (`"lat":"origin_lat","lon":"origin_lon","measure":"shipments"`) for every map spec, or pass every spec through `widget_roles.migrate_widget_config` in `seed_demo_reports` (`demo_content.py:1102-1110`) before `ReportWidget(...)` is created.
  2. Frontend hardening: in `missingRequiredRoles`/`missingWidgetOptions`, resolve roles the way the backend `resolve_roles` does (`cfg.roles?.[role] ?? cfg[configKeyFor(role)]`), and add `data?.grid` (and `data?.nodes`) to the drawable check in `WidgetBody.tsx:324`.
  3. `_quality_specs`: "Rows" becomes `{"measure":"revenue","aggregation":"count"}` with the C-02 formatter, or uses a distinct `__rows__` count. Replace "Missing cost" with an honest metric over data that exists, e.g. "Refund rows" (`count` with `filters:[{column:'revenue',op:'lt',value:0}]`), or add an `nmiss` aggregation (`_agg_series`: `int(s.isna().sum())`, plus `_pandas_agg_fn`, `duck_agg`, the frontend `AGGREGATIONS`) and seed some null costs. "Prepared" card → `{"measures":["revenue"],"aggregation":"sum"}` plus `prep_steps`.
  4. Make the prep step do something visible: e.g. `{"kind":"filter","column":"revenue","op":"gt","value":0}` to drop refunds (about 3% of rows, `demo_content.py:185-197`), so "as loaded" and "prepared" differ.
  5. Add an Alembic data migration, or rely on the documented re-seed, so that existing installs get the fixed configs.
- **Tests:** automated: `backend/tests/test_demo_reports.py`: a new test asserts that every seeded widget has no missing required roles according to `widget_roles.missing_roles(widget_type, config)` and the flattened config (no `roles`-only map). `backend/tests/test_demo_use_cases.py`: the quality report's "Prepared" card has `measures`, the prepared bar's widget-data differs from the raw bar's, and no `count` KPI is backed by a currency-formatted column without the C-02 formatter path. `frontend/src/components/report/WidgetPlaceholder.test.tsx`: `missingRequiredRoles({widget_type:'map_contour', config:{roles:{lat:'a',lon:'b'}}})` returns `[]`. Manual: re-seed, open World Sales Map (all tiles draw) and "Can I trust this data?" (sensible counts, no "Needs Fields", the two bars differ).
- **Effort:** M
- **Depends on / related:** C-02, C-29 (Origin density bubbles on the same dashboard)

### C-04 — Drop a stale widget selection when the page changes, so no 404 PATCH is sent to a widget on another page
- **Severity:** High
- **Evidence:** #3 · C-14/15 (404 PATCH /reports/23/pages/40/widgets/255 + uncaught AxiosError; repeated for widgets 257/258/259/271/275/300), C-24, C-35, C-37..41
- **Problem:** After a page is added or switched while a widget is selected, the Properties pane keeps showing the widget from the old page. Every edit then PATCHes `/pages/<new page>/widgets/<old widget>`, gets a 404, and throws an uncaught AxiosError. A click near the Assign-data modal also landed on the page-tab "+" and created a page.
- **Root cause / where:** (confirmed for the stale selection)
  - `frontend/src/pages/ReportBuilder.tsx:2420-2435` `addPage` calls `setActivePage(page)` without `setSelectedW(null)`. The same applies to `handleButtonApplyBookmark` (`:1633`), `onGo` in `PresentControls` (`:4728`) and `loadReport`'s `setActivePage(prev => …)` (`:557`), which keeps the selection.
  - `updateWidgetConfig` (`:2076-2120`) PATCHes `activePage.id` + `selectedW.id` with no check that the widget is on that page, and the caller does not catch the error (unhandled promise → pageerror).
  - The "+ Add" click going through to the page-tab "+" is unconfirmed. `AssignDataDialog`/`AddFieldDialog` (`components/report/DataRolesList.tsx:165-297`) close on backdrop `mouseDown`, so a fast click sequence can close the modal and let the next click land on the tab strip.
- **Fix:**
  1. Add an effect `useEffect(() => { setSelectedW(s => s && activePage?.widgets.some(w => w.id === s.id) ? s : null); setMultiSelectedIds(new Set()) }, [activePage?.id])`. This makes every page change clear a widget selection that is not on the new page.
  2. In `updateWidgetConfig`, resolve the widget's real page (`report.pages.find(p => p.widgets.some(w => w.id === selectedW.id))`). PATCH that page, or abort with a toast if the widget is not found. Wrap the call sites in `.catch(e => toast.error(friendlyError(e)))`.
  3. Modals: close on backdrop `click` (`mousedown` and `mouseup` both on the backdrop) instead of `mouseDown`, so a press that starts inside the dialog cannot close it and leak the following click.
- **Tests:** automated: `frontend/src/pages/ReportBuilder.test.tsx`: select a widget on page 1, click the add-page "+", and assert the Properties pane shows the page/empty state and that no `reportsApi.updateWidget` call goes out with the old widget id. Another test switches tabs with a selection and asserts `selectedW` is cleared. `DataRolesList.test.tsx`: a mousedown inside the dialog followed by mouseup on the backdrop does not close it. Manual: select a chart, add a page, then change a title. There should be no 404 in the console.
- **Effort:** S
- **Depends on / related:** C-12 (accidental clicks on overlays)

### C-05 — Show the dataset chosen in "Create a dashboard" as soon as the builder opens
- **Severity:** High
- **Evidence:** #2 · C-07/08
- **Problem:** After Create with "Demo — Sales" picked, the builder's Fields panel says "Attach a dataset to this report to browse columns" and DATASETS lists only "+ Add Dataset". After a reload the dataset is there. Users think the pick was lost and may attach it twice.
- **Root cause / where:** `frontend/src/pages/Reports.tsx:143-168` `create` sends `dataset_id` and navigates to `/reports/{id}?edit=1`. `backend/app/routers/reports.py:288-305` stores it. In the builder, `reloadAttachedDatasets` (`pages/ReportBuilder.tsx:740-763`) swallows any failure of `datasetsApi.get` (`catch { setDatasetsReady(true) }`), leaving `dataset` null with no retry and no message. The effect at `:781-799` re-runs only when `report.dataset_id` changes, so one failed or aborted fetch on the slow first load sticks until a reload. (unconfirmed: the most likely path given the code; the QA environment was under heavy load)
- **Fix:**
  1. In `reloadAttachedDatasets`, retry once on failure. If it still fails, set an `attachError` state and render "Couldn't load <dataset> — Retry" in the Fields panel, not the misleading "Attach a dataset".
  2. Tell "no dataset attached" (`!report.dataset_id`) apart from "dataset not loaded yet": while `report.dataset_id && !dataset`, show a skeleton instead of `bc.shell.ds.attachToBrowse` (`ReportBuilder.tsx:3468-3469`).
  3. Optionally hand the created report to the builder through `navigate(to, { state: { report: r } })` and prime `setReport` from `routeLocation.state`, so the first paint already knows the dataset.
- **Tests:** automated: `frontend/src/pages/ReportBuilder.test.tsx`: `reportsApi.get` resolves with `dataset_id: 4` and `datasetsApi.get` rejects once and then resolves. Assert the fields list renders the dataset's columns and never shows "Attach a dataset to this report". A second case where it always rejects asserts the Retry message. Manual: create a dashboard with Demo — Sales. The fields should be listed straight away, with no reload.
- **Effort:** S
- **Depends on / related:** C-30 (same Create dialog)

### C-06 — Make the Word cloud draw its words and reject a number as "Word text"
- **Severity:** High
- **Evidence:** #5 · C-20..23
- **Problem:** With Word text = product (10 values) and Size = revenue, the tile is completely blank, even after a reload, with no message. A numeric column (revenue) was accepted as "Word text".
- **Root cause / where:** `frontend/src/components/report/chartRenderers/WordCloudRenderer.tsx`. Font size is `14 + t*46` px with `minV = min(values, 0)`, so 10 similar revenue values all get roughly 50-60 px. d3-cloud silently drops any word it cannot place, and 15-25-character product names at 55 px (about 600-800 px wide) do not fit the 600×400 default box, so nothing is placed. The seeded demo works only because it uses short topic words with counts. The `ResizeObserver` effect has `[]` deps and runs while the early "configure" branch is rendered, so `containerRef` is null and the observer is never attached; the layout box never follows the tile size. When zero words are placed there is no fallback text. The "Word text" role is `category`, and `roleAccepts('category')` returns `any` (`types/report.ts:303`), so numbers are allowed. (root cause likely; confirmed from code reading, not seen in a browser)
- **Fix:**
  1. Attach the size observer through a callback ref, or depend on `rows.length > 0`, so it observes the real container. Pass `plotW/plotH` from `MeasuredChart` (already in `ChartRendererProps`) instead of a hard-coded 600×400.
  2. Scale font size to the box and the text: `maxFont = min(60, box.w / (longestLabel.length * 0.6))`, and use `minV = min(values)` (not 0) so sizes spread.
  3. In the `end` callback, if fewer words were placed than given, retry once at 0.7× scale. If still zero, render "Words are too long to fit — enlarge the tile" instead of a blank SVG.
  4. Word text role: offer non-numeric columns first, and show an inline warning when a numeric measure is chosen, the same way as `semanticAggregationWarning` in `WidgetConfigPanel.tsx:2092-2108`.
- **Tests:** automated: new `frontend/src/components/report/chartRenderers/WordCloudRenderer.test.tsx`. Mock `d3-cloud` to record the `fontSize` accessor and the `size()` call, and assert the max font size fits a 25-character word inside `plotW`. Mock `end` with `[]` and assert the fallback message. Manual: Word cloud with product + revenue on Demo — Sales should show 10 words.
- **Effort:** S
- **Depends on / related:** C-09 (role type validation)

### C-07 — Give Scatter an X measure and a Y measure, and say so when nothing can be plotted
- **Severity:** High
- **Evidence:** #6 · C-24
- **Problem:** The Scatter roles are Dimension + one Measure. With product + units, the tile shows axes and no points, and there is no way to give it an X measure and a Y measure.
- **Root cause / where:** (confirmed) `frontend/src/types/report.ts:346` `scatter: [category (required), measure]`, and the backend `widget_roles.py:105` `"scatter": ("category",)` with `widget_data.py:4225 "scatter": shape_series`. `ScatterChartRenderer.tsx:8` plots `x: r.x ?? r.name` on `XAxis type="number"`. A text dimension ("Aurora Suite") is not a number, so recharts drops every point. The demo "Weight against height" works only because its dimension is numeric.
- **Fix:**
  1. Change scatter roles to `measure` (X, numeric, required), `measure2` (Y, numeric, required), and `category` (Label/detail, optional). Mirror this in `widget_roles.REQUIRED_ROLES` and the parity test.
  2. Backend: route `scatter` to `shape_xy_numeric` (`widget_data.py:2095`) when `measure2` is set. When a `category` is also set, aggregate x and y per category (`agg` and `aggregation2`) so that one point per product is possible. Keep `shape_series` for legacy configs that have a numeric dimension.
  3. Add a migration in `widget_roles.migrate_widget_config` and `configShape.ts migrateWidgetConfig`: a legacy scatter with a numeric `dimension` becomes `measure` (X) = dimension and `measure2` (Y) = the old measure.
  4. Renderer: if every x is non-numeric, render an `EmptyState` saying "X must be a number — assign an X measure".
  5. Update the demo spec "Weight against height" (`demo_content.py:767`).
- **Tests:** automated: `backend/tests/test_widget_roles.py` (scatter requires measure + measure2), a new `backend/tests/test_widget_data_scatter.py` (one point per category with avg x/y), `frontend/src/components/report/chartRenderers/index.test.tsx` or a new `ScatterChartRenderer.test.tsx` (string x shows the empty-state message), and `frontend/src/components/report/widgetConfigPanel` migration cases in `widgetConfigMigrations.json`. Manual: Scatter units (X) × revenue (Y) by product should show 10 points.
- **Effort:** M
- **Depends on / related:** —

### C-08 — Label Sankey nodes and colour flows by their source
- **Severity:** High
- **Evidence:** #7 · C-25
- **Problem:** Region → category → revenue draws ribbons and node bars but no node names, so the chart cannot be read. All flows use one pale colour.
- **Root cause / where:** (confirmed) `frontend/src/components/report/chartRenderers/SankeyChartRenderer.tsx:15-22`. The recharts `<Sankey>` is given `node={{fill,stroke}}` (an object), so recharts draws a bare rectangle with no text. `link` is one fixed stroke.
- **Fix:**
  1. Pass a custom `node` element (`node={<SankeyNode/>}`) that draws the rect plus a `<text>`: to the right of left-side nodes and to the left of right-side nodes (`x + width + 6`, `textAnchor` start/end), truncated to the available margin, with the formatted value in the `<title>`.
  2. Pass a custom `link` that colours each ribbon by `COLORS[sourceIndex % COLORS.length]` at 0.35 opacity. Colour nodes the same way.
  3. Widen the right margin from the measured `plotW`, using the longest label length.
- **Tests:** automated: new `frontend/src/components/report/chartRenderers/SankeyChartRenderer.test.tsx`. Render `{nodes:[{name:'Europe'},{name:'Hardware'}], links:[…]}` and assert the text "Europe" and "Hardware" are in the SVG, and that two links get different strokes. Manual: Sankey region → category should show the region names on the left and the category names on the right.
- **Effort:** S
- **Depends on / related:** C-15 (labels on other hierarchy charts)

### C-09 — Put each clicked field into a role of the matching type and validate map coordinates
- **Severity:** High
- **Evidence:** #30, #34 · C4-05..11 (origin_lat → Country, origin_lon → Latitude, from_city → Longitude), C4-12/13 (shipments as Longitude); area table C4-A, C4-B
- **Problem:** Clicking fields in the Fields panel fills a Point Map's roles in order, ignoring type: a latitude goes into Country and a text city into Longitude, with no warning. The Longitude role also accepts any number, e.g. a measure like `shipments` with values 2-40.
- **Root cause / where:** (confirmed)
  - `frontend/src/lib/fieldPlacement.ts:23-25` `isNumericRole` treats only `measure*`, `size`, `target` or labels containing "numeric" as numeric; `lat`, `lon`, `lat2`, `lon2` count as text roles.
  - `ReportBuilder.tsx:2758-2762` `isNumericField` returns false for a coordinate column (`nonAdditiveKind` = 'coordinate'). So origin_lat counts as a "text" field and goes to the first empty non-numeric role, Country. from_city (text) also fits lat/lon, which are "non-numeric" by this rule.
  - The Assign-data picker narrows lat/lon to numeric via `roleAccepts` (`types/report.ts:295-307`), but it does not check the range or geography semantics.
- **Fix:**
  1. `fieldPlacement.isNumericRole`: return `roleAccepts(rf.role) === 'numeric'`, one rule shared with the picker.
  2. Pass a field *use* (`fieldUse`: measure/category/date/geo) to `roleForField` instead of a boolean. A `geo` field whose name or `geo_level` says latitude goes to `lat` (then `lat2`), a longitude to `lon` (then `lon2`), and a country goes to the `category` role labelled Country. Text never goes into a numeric role.
  3. Map role pickers (`WidgetConfigPanel.roleChoices`, ~line 1310): for lat/lon, list Geography fields first under a "Geography" group. Mark numeric columns whose observed min/max (from `analysis.numeric`) fall outside ±90/±180 with "(values out of range)", or hide them unless "Show all" is ticked. Show an inline warning when an out-of-range field is chosen.
  4. Country role: refuse numeric columns (`roleAccepts('category')` stays `any` for other charts, but map `category` roles become text-only).
- **Tests:** automated: `frontend/src/lib/fieldPlacement.test.ts`: on `ROLE_SPECS.map_points`, a click on origin_lat lands in `lat`, origin_lon in `lon`, from_city in `category`, and shipments in `measure`; a text field is never placed into `lat`/`lon`. `WidgetConfigPanel.test.tsx`: the Longitude picker lists `origin_lon` under Geography and flags `shipments`. Manual: on Demo — Routes, select a Point Map and click origin_lat, origin_lon, shipments. The map should show 10 dots at the cities.
- **Effort:** M
- **Depends on / related:** C-10, C-27, C-28

### C-10 — Make a map's lat/lon or country mode explicit, show a placeholder when it is unassigned, and hide the country-match note in lat/lon mode
- **Severity:** High
- **Evidence:** #31, #32 · C4-05..11 (single dot over SE Asia, "9 rows did not match a country"), C4-15 ("300 rows did not match a country" on unassigned Bubble Map); area table C4-C
- **Problem:** With lat/lon assigned, the Point Map showed a single dot zoomed in, plus "9 rows did not match a country" even though Country was meant to be empty. An unassigned Point or Bubble map shows "300 rows did not match a country" instead of an "assign data" state.
- **Root cause / where:** (confirmed by code. The Aggregation=Sum hypothesis from the notes is NOT the cause: `shape_geo_points` groups by exact coordinates.)
  - `backend/app/services/widget_data.py:2787-2789` `shape_geo_points` uses lat/lon mode only when both resolve to existing columns. Otherwise it falls back silently to `shape_series` grouped by `category`. In C4-11 the leftover Country=`from_city` (from the C-09 mis-assignment) and an incomplete or invalid lon put the map into country mode. 10 city names were matched as countries, 9 failed, and "Singapore" matched as a country, giving one dot in SE Asia.
  - With no roles at all, `shape_series` returns the raw table. `GeoPointMapRenderer.tsx:73-91` counts every raw row as "unmatched" and shows `pg.modelsMaps.map.noCountry` (`:307-310`).
  - `ROLE_SPECS.map_points`/`map_bubbles` (`types/report.ts`) mark every role optional, and `missingWidgetOptions` (`WidgetPlaceholder.tsx:64`) has no map_points/map_bubbles rule, so no placeholder is drawn.
- **Fix:**
  1. `missingWidgetOptions`: for `map_points` and `map_bubbles`, return `['Country or Latitude/Longitude']` unless `category` or both `lat` and `lon` are set, the same rule as for `map_layers`. When only one of lat/lon is set, return the missing one.
  2. Backend `shape_geo_points`: if exactly one of lat/lon is set, or a set coordinate is not numeric, return `{"type":"error","code":"incomplete_coordinates", ...}` instead of falling back to country mode. When both lat/lon are valid, ignore `category` for placement (keep it as the label).
  3. `GeoPointMapRenderer`: show the unmatched-country note only when `!coordinateMode && data.type !== 'table'`. Change its text to name the column ("9 values of from_city are not country names").
  4. In the config panel, show a one-line mode hint ("Placing by coordinates" or "Placing by country").
- **Tests:** automated: `backend/tests/test_shape_geo.py`: lat set and lon missing gives an `incomplete_coordinates` error. lat+lon+category gives coordinate rows (10 locations for the routes fixture). `frontend/src/components/report/chartRenderers/geoUnmatchedAndDensity.test.tsx`: coordinate rows never show `geo-unmatched`. A raw-table payload shows the placeholder. `WidgetPlaceholder.test.tsx`: an empty map_points needs "Country or Latitude/Longitude". Manual: add a Point Map on Demo — Routes. It should show the placeholder first, then 10 dots once lat/lon are set, with no country note.
- **Effort:** M
- **Depends on / related:** C-09

### C-11 — Default percentages and ratios to Average, never Sum, on every role and every aggregation path
- **Severity:** Medium
- **Evidence:** #10, #24 · C-31/32 (Bar + line: margin_pct summed, 0-12000%), C3-10 (Dual axis line 2600%); area table C-32, C3-3
- **Problem:** Putting `margin_pct` on a second axis sums it, giving an axis up to 2,600% or 12,000% and a legend of "sum(margin_pct)".
- **Root cause / where:** (confirmed)
  - `frontend/src/lib/semanticGuard.ts:145 defaultSummary('margin_pct')` already returns `avg`, but it is applied only on the Fields-panel click/drag path (`ReportBuilder.tsx:2356-2376`), and even there only when the aggregation was `count` or blank.
  - The Assign-data dialog path (`WidgetConfigPanel.tsx:1191 setFields → setRole`) never sets an aggregation. Panel state defaults to `agg = cfg.aggregation ?? 'sum'` (`:241`), and `agg2` blank falls back to `agg` (`:744`; backend `widget_data.py:2008 agg2 = aggregation2 or agg`). So a second measure always inherits the first measure's Sum.
- **Fix:**
  1. `WidgetConfigPanel.setFields`: when `measure` (or `measure2`) is set and the author has not changed `agg` (or `agg2`) by hand, set it to `defaultSummary(col, columnMeta)`. This needs `columnMeta` passed as a prop from `ReportBuilder`.
  2. `ReportBuilder.planFieldOnWidget` (`:2369-2376`): always apply `sensible` to `aggregation2` for `measure2`, independent of the first aggregation.
  3. Backend safety net in `shape_dual_series`: when `aggregation2` is absent, use `semantic_guard.default_summary(meas2, column_meta)` instead of `agg`. Do the same for `aggregation` when it is absent.
  4. Axis/legend: show "Average margin_pct" (`seriesName`) instead of the raw "sum(margin_pct)".
- **Tests:** automated: `frontend/src/components/report/WidgetConfigPanel.test.tsx`: in a dual_axis_line, assigning revenue then margin_pct through Assign data saves `aggregation:'sum'` and `aggregation2:'avg'`. `backend/tests/test_semantic_guard.py`/`test_widget_data_measures.py`: `shape_dual_series` with no `aggregation2` averages margin_pct. Manual: Dual axis line month × revenue | margin_pct. The right axis should stay below 100%.
- **Effort:** S
- **Depends on / related:** C-02

### C-12 — Keep the hover toolbars inside their own tile, in View and Edit
- **Severity:** Medium
- **Evidence:** #16, #36 · C-58 (hover bars cover the tile title below / "Revenue against target"), C-54 (covers "Total units (tab)"), C4-15 (click meant for the canvas hit Duplicate → "Point Map (copy)"); area table C4-D
- **Problem:** The floating toolbars (AI / focus / image in View; grip / duplicate / data / filter in Edit) stick out above the tile edge and cover neighbouring titles. A click on what looks like empty canvas lands on "Duplicate" and silently creates a copy.
- **Root cause / where:** (confirmed) `frontend/src/pages/reportBuilder/viewMode.css:7` `.dl-vw-wt { position:absolute; top:-18px; left:50%; … }` and `builder.css:249` `.dl-bd-wt { top:-22px; … }`. Both are placed outside the tile box, in the inter-tile gap and over the tile above or below. `pointer-events:auto` is set on hover. `duplicateWidget` (`ReportBuilder.tsx:1973`) pushes an undo entry, but the toast has no Undo action.
- **Fix:**
  1. Move both toolbars inside the tile header: `top: 6px; right: 8px; left:auto; transform:none` (`inset-inline-end` for RTL). Reserve header padding (`padding-inline-end: <toolbar width>` on hover/focus) so titles truncate instead of being covered.
  2. Only enable `pointer-events` after a 150 ms hover delay, so that passing the pointer over a tile does not arm the buttons.
  3. Show the "Duplicated" toast with an Undo action that calls `undoStack.undo()`.
- **Tests:** automated: `frontend/src/pages/ReportBuilder.test.tsx`: the Duplicate toast offers Undo and calling it removes the copy. A CSS snapshot or computed-style check in `frontend/src/pages/reportBuilder/viewMode.test.tsx` (new) asserts `.dl-vw-wt` `top` ≥ 0. Manual: on Demo — Sales Overview, hover each tile. No toolbar should overlap another tile's title.
- **Effort:** S
- **Depends on / related:** C-04

### C-13 — Fit KPI, card and gauge numbers inside their tiles
- **Severity:** Medium
- **Evidence:** #15 · C-58 ("Revenue, cost and units" third value cut; "Revenue against target" gauge value cut at the bottom), C-33/34 ("$" wrapped onto its own line)
- **Problem:** Multi-row cards cut off their last value, and the gauge value "$ 8,632,597" wraps and is clipped at the bottom of the tile.
- **Root cause / where:** (confirmed)
  - `frontend/src/components/report/chartRenderers/GaugeRenderer.tsx:~126-129`: the value is an absolutely positioned `div` at `top:55%`, `translate(-50%,-20%)`, `fontSize:22`, with no `whiteSpace:nowrap` and no width-aware sizing, so it wraps and overflows.
  - Card (`WidgetBody.tsx:568-585`) sizes each figure by width only (`fitFigureSize`, which uses `100cqi`). Three rows at 24 px plus labels overflow a short tile, which only scrolls inside, so it looks clipped.
- **Fix:**
  1. Gauge: put the value inside the arc's inner box with `whiteSpace:'nowrap'` and `fontSize: fitFigureSize(text, 22)` (`containerType:'inline-size'` on the wrapper). Clamp the position to `bottom: 4px`.
  2. Card: use container *block* units too, `min(fit-by-width, calc(100cqb / (rows * 2.2)))`, so N rows always fit the tile height. Fall back to a horizontal layout when the tile is wider than it is tall.
- **Tests:** automated: `frontend/src/components/report/chartRenderers/gaugeShapes.test.tsx`: the value element has `white-space: nowrap` and a font-size expression that uses `cqi`. `frontend/src/components/report/WidgetRenderer.test.tsx` (card): with 3 rows, the font-size style contains `cqb`. Manual: Demo — Sales Overview at 1440×900. All three card values and the gauge value should be fully visible.
- **Effort:** S
- **Depends on / related:** C-02

### C-14 — Show the "Needs Dimension" placeholder for a pie (or any category chart) given only a measure
- **Severity:** Medium
- **Evidence:** #4 · C-14/15 (first pie version)
- **Problem:** A Pie with a measure and no dimension renders as one solid disc with a stray radius line.
- **Root cause / where:** (confirmed) With a measure and no dimension, `shape_series` returns `{"type":"scalar","rows":[{name:meas,value}]}` (`backend/app/services/widget_data.py:1658-1690`). In `WidgetBody.tsx:322-333`, a placeholder is drawn only if `nothingToDraw || rawTableForChart`, and a scalar has one drawable row. The pie then draws a single 100% slice.
- **Fix:**
  1. In `WidgetBody.tsx`, treat `data?.type === 'scalar'` as unfinished when `missing.length` and `familyOf(wt) !== 'kpi'`, i.e. extend `rawTableForChart` to `wrongShapeForChart = (data.type === 'table' || data.type === 'scalar') && familyOf(wt) not in ['table','kpi']`.
- **Tests:** automated: `frontend/src/components/report/WidgetPlaceholder.test.tsx` or `WidgetRenderer.test.tsx`: a pie with `{measure:'revenue'}` and a scalar payload renders the "Needs Dimension" placeholder. Manual: add a Pie and assign only revenue. The placeholder should be shown.
- **Effort:** S
- **Depends on / related:** C-03 (same drawable check)

### C-15 — Label sunburst segments and colour them by top-level branch
- **Severity:** Medium
- **Evidence:** #8 · C-26
- **Problem:** The region → category sunburst has no segment labels, and every ring is the same blue, so it cannot be read without hovering.
- **Root cause / where:** (confirmed) `frontend/src/components/report/chartRenderers/HierarchyRenderer.tsx:232-293` `Sunburst`. Every `<path>` gets `fill={seriesColor(0)}` with only an opacity step per depth, and there is no `<text>`; the name lives only in `<title>`. The size is a fixed 260 px.
- **Fix:**
  1. Colour each depth-1 branch with `seriesColor(i)` and pass that colour down to its descendants, lightened per depth.
  2. Add a centred `<text>` per segment when its arc length (`(a1-a0)*midRadius`) is at least the label width estimate. Rotate it along the radius, and hide it otherwise (the `<title>` stays).
  3. Size the SVG from `plotW/plotH` instead of a fixed 260.
- **Tests:** automated: `frontend/src/components/report/chartRenderers/HierarchyRenderer.test.tsx`: a 4-region tree renders at least 4 distinct fills and a `<text>` for each wide segment. Manual: Sunburst region → category should show readable labels in distinct colours.
- **Effort:** S
- **Depends on / related:** C-08

### C-16 — Make box-plot category labels readable
- **Severity:** Medium
- **Evidence:** #9 · C-27, C-59 (Distributions demo)
- **Problem:** Box-plot x-axis category labels are about 4 px glyphs and cannot be read.
- **Root cause / where:** (confirmed) `frontend/src/components/report/chartRenderers/BoxPlotRenderer.tsx:55` draws into `viewBox="0 0 1000 400"` with `preserveAspectRatio="none"`. The category `<text fontSize={10}>` (`:79`) is scaled non-uniformly with the SVG, so it is squashed to a few pixels. The y ticks were already moved to an HTML gutter for this exact reason (comment at `:8-11`), but the x labels were not.
- **Fix:**
  1. Render the category labels in an HTML strip under the SVG (absolutely positioned at `(slot centre / W) * 100%`, ellipsis, `title` = full name), as the y-tick gutter does. Rotate or thin them when `slotW` is less than the label width.
- **Tests:** automated: `frontend/src/components/report/chartRenderers/BoxPlotRenderer.test.tsx`: category names are rendered as HTML elements (not SVG `<text>`) with font-size ≥ 10 px. Manual: box plot revenue by region should show four legible region names.
- **Effort:** S
- **Depends on / related:** —

### C-17 — Stop the false "changed in another session" banner after my own classification or comment
- **Severity:** Medium
- **Evidence:** #18 · C-84..87 (also seen in QA MAP-04 notes)
- **Problem:** Right after classifying the report (and after posting a comment), a yellow banner says "This report was changed in another session. Reload to see those edits", although only this session made changes.
- **Root cause / where:** (confirmed for classification) `frontend/src/pages/ReportBuilder.tsx:3640-3652`. The classification `onChange` calls `reportsApi.setClassification`, which bumps the revision (`backend/app/routers/reports.py:516 _bump_revision`). It then calls `setReport(updated)` but never updates `loadedRevision`. The poll at `:706-727` then sees `remote > known` and raises the banner. `syncRevisionAfterOwnWrite` (`:1116`) exists but is not called here. Comments (`reports.py:2714-2741`) do not bump the revision, so the comment case is probably the same classification write, or another write that does not sync (unconfirmed). The same handler also reads `e.target.value` after an `await` to choose its toast. That is the likely cause of C-83 "Classification cleared" being shown on Confidential.
- **Fix:**
  1. After `setReport(updated)`, call `setLoadedRevision(updated.revision ?? await reportsApi.getRevision(reportId))`.
  2. Generalise: route every own-session write that bypasses `loadReport` through one `afterOwnWrite()` that updates `loadedRevision`. Grep for `reportsApi.` calls not followed by `loadReport`/`syncRevisionAfterOwnWrite`.
  3. Use the captured `next` (not `e.target.value`) for the toast.
- **Tests:** automated: `frontend/src/pages/ReportBuilder.test.tsx`: mock `setClassification` to return `revision: 5` and `getRevision` to return 5. Change the select, advance timers by 20 s, and assert there is no stale banner and the toast reads "Classified Confidential". Manual: classify and comment, then wait 30 s. There should be no banner.
- **Effort:** S
- **Depends on / related:** —

### C-18 — Stop the Suggest pane counting distinct years as if they were identifiers
- **Severity:** Medium
- **Evidence:** #19 · C-90 ("Asia Pacific leads distinct year with 2")
- **Problem:** Deterministic suggestions read "Asia Pacific leads distinct year with 2", which means nothing.
- **Root cause / where:** (confirmed) `frontend/src/components/report/SuggestionsPane.tsx:48` picks `idCol = visible.find(c => isIdentifier(c.name, meta))`. The server classifies `year` as number kind `code` (`backend/app/services/column_classes.py:198`). `semanticGuard.nonAdditiveKind` maps a recorded `code` to `'identifier'` (`lib/semanticGuard.ts:74`), so `isIdentifier('year')` is true. `countCfg` then builds `countd(year)` head-counts (`:85-88`), and `suggestionTakeaway.ts:84,143` words it as "leads distinct year".
- **Fix:**
  1. In `isIdentifier`, exclude columns whose name-based kind is `year` (`WORD(column, year words)`), or only treat a recorded `code` as an identifier when its name matches `ID_NAME` or its role is `identifier`.
  2. In `SuggestionsPane`, only use `idCol` for head-counts when its distinct count is close to the row count (>50% unique). Otherwise count rows.
- **Tests:** automated: `frontend/src/components/report/SuggestionsPane.test.tsx`: given columns region, revenue, year (meta `{year:{number:'code'}}`), no suggestion config has `aggregation:'countd'` on `year`. `frontend/src/lib/semanticGuard.test.ts`: `isIdentifier('year', {year:{number:'code'}})` is false. Manual: open the Suggest pane on Demo — Sales. Head-counts should say "rows", not "distinct year".
- **Effort:** S
- **Depends on / related:** C-11

### C-19 — Make widget resize reliable, with no page text selected during the drag
- **Severity:** Medium
- **Evidence:** #20 · C-91/92
- **Problem:** Dragging the resize handle barely resizes the widget, and the drag selects text across the page (the AI pane gets highlighted). The handle is hard to hit.
- **Root cause / where:** `frontend/src/components/report/WidgetRenderer.tsx:1784-1797`. The handle is an 18×18 px corner box, and `onMouseDown` and `onPointerDown` both call `onResizeStart`. The second start can reset the first, and `preventDefault` on pointerdown suppresses the compatibility `mousedown`. The move/up listeners are on `window` (`ReportBuilder.tsx:2608+`), but nothing sets `user-select:none` on the document during the drag, so text outside the tile gets selected. (unconfirmed: from code reading)
- **Fix:**
  1. Handle only `onPointerDown`, with pointer capture. Drop the duplicate `onMouseDown`.
  2. While `dragging || resizing`, set `document.body.style.userSelect = 'none'` and the cursor, and restore them in cleanup.
  3. Enlarge the hit area to 24×24 px. Show the handle only on hover/selection, and add edge handles (right and bottom).
- **Tests:** automated: `frontend/src/pages/ReportBuilder.test.tsx`: pointerdown on `widget-resize-handle`, pointermove +200 px, pointerup. Assert `updateWidget` is called once with a larger `layout.w`, and `document.body.style.userSelect` is `'none'` during the drag and `''` after. Manual: resize a bar chart by dragging. It should resize smoothly with no text highlighted.
- **Effort:** S
- **Depends on / related:** C-12

### C-20 — Add "Duplicate" (Save as copy) to the dashboard card menu
- **Severity:** Medium
- **Evidence:** #1, #21 · C-02/03, C-97..100; area table C-03
- **Problem:** The card ⋯ menu has Open / Edit / Copy link / Move / Rename / Export / Delete but no way to copy a dashboard.
- **Root cause / where:** (confirmed: missing feature) `frontend/src/pages/reports/DashCard.tsx:13` and `pages/Reports.tsx:44-50` say Duplicate was left out because "the backend has no data for them". `backend/app/routers/reports.py` has no copy endpoint. The page/widget cloning logic already exists in `restore_version` (`:1240`, `_remap_restored_refs` `:1110`) and `create_report` (`:288`).
- **Fix:**
  1. Backend: add `POST /reports/{id}/duplicate` (`{name?, folder_id?}`). It requires read access, creates a new Report owned by the caller (`created_by`, unpublished, no grants or share links), copies datasets/theme/style/display_rules/parameters/common filters, clones pages and widgets, and remaps `container_id`, drillthrough, tooltip page and bookmark references with the `_remap_restored_refs` logic. Audit it as `report.duplicate`.
  2. Frontend: add `reportsApi.duplicate`, and a "Duplicate" item in the card menu (`Reports.tsx` menu items near `:316`). Name the copy "<name> (copy)", file it in the same folder, and open it in Edit.
- **Tests:** automated: new `backend/tests/test_report_duplicate.py`: the copy has new page and widget ids, `container_id` points at the copied container, the copy is owned by the caller and unpublished, and a viewer without read access gets 404. `frontend/src/pages/Reports.test.tsx`: the menu has Duplicate and clicking it calls the API and navigates. Manual: duplicate Demo — Sales Overview. The copy should be identical and editable.
- **Effort:** M
- **Depends on / related:** —

### C-21 — Add width × height inputs for a Custom page size
- **Severity:** Medium
- **Evidence:** #22 · C-103..109 (C-109), C-112..115 (C-113)
- **Problem:** Choosing "Custom" page size shows no width or height inputs, so the option does nothing.
- **Root cause / where:** (confirmed) `frontend/src/components/report/PagePropertiesPanel.tsx:263-268` renders only the `16:9 / 4:3 / custom` segmented buttons. `custom_width` exists in the model and schemas (`backend/app/models/models.py:278`, `schemas.py:459/477/497`) and `types/report.ts:43`, but no UI reads or writes it, and there is no `custom_height`.
- **Fix:**
  1. Backend: add a `custom_height` column (Alembic migration) plus the schema fields, validated to 320-10000 px.
  2. `PagePropertiesPanel`: when `pageSize === 'custom'`, show two number inputs (W, H) seeded from the page and saved with `page_size`.
  3. The canvas sizing in `ReportBuilder` (page frame) honours `custom_width/height` when `page_size==='custom'`.
- **Tests:** automated: `backend/tests/test_report_page_size.py`: PATCH a page with `page_size:'custom', custom_width:1600, custom_height:1200` round-trips, and out-of-range values give 422. `frontend/src/components/report/PagePropertiesPanel.test.tsx`: selecting Custom shows the inputs, and saving sends both values. Manual: set 1600×1200. The canvas frame should change size.
- **Effort:** M
- **Depends on / related:** —

### C-22 — Give dual-axis charts enough width when added or auto-laid-out
- **Severity:** Medium
- **Evidence:** #23 · C3-09 (also C3-11: adding a widget shrank Dual Axis Line to half width)
- **Problem:** A new Dual axis bar lands 4 columns wide. With two axes and two titles, the plot area collapses to about 30 px, and the bars and labels become an unreadable blob.
- **Root cause / where:** (confirmed) Pages are auto-packed by the "executive" recipe (`frontend/src/lib/dashboardLayout.ts:18 DEFAULT_RECIPE`, `shownLayouts :445-451`). `placeHeroAndSide` (`:152-166`) always gives the second chart `w:4`, and `clampLayout` only enforces `minSize`, which is `{w:4}` for every ordinary chart (`:50-56`). The catalog `defaultW: 6` (`types/report.ts:170-173`) is overridden by the recipe.
- **Fix:**
  1. Add dual-axis types (`DUAL_MEASURE_WIDGETS` minus butterfly), `small_multiples` and `forecast` to a `MIN_W_6` set in `minSize` (`w:6`).
  2. In `placeHeroAndSide`, if `minSize(side).w > 4`, do not place it in the side slot: put the hero full width and move the side chart to the next row (`placeRow` with 2 per row).
  3. Optional: in the axis planner (`axisOptions.ts`), hide the second axis title when `plotW < 260`.
- **Tests:** automated: `frontend/src/lib/dashboardLayout.test.ts`: `applyRecipe` with [bar, dual_axis_bar] never gives `dual_axis_bar` a width below 6 and produces no overlaps. Manual: add a Dual axis bar to a page that has one chart. It should be at least half width and readable.
- **Effort:** S
- **Depends on / related:** —

### C-23 — Make "Split into multiples by" a required data role for Small multiples
- **Severity:** Medium
- **Evidence:** #25 · C3-13/14; area table C3-5
- **Problem:** Out of the box, Small multiples shows a single "All" panel. The facet, which defines the chart, is set elsewhere (Data & aggregation → Facet by), and that list also offers measures.
- **Root cause / where:** (confirmed) `frontend/src/types/report.ts` `small_multiples: [category (req), measure]`. The comment above it states that `facet_by` is deliberately a widget option. Backend `widget_roles.py:112 "small_multiples": ("category",)`.
- **Fix:**
  1. Add a role `{ role: 'facet', label: 'Split into multiples by', required: true }` that maps to config key `facet_by` (`ROLE_TO_CONFIG_KEY`, and backend `_ROLE_CONFIG_KEY`, `_LEGACY_ROLE_KEYS`). Mark it text/date-only (a `CATEGORY_ROLES` set in `roleAccepts`) so measures are not offered.
  2. Add it to `REQUIRED_ROLES` in the backend and keep the parity test green. Existing widgets without `facet_by` show the "Needs Split into multiples by" placeholder instead of "All".
  3. Remove the duplicate Facet select from the Data & aggregation group, or keep it bound to the same key.
- **Tests:** automated: `backend/tests/test_widget_roles.py` (small_multiples requires facet_by), `frontend/src/components/report/chartRenderers/SmallMultiplesRenderer.test.tsx`/`WidgetPlaceholder.test.tsx` (missing facet shows the placeholder), and `WidgetConfigPanel.test.tsx` (the facet picker excludes numeric measures). Manual: add Small multiples. Assign data should ask for the split field, and choosing channel should draw 4 panels.
- **Effort:** S
- **Depends on / related:** —

### C-24 — Show the whole time range on a dual-axis time series by default
- **Severity:** Medium
- **Evidence:** #26 · C3-16; area table C3-2
- **Problem:** Dual axis time series with a daily date field shows only the first 50 of 633 dates ("Showing 50 of 633 date values"), roughly Jan 25 to Feb 24 2024. This is misleading.
- **Root cause / where:** (confirmed) `backend/app/services/widget_data.py:1989` `shape_dual_series`: `limit = config.limit or (FULL_DATA_LIMIT if dimension_granularity else 50)`. Without a granularity, a date axis is treated like a category and capped at 50.
- **Fix:**
  1. If the category column is date-like (`_is_date_like`) and no granularity is set, pick an automatic grain so that there are at most about 120 points (day → week → month), using the existing auto-grain helper in shape_series if present. Report it as `auto_granularity` in the result. Otherwise use `FULL_DATA_LIMIT`.
  2. Apply the same rule to `numeric_series` (500-row cap, C3-18) or at least disclose the cap.
  3. Frontend: show "by week (automatic)" in the truncation note and as the axis subtitle.
- **Tests:** automated: `backend/tests/test_widget_data_measures.py` or a new `test_dual_series_time.py`: 633 daily rows and no limit/granularity give at most 120 points that cover the first and last date, with `auto_granularity` set. Manual: Dual axis time series date × revenue | units should span 2024-01 to 2025-12.
- **Effort:** S
- **Depends on / related:** C-25

### C-25 — Decide how to present the negative revenue axis on daily time series
- **Severity:** Medium
- **Evidence:** #27 · C3-16 (left axis down to "$ -11,000")
- **Problem:** The left axis of Dual axis time series goes down to "$ -11,000". The tester read this as an artefact of the scale.
- **Root cause / where:** (likely genuine data, unconfirmed) The demo sales data deliberately contains about 3% refunds with negative revenue (`backend/app/services/demo_content.py:185-197`). With about 3 rows per day, a day whose only sale is a refund sums negative. The recharts domain is `'auto'` (`chartRenderers/axisOptions.ts:833-839`), and the lines use `type="monotone"` (`DualAxisTimeSeriesRenderer.tsx:48`), which can also overshoot slightly between points.
- **Decision needed:** Probably not a code bug: the negative values are real data. Decide whether the chart should explain them.
- **Fix:**
  1. (If accepted) Draw a zero reference line when the domain crosses 0, and use `type="linear"` for daily series so the curve never overshoots below the data.
  2. After C-24, daily data is auto-bucketed to weeks or months, which removes most negative buckets.
- **Tests:** automated: `frontend/src/components/report/chartRenderers/dualAxisSecondSeries.test.tsx`: with a negative value, a `ReferenceLine y=0` is rendered. Manual: check the chart against the data table for that day.
- **Effort:** S
- **Depends on / related:** C-24

### C-26 — Use one picker interaction everywhere: apply the choice on click in multi-field roles
- **Severity:** Medium
- **Evidence:** #29 · C3-20 (Matrix/List/Crosstab pickers); area table C3-6
- **Problem:** Multi-field role pickers (Matrix, Crosstab, List, Card, hierarchy levels) are checklists that need a separate "Add" click. Single roles apply on click. Ticking a field appears to do nothing.
- **Root cause / where:** (confirmed) `frontend/src/components/report/DataRolesList.tsx:216-297` `AddFieldDialog`. In `multi` mode, `toggle()` only updates local `picked`, and `onApply` runs only from the footer "Add" button (`:290-295`).
- **Fix:**
  1. In multi mode, apply each toggle immediately (`onApply(next)` inside `toggle`) and keep the dialog open. Turn the footer button into "Done", and keep the order badges.
  2. Alternatively: the first click on an empty multi role applies and closes, as for a single role; "+ Add" on the role again adds the next field. Pick one and use it across the app.
- **Tests:** automated: `frontend/src/components/report/DataRolesList.test.tsx`: in multi mode, clicking a checkbox calls `onApply` with that field without pressing a footer button. Manual: Matrix → Rows → tick region. The role should fill at once.
- **Effort:** S
- **Depends on / related:** C-28

### C-27 — Accept a field dropped onto a role in the Properties panel
- **Severity:** Medium
- **Evidence:** #33 · C4-05..11 (C4-09)
- **Problem:** Dragging a field from the Fields panel onto a role name in Properties is ignored. Drag works only onto the canvas tile.
- **Root cause / where:** (confirmed) `frontend/src/components/report/DataRolesList.tsx` role rows have no `onDragOver`/`onDrop`. The drag source sets `application/x-field` (`pages/ReportBuilder.tsx:3194-3196`), and only the canvas handles it (`:4081-4100`).
- **Fix:**
  1. Add `onDragOver` (accept `application/x-field` when `roleAccepts(role)` fits the field's use) and `onDrop` to each role row in `DataRolesList`. Call a new `onDropField(role, column)` prop, which `WidgetConfigPanel` routes to `setFields`. Highlight a role that can take the field and show a not-allowed cursor on one that cannot.
- **Tests:** automated: `frontend/src/components/report/DataRolesList.test.tsx`: `fireEvent.drop` on the Latitude row with `dataTransfer` `application/x-field=origin_lat` calls `onDropField('lat','origin_lat')`, and dropping a text field on Latitude is rejected. Manual: drag origin_lon onto "Longitude" in Properties.
- **Effort:** S
- **Depends on / related:** C-09

### C-28 — Let the field picker take the single match on Enter, and give each option a distinct accessible name
- **Severity:** Medium
- **Evidence:** #35 · C4-12/13; area table C4-E
- **Problem:** In the Assign-data picker, typing in "Search fields" and pressing Enter does nothing; the user has to Tab and then press Enter. Picker items have the same accessible name as the matching field in the left Fields panel, which makes them ambiguous for assistive tech and test drivers.
- **Root cause / where:** (confirmed) `frontend/src/components/report/DataRolesList.tsx:252-253`: the search `<input>` has no `onKeyDown`. The option buttons (`:278-284`) use only `{c.label}` as their name.
- **Fix:**
  1. On Enter in the search box: when `shown.length === 1`, `choose()` it (single) or toggle it (multi). Up/Down arrows move a roving active option (`aria-activedescendant`).
  2. Set `aria-label={t('bc.canvas.useFieldFor', { field: c.label, role: shownHeading })}` ("Use origin_lat for Latitude") on each option.
- **Tests:** automated: `frontend/src/components/report/DataRolesList.test.tsx`: type "origin_lat" and press Enter, and `onApply(['origin_lat'])` is called. The option's accessible name contains the role. Manual: keyboard-only, assign Latitude.
- **Effort:** S
- **Depends on / related:** C-26

### C-29 — Show one readable count per bubble on the World Sales Map "Origin density" tile (QA MAP-02)
- **Severity:** Medium
- **Evidence:** QA MAP-02 (journey_main_clean/QA/REPORT.md:83, shots MAP-02, MAP-02-zoom); HEADER item 24
- **Problem:** Each origin city shows two concentric bubbles with two overlapping numbers (e.g. "34" over "37", "1" over "31"), so the counts are hard to read.
- **Root cause / where:** (confirmed from the data plus the code) The demo jitters each origin by N(0, 0.8°) (`backend/app/services/demo_content.py:321-322`), and the tile seeds `cluster_cell_degrees: 10` (`:915-918`). `shape_geo_clusters` (`backend/app/services/widget_data.py:2879-2925`) snaps points with `round(lat/cell)*cell`. Cities that sit near a 5° boundary (Tokyo 35.7, Dubai 55.3, LA 34.05, …) are split into two cells, and both cells' mean positions fall on the same city. `GeoClustersRenderer` (`frontend/src/components/report/chartRenderers/GeoLineClusterRenderer.tsx:94-140`) draws each cell as a circle with its count text and no collision handling. The smaller cluster is drawn on top, so its bold label overlays the big one's faded label.
- **Fix:**
  1. Renderer: after projecting, merge markers whose circles overlap (greedy, largest first: when the distance is less than `r1 + r2`, merge counts and values and take the weighted centroid) before drawing. This is screen-space clustering and works at any zoom level.
  2. Draw only one label per merged marker. Hide a label whose box overlaps an already-drawn label (the same idea as `lib/chartDeclutter.ts`).
  3. Optionally, server side: when the grid splits points that lie within `cell/4` of each other across a boundary, merge adjacent cells (or use the `round(x/cell - 0.5)` floor grid with an offset chosen to minimise splits).
- **Tests:** automated: `frontend/src/components/report/chartRenderers/geoRenderers.test.tsx`: two cluster rows at (35.3, 139.7, count 3) and (35.9, 139.7, count 27) render one `[data-cluster]` with label "30". `backend/tests/test_network_and_geo_shapes.py`: the routes fixture with cell 10 gives one cluster per city once merging is enabled. Manual: World Sales Map → Origin density should show exactly 10 bubbles with one number each.
- **Effort:** S
- **Depends on / related:** C-03

### C-30 — Decide whether "Create a dashboard" may proceed with an empty name (QA DASH-04)
- **Severity:** Medium
- **Evidence:** QA DASH-04 (journey_main_clean/QA/REPORT.md:71, 104-112; shots DASH-04a, DASH-04); HEADER item 24
- **Problem:** With the name left empty, Create is enabled and makes "Untitled dashboard" with no name-required message. The QA plan (`qa/TEST_PLAN.md` DASH-04) expects Create to be disabled or a "name required" message.
- **Root cause / where:** This is intended behaviour, not a bug: `frontend/src/pages/reports/dialogs.tsx:80` sets `blocked` only for AI/template mode, and `pages/Reports.tsx:151` uses `c.name || nextUntitledName(...)`. `pages/Reports.test.tsx:581-589` asserts the auto-naming ("Blank with no data … auto-named"), and `ReportBuilder.tsx:1801-1810` removes such a dashboard if it is left empty. The product rule and the QA plan disagree.
- **Decision needed:** The product auto-names on purpose; the QA plan expects a required name. Pick one and update the other.
- **Fix:**
  1. Option A, require a name: `blocked ||= mode !== 'ai' && !name.trim()`. Prefill the input with `placeholderName` (selected, so typing replaces it) so the user can still accept the default with one click. Show "Give the dashboard a name" under the field. Update `Reports.test.tsx` accordingly.
  2. Option B, keep auto-naming: change the QA plan's DASH-04 expectation to "an empty name creates 'Untitled dashboard N', which is removed if left empty". Show the placeholder name in the Create button tooltip.
- **Tests:** automated: `frontend/src/pages/Reports.test.tsx`: for Option A, the Create button is disabled while the name is empty and enabled after typing. Manual: New dashboard → empty name → Create, then check the behaviour matches the chosen rule.
- **Effort:** S
- **Depends on / related:** C-05

Coverage: worklist items 1..36 all mapped. Merged: #1+#21 (C-20), #10+#24 (C-11), #11+#28+#14-part (C-02), #12+#17 (C-01), #13+#14 (C-03), #16+#36 (C-12), #30+#34 (C-09), #31+#32 (C-10). Decision needed: #27 (C-25, negative values are probably real refund data) and QA DASH-04 (C-30, auto-naming is deliberate). Extra QA items: MAP-02 → C-29, DASH-04 → C-30, seeded demos → C-03.


## Shell, Ask AI, Insights, automations & monitoring

### AD-01 — Add one shared model health gate and a per-step AI timeout (fail fast when the model is down)
- **Severity:** High
- **Evidence:** #7, #17 · D-07, D-58; EVALUATION §2 #15 (F-14, D-58, D-07, B2) and Cross-cutting theme 1. Other groups should reference this task for Suggest dashboards (F-14), data-check / AI description waits (B2) and any other "spins for minutes" item.
- **Problem:** When the model server can't be reached, the header already shows a red light, but AI features still wait minutes before they give up. Suggest dashboards waits more than 2 minutes, an automation step more than 8 minutes, and an Ask AI suggestion more than 70 seconds. Describe/entities steps took about 9 minutes and were then reported as "ok".
- **Root cause / where:**
  - `backend/app/services/llm.py:218` `LLMClient.__init__` (default `timeout=180.0`) and `llm.py:371-372` `_post`: the code passes `httpx.AsyncClient(timeout=self.timeout)`, a single float. That makes the **connect** timeout 180 s too, so an unreachable host costs 3 minutes for each attempt, endpoint and retry (`core/config.py:103` `llm_timeout_s = 180`). Confirmed.
  - `llm.py:351` `_post` always makes the HTTP call. It never checks the health that `services/llm_endpoints.py:238` `is_up()` / `:420` `probe_all()` already keep up to date every 30 s (`PROBE_SECONDS`). `llm_endpoints.py:255` `candidates()` deliberately keeps down endpoints as a "last resort", so a known-dead endpoint is still dialled. Confirmed.
  - Nothing puts a time limit on whole AI steps: `services/automation_runner.py:1850` `output_ref = await spec.run(ctx, session)` has no `wait_for`, and `suggest_dataset_dashboard.py:1188` makes 2 attempts in a loop. Confirmed.
  - Frontend: `pages/ask/useAiOffline.ts:13` is the only offline signal, and only Composer, Retry, Home and Copilot use it. Suggestion cards, Suggest dashboards, automation Start and AI-description buttons ignore it. Confirmed.
- **Fix:**
  1. `llm.py:372`: build `httpx.Timeout(self.timeout, connect=settings.llm_connect_timeout_s)` and add a new setting `llm_connect_timeout_s: float = 5.0` in `core/config.py` (also exposed in `services/app_settings.py`).
  2. `llm_endpoints.py`: add `known_down(endpoint_id, fresh_s=2*PROBE_SECONDS) -> bool` and `model_available(choice=None) -> tuple[bool, str | None]`. An endpoint counts as unavailable only when it is marked down **and** the check is recent. "Never checked" counts as available.
  3. `llm.py:_post`: before the loop, drop targets that are `known_down`. If none are left, set `self.last_error = MODEL_UNREACHABLE` (a new constant next to `BUDGET_SPENT`/`AI_NOT_ALLOWED`) and `return None` without sending a request. Every existing caller already treats `None` as "no model" and falls back (for example `agent/graph.py:311-327` → `without_model`), so they all fail fast at once.
  4. New `services/ai_deadline.py`: `async def ai_step(coro, *, seconds, what)` wraps `asyncio.wait_for` and raises `AiStepTimeout(f"{what} did not finish in {n} min")`. Use it in the automation runner (AD-03), in `routers/datasets.py:2403` `suggest-dashboards`, and in the data-check / describe paths owned by group B.
  5. `routers/llm.py:15` `GET /llm/endpoints`: add `ai_available: bool` (from `model_available()`). Frontend `useAiOffline` keeps reading the same broadcast.
  6. Frontend: add `useAiGate()` in `pages/ask/useAiOffline.ts`, returning `{ offline, reason }`. Every AI trigger button gets `disabled={offline}` with the reason as its title, or else goes straight to its no-AI path. Track the call sites (ChatPane suggestion cards in AD-02, Suggest dashboards with AI, automation Start, AI descriptions) as a checklist in this task.
  7. Steps that ran with no model must say so: when `client.last_error == MODEL_UNREACHABLE`, write "skipped — AI unavailable" rather than "ok" (group B's describe/entities steps use the same constant).
- **Tests:** automated:
  - `backend/tests/test_llm_client.py`: the client's `Timeout.connect == settings.llm_connect_timeout_s`. A client whose only endpoint was `mark(..., False)` a moment ago returns `None` with **zero** MockTransport calls and `last_error == MODEL_UNREACHABLE`. A stale down mark (older than the freshness window) still calls out.
  - `backend/tests/test_llm_endpoints.py`: `model_available` truth table (fresh down → False, stale → True, never checked → True, Auto with one up → True).
  - `frontend/src/pages/ask/askStates.test.tsx`: `useAiGate` reports offline from a broadcast endpoints payload.
  - Manual: point the default endpoint at an unroutable IP, wait for the red light, then click Suggest dashboards, an Ask suggestion and Start automated analysis. Each should refuse or fall back in under 2 s.
- **Effort:** L
- **Depends on / related:** AD-02, AD-03; group F (F-14 Suggest dashboards), group B (B2 data checks / AI descriptions)

### AD-02 — Make Ask AI suggestion cards respect "new questions are paused"
- **Severity:** High
- **Evidence:** #6, #7, #8 · D-06, D-07/08
- **Problem:** The composer is locked while the model is unreachable, but the six suggestion cards still look enabled, send a question, and spin for 70 s or more. After 20 s the wait text says "the query is being checked against your database", even though no query was ever written.
- **Root cause / where:**
  - `frontend/src/components/chat/ChatPane.tsx:514` passes `startView(q => void send(q), busy)`. `busy` doesn't include `offline` (computed at `:181`), so `pages/ask/SuggestionGrid.tsx` `disabled={disabled}` stays false. The chip lists at `:519` and `:580` use `disabled={busy}` and also ignore offline. `send()` at `:288` has no offline guard. Confirmed.
  - `components/chat/Pending.tsx:92-95` / `:127-128` show `t('pend.slow')` after `UNUSUAL_AFTER_S = 20` (`:27`), whatever stage the request is in. The text is in `i18n/en.ts:3447` / `ar.ts:3446`. Confirmed.
- **Fix:**
  1. `ChatPane.tsx:514`: `startView(q => void send(q), busy || offline)`. Change `:519` and `:580` to `disabled={busy || offline}`.
  2. `SuggestionGrid.tsx`: accept `disabledReason?: string` and set it as the cards' `title`/`aria-describedby` (reuse `t('off.composer')`), so the paused state is explained where the user clicks.
  3. `send()`: return early when `offline && owned`. This guards Enter and any other entry point.
  4. Change `pend.slow` (en and ar) to neutral wording such as "Still working — this is taking longer than usual." Keep the database wording only for a stage the server reports (none today).
  5. With AD-01 in place, a click that slips through still gets the instant no-AI fallback (as DirectQuery datasets already do in 0.1 s).
- **Tests:** automated:
  - `frontend/src/components/chat/askCards.test.tsx`: with `useAiOffline` mocked offline, every `.dl-sug__card` is disabled and clicking one never calls `agentApi.ask`.
  - `frontend/src/components/chat/ChatPaneProgress.test.tsx`: after 21 s with fake timers, the slow note doesn't contain "database".
  - Manual: `/ask?dataset=1` with the model down. Cards are greyed with the "paused" tooltip.
- **Effort:** S
- **Depends on / related:** AD-01, AD-09

### AD-03 — Time out stuck automation steps, watch for stale "running" steps, and notify on failure
- **Severity:** High
- **Evidence:** #17, #19 · D-42..46/56..58, D-47
- **Problem:** A run sat on "Build the report → Running" for more than 12 minutes while the page promised "about 1 min". Nothing errors, nothing times out, and the bell never says the run is stuck, failed or was cancelled.
- **Root cause / where:**
  - `backend/app/services/automation_runner.py:1839-1850` `tick()` marks the step `running`, commits, then runs `await spec.run(ctx, session)` with no deadline.
  - `reap_stuck_automation_steps` (`:1919`) runs **only at startup** (`main.py:505`). While the process is alive, nothing ever ends a hung step.
  - `_fail` (`:1680`) records the failure but never calls `notify_run`. `describe_run` (`:563`) has no shape for failed or cancelled runs. Notifications come only from step 5's hold (`:1241`) and step 7 (`:1595`). The cancel endpoint (`routers/automation.py:180`) doesn't notify either.
  - All of the above is confirmed. **Why** compose hung is unconfirmed: `_compose_step` (`:1428`) makes no model call, so it was blocked on DB work or the loop stopped. The fix covers both cases.
  - Minor: `finished_at = now` is the tick **start** time, so the "Finished" column shows start times.
- **Fix:**
  1. Add a per-step budget, `STEP_TIMEOUT_S = {"profile": 600, "describe": 180, "scan": 600, "propose": 300, "review": 120, "compose": 180, "notify": 60}`. Wrap `:1850` in `ai_step(spec.run(ctx, session), seconds=…, what=<step label>)` from AD-01. On `AiStepTimeout`, follow the existing rollback path and `_fail` with "Build the report did not finish in 3 min".
  2. In `run_automation_loop` (`:1897`), every about 60 s call a new `reap_stale_running_steps(session, now)`. It fails steps whose `status == "running"` and `started_at < now - (budget + grace)`, using the same body as the startup reaper with an error like "Stopped responding". It covers a hung or crashed worker.
  3. `_fail`: when `step.attempts == 1` (first failure) or the step is out of retries, call `notify_run`. Give `describe_run` a failed shape ("Your automated analysis stopped at <step>: <error>. Open it to retry or cancel.", link `/automation?run=<id>`). `cancel_run`: notify the creator when the canceller is someone else.
  4. Set `finished_at = datetime.utcnow()` in `_succeed`/`_fail` rather than reusing the tick's `now`.
  5. Frontend `pages/Automations.tsx`: when the running step's `started_at` is older than `2 × estimateMinutes(rows)` (`:57`), show "Taking longer than usual" next to Cancel. Change `auto.estimate` (`i18n/en.ts:400`) to "…the bell tells you when it is ready, or if it stops".
- **Tests:** automated:
  - `backend/tests/test_automation_runner.py`:
    - `TestStepTimeout`: monkeypatch `STEP_TIMEOUT_S["compose"]=0.05` and a compose that `await asyncio.sleep(1)`. After one tick, the step is `failed`, the error mentions "did not finish", the run is `failed`, and one `Notification(kind="automation")` exists for the creator.
    - `TestPeriodicReaper`: a step `running` with an old `started_at` is failed by `reap_stale_running_steps`.
  - `backend/tests/test_automation_api.py`: cancelling someone else's run notifies its creator.
  - `frontend/src/pages/Automations.test.tsx`: an old running step shows the "longer than usual" note.
  - Manual: start a run with the model unreachable. Within about 5 min it reaches Failed with a reason, and the bell shows it.
- **Effort:** M
- **Depends on / related:** AD-01, AD-22

### AD-04 — Ignore stale scan responses on the Insights hub
- **Severity:** High
- **Evidence:** #12 · D-28..32
- **Problem:** Switch datasets quickly (Sales → Routes → Metrics) and the picker shows "Demo — Metrics" while the card shows the Sales findings, even 20 s later. The card doesn't name its dataset, so nothing reveals the mismatch.
- **Root cause / where:** `frontend/src/pages/InsightsHub.tsx:95-106` `runScan`: `insightsApi.runShared(selected).then(r => setScan(r))` has no request id or cleanup, so a slower earlier response overwrites the current one. `services/api.ts:2153` `runShared` shares one promise per dataset, so a late Sales promise always resolves eventually. Confirmed.
- **Fix:**
  1. Store the result together with its dataset: `setScan({ forId: selected, ...r })`. In the effect use `let alive = true; … .then(r => { if (alive) … }); return () => { alive = false }`, or a `seqRef` as in `DatasetDetail.tsx:313` `previewSeq`.
  2. Render the card only when `scan.forId === selected`.
  3. Put the dataset name in the card header ("Top insights · Demo — Metrics").
- **Tests:** automated: `frontend/src/pages/InsightsHub.test.tsx`. Mock `insightsApi.runShared` with deferred promises for datasets A and B. Select A, then B. Resolve B, then A. The card shows B's narrative and its heading names B. Manual: repeat D-30's quick-switch sequence.
- **Effort:** S
- **Depends on / related:** AD-06, AD-08

### AD-05 — Remove "Pin finding", which promises a dashboard that doesn't exist
- **Severity:** High
- **Evidence:** #15 · D-35..38
- **Problem:** The pin icon on findings toasts "Pinned to your dashboard", but pins appear nowhere (not on Home, My dashboards or Datasets) and can't be unpinned.
- **Root cause / where:** `frontend/src/pages/DatasetDetail.tsx:1310-1320` and `components/report/InsightsPane.tsx:164-174` call `pinsApi.create` and toast `i2d.dd.pinned` / `ins.pinned` (`i18n/en.ts:2476`). Nothing in the app reads `pinsApi.list`, and `components/DynamicPinCard.tsx` is mounted only in tests. The widget pin was already removed for this exact reason (`components/report/WidgetRenderer.tsx:1510-1513`). Confirmed.
- **Fix:**
  1. Remove both pin buttons and their toasts and i18n keys (en and ar). Keep `pinsApi` and `routers/pins.py`, as was done for widgets.
  2. Decision needed (follow-up, not required for this fix): a "Pinned" section on Home built from `DynamicPinCard` + `pinsApi.list/remove`, with an unpin control. If the team picks that, ship it **instead of** step 1.
- **Tests:** automated: `frontend/src/components/report/InsightsPane.test.tsx` and `frontend/src/pages/DatasetDetail.test.tsx` assert that no button labelled by `ins.pinAria` / `i2d.dd.pinFinding` exists. Manual: Analysis › Insights shows no pin icon.
- **Effort:** S
- **Depends on / related:** —

### AD-06 — Make "View full scan →" show the scan just seen, and stop the analysis 404s (INS-02)
- **Severity:** Medium
- **Evidence:** #13 · D-33/34; QA INS-02
- **Problem:** "View full scan →" from the Insights hub opens `/datasets/N#insights` on an empty panel with only "Generate insights", so the scan the user just saw is lost. The page also logs 2× `404 GET /api/v1/datasets/N/analysis` on arrival.
- **Root cause / where:**
  - `frontend/src/pages/DatasetDetail.tsx:604-610`: `insights` starts as `null`, and the section at `:1271-1290` fills only when the button is pressed.
  - The hub's result lives in `InsightsHub` local state, and `services/api.ts:2156` removes the promise from `_insightsInFlight` once it settles, so the result can't be reused.
  - The backend saves the raw findings (`routers/datasets.py:2752-2771`, `analysis_type="insights_scan"`) but has no read endpoint.
  - The 404s come from `DatasetDetail.tsx:288` `analysisApi.get` → `routers/analysis.py:208-239` `get_analysis`. It returns 404 for the normal "no profile yet" state (and for restricted callers).
  - All confirmed.
- **Fix:**
  1. `services/api.ts`: add a resolved-result cache next to `_insightsInFlight` (`Map<dsId, {at, result}>`, TTL 5 min). `runShared` returns the cached result while it is fresh. Add `insightsApi.cached(dsId)`.
  2. `DatasetDetail.tsx`: when `analysisPick === 'insights'`, `insights == null`, and the dataset isn't DirectQuery, call `insightsApi.runShared(ds.id).then(setInsights)` on its own. From the hub this is a cache hit, so it's instant. DirectQuery keeps the explicit button (it reads up to 250K rows).
  3. `routers/analysis.py:238`: return `200 null` (not 404) when there is simply no analysis yet. Keep 404 for an unknown or foreign dataset. Update the callers at `DatasetDetail.tsx:288` and `ReportBuilder.tsx:796` to treat `null` as "none", keeping the `?new=1` auto-run.
- **Tests:** automated:
  - `frontend/src/pages/DatasetDetail.test.tsx`: with `insightsApi.runShared` resolving, rendering `/datasets/1#insights` shows `insights-narrative` without a click.
  - `backend/tests/test_analysis_contract.py`: GET `/datasets/{id}/analysis` with no stored result returns 200 with body `null`, and a foreign org still gets 404.
  - Manual: Insights hub → Sales → View full scan. The findings appear at once and the console shows no 404.
- **Effort:** M
- **Depends on / related:** AD-04, AD-07

### AD-07 — Stop labelling non-significant per-row findings STANDOUT, and chart them the way they are stated
- **Severity:** Medium
- **Evidence:** #14 · D-33/34
- **Problem:** "Sao Paulo has the highest shipments per row" (p = 0.222) is shown as STANDOUT. Its chart is sum(shipments), where Dubai is the top bar, so the headline and the chart disagree.
- **Root cause / where:**
  - `backend/app/services/insights.py:633-642` (`_standouts`, the per-row branch) rewrites the title by deleting " average " and appending " per row", and sets `figures.per_row`.
  - `frontend/src/components/insights/FindingChart.tsx:47` decides on avg vs sum with `/\baverage\b|\bmean\b/` on the title, so per-row findings are drawn as `sum`. `FindingChart`'s `Finding` type (`:6-10`) doesn't even carry `figures`.
  - `insights.py:336-358` `_mean_standouts` keeps `kind: "standout"` for weak results and only multiplies the score by 0.4. The UI's kind label (`DatasetDetail.tsx:1300-1304`) ignores `significant`.
  - All confirmed.
- **Fix:**
  1. Backend: on per-row and mean findings, set `figures["aggregation"] = "avg"`. When `significant is False` after `_apply_multiple_comparison_correction`, either drop standout/laggard from the ranked list or change `kind` to `"pattern"`. Recommendation: drop them from the preview and use "pattern" in the full list.
  2. `FindingChart.tsx`: extend `Finding` with `figures?: { aggregation?: string; per_row?: boolean }`. When present, prefer `figures.aggregation` (or `per_row` → avg) over the title regex.
  3. Finding cards: when `significant === false`, show a "Not significant (p = 0.22)" chip.
- **Tests:** automated:
  - `backend/tests/test_insights.py`: build a frame where a per-row standout has p > 0.05. Assert the finding isn't `kind == "standout"` (or is absent) and carries `figures.aggregation == "avg"`.
  - `frontend/src/components/insights/FindingChart.test.tsx`: a finding with `figures.per_row` requests `aggregation: 'avg'`.
  - Manual: Routes › Insights. Shipments per row is no longer STANDOUT, and its chart shows averages.
- **Effort:** M
- **Depends on / related:** AD-06

### AD-08 — Keep the chosen dataset when an Insights filter chip hides it
- **Severity:** Medium
- **Evidence:** #16 · D-41
- **Problem:** Toggling "Mine" or "Hide test-looking" visibly swaps the picker from "Demo — Projects" to the first remaining option ("QA B flow output") while "Scanning for insights…" shows. The user never chose that dataset.
- **Root cause / where:** `frontend/src/pages/InsightsHub.tsx:130-140`: the controlled `<select value={selected}>` lists only `(noMatches ? clean.visible : filtered)`. When the selected dataset is filtered out, the browser displays the first option while React state still holds the old id. The "Scanning…" belongs to the old dataset's in-flight scan. No chip handler calls `setSelected` (`components/dataset/DatasetListFilter.tsx:17-30`). Confirmed in code; the screenshot matches. The same select pattern exists in `pages/Automations.tsx` (D-41 Low note).
- **Fix:**
  1. Add a helper `withSelected(options, selectedItem)` in `components/dataset/DatasetListFilter.tsx`. It appends the selected dataset when the filters hide it, labelled "· hidden by filter".
  2. Use the helper in InsightsHub and Automations.
  3. Never auto-pick a dataset when the filters change.
- **Tests:** automated: `frontend/src/pages/InsightsHub.test.tsx`. Select a dataset not created by the user, click "Mine". The `select.value` still equals that id and `insightsApi.runShared` was called only once. Manual: repeat D-41.
- **Effort:** S
- **Depends on / related:** AD-04

### AD-09 — Fix the Ask AI composer draft: clear it on New chat, and disable "Edit question" while paused
- **Severity:** Medium
- **Evidence:** #9, #10 · D-10..17, D-13/14
- **Problem:** "New chat" keeps the previous "Edit question" text in the composer. While the model is offline, "Edit question" copies text into a composer that is locked (read-only), which is a dead end.
- **Root cause / where:**
  - `frontend/src/components/chat/ChatPane.tsx:241-255`: the conversation-change effect resets `messages`, `loadError` and `convId` but not `input` (`:192`), so going to `conversationId = null` (from `pages/AskAI.tsx:377` `onNew`) keeps the draft.
  - The Edit buttons at `ChatPane.tsx:595`, `:872` and `:966` call `setInput(...)` with no `offline` check, while the Composer is `locked={offline}` (`:673`).
  - Confirmed.
- **Fix:**
  1. In the effect at `:241`, call `setInput('')` when `conversationId == null` and the change isn't the pane's own new thread (`knownId` already tells these apart).
  2. Add `disabled={offline}` and `title={t('off.composer')}` to the three Edit buttons.
- **Tests:** automated: `frontend/src/components/chat/ChatPane.test.tsx`. (a) Type a draft, rerender with `conversationId={null}`, and the composer is empty. (b) With offline mocked, the Edit buttons are disabled. Manual: repeat D-14/D-16.
- **Effort:** S
- **Depends on / related:** AD-02

### AD-10 — Say "AI is not allowed for this dataset" before the first question
- **Severity:** Medium
- **Evidence:** #11 · D-21..23
- **Problem:** On a dataset whose AI policy is "not allowed", Ask AI shows six suggestions and an open composer. The user learns only after asking that "AI is switched off for this data".
- **Root cause / where:** `frontend/src/pages/AskAI.tsx` never reads the dataset's AI policy. The data is available from `allowAiApi.get` (`services/api.ts:2333`) → `routers/datasets.py:3647` `get_dataset_allow_ai` (`effective`). The "Ask about this data" link (`pages/DatasetDetail.tsx:926`) doesn't reflect the policy either. Confirmed.
- **Fix:**
  1. `AskAI.tsx`: when `datasetId != null`, fetch `allowAiApi.get(datasetId)`. If `effective === false`, show a notice above the suggestions: "AI is off for this dataset — answers use the built-in analyses only (no AI)". Label the composer the same way. Keep the suggestions, because the no-AI fallback answers them instantly.
  2. `DatasetDetail.tsx:926`: when AI isn't allowed, change the link's title/subtitle to "Ask (built-in analyses, no AI)".
- **Tests:** automated: `frontend/src/pages/AskAI.test.tsx`. With `allowAiApi.get` mocked as `{effective:false}`, the notice renders before any question is sent. Manual: `/datasets/6` → Ask about this data.
- **Effort:** S
- **Depends on / related:** AD-02

### AD-11 — Stop suggesting SUM of latitude, percentages, body measures and per-row ID columns in Ask AI
- **Severity:** Medium
- **Evidence:** #27 · D-65
- **Problem:** Suggestion cards offer "Total origin lat by from city", "Total height by group" and "Total progress pct by task".
- **Root cause / where:**
  - `frontend/src/pages/AskAI.tsx:139` stores only `d.columns` from the dataset list. It ignores `d.column_meta`, which the list already returns (`backend/app/schemas/schemas.py:269`).
  - The effect at `:151` that would load `column_meta` returns early whenever columns are already known, so `classesById` stays empty. `datasetSuggestionCards` (`pages/ask/suggestions.ts:52-83`) therefore can't apply its `isCode` / `ADDS_UP` rules, and falls back to `classify()` (`:22-30`), which only checks dtype and `ID_LIKE`. Confirmed.
  - The `task` label column is near-unique (one row per task) and isn't detected at all. Confirmed.
- **Fix:**
  1. `AskAI.tsx:139`: also fill `classesById[d.id] = d.column_meta` from the list.
  2. `suggestions.ts`: when there's no stored class, mirror the backend name rules from `backend/app/services/semantic_guard.py:30` `_COORD_WORDS` and `:240` `_INTENSIVE_WORDS`. Coordinates, pct/rate/share, and level-type measures are averaged (`highestAvg`/`avgPer`) and never totalled. Add body measures (`height`, `weight`, `bmi`) to both lists.
  3. Skip label columns whose distinct count is at least 0.9 × rows. Use `DatasetColumnOut.stats` (unique count) when present.
- **Tests:** automated: `frontend/src/pages/ask/askHelpers.test.ts`.
  - Columns `origin_lat`, `from_city` produce no "Total origin lat".
  - `progress_pct` with `task` (unique) produces no "Total…" and no "Top 5 task".
  - A stored `{number:'level'}` class gives `highestAvg`.
  - Manual: Ask AI on Routes, Metrics and Projects.
- **Effort:** S
- **Depends on / related:** group C/F (same semantic_guard rules used by widget suggestions)

### AD-12 — Keep the deep-link target through login
- **Severity:** Medium
- **Evidence:** #1 · A-08
- **Problem:** Opening `/reports/1` while signed out, then signing in, lands on Home instead of the requested page.
- **Root cause / where:**
  - `frontend/src/components/ProtectedRoute.tsx:9` `<Navigate to="/login" replace />` doesn't carry `state.from`.
  - `pages/Login.tsx:95-98` (`if (user) window.location.replace('/')`) always goes to `/` after `login()` (`:142`).
  - `pages/SsoCallback.tsx:13` also replaces to `/`.
  - Confirmed.
- **Fix:**
  1. `ProtectedRoute`: use `useLocation()` and `<Navigate to="/login" replace state={{ from: pathname + search + hash }} />`.
  2. `Login.tsx`: read `location.state?.from`, validate it as same-origin (must start with `/`, not `//`, and not `/login`), and `window.location.replace(safeFrom ?? '/')`.
  3. For SSO: save `from` in `sessionStorage` before handing off to the identity provider (`:121`). `SsoCallback` reads it, validates it the same way, and clears it.
- **Tests:** automated: `frontend/src/pages/Login.test.tsx`. With state `from=/reports/1`, a successful login calls `location.replace('/reports/1')`. `from='//evil.example'` gives `/`. New `frontend/src/components/ProtectedRoute.test.tsx` checks that a signed-out render navigates with `state.from`. Manual: open `/reports/1` signed out, sign in, and land on the report.
- **Effort:** S
- **Depends on / related:** AD-13

### AD-13 — Replace the bare "Loading…" during auth bootstrap with the app loader
- **Severity:** Medium
- **Evidence:** #2 · A-08b
- **Problem:** Protected routes show unstyled "Loading…" text in the top-left of a blank page while `/auth/me` resolves. Under load this lasted about 2 min (D-01).
- **Root cause / where:** `frontend/src/components/ProtectedRoute.tsx:8` returns `<div style={{padding:40}}>{t('common.loading')}</div>`. The branded `components/ui/Loader` is used only by `App.tsx:73-76` `LoadingFallback`. Confirmed.
- **Fix:**
  1. Return `<Loader label={t('common.loading')} />`, centred full-screen with `var(--bg)`, so it matches `LoadingFallback`.
  2. Optional: an app-shell skeleton (rail + top bar placeholders).
- **Tests:** automated: `frontend/src/components/ProtectedRoute.test.tsx`. With `loading: true`, the Loader renders (`role="status"`), not a bare div. Manual: throttle the network and open `/datasets`.
- **Effort:** S
- **Depends on / related:** AD-12

### AD-14 — Close the notifications panel on Escape, on route change and when the command palette opens
- **Severity:** Medium
- **Evidence:** #3, #4 · A-20, A-22, A-23
- **Problem:** The bell panel ignores Escape. It stays open over the page after Ctrl K and after navigating to a dashboard.
- **Root cause / where:** `frontend/src/components/NotificationsBell.tsx:35-42` closes only on an outside `mousedown`. It has no keydown handler and doesn't watch `useLocation`. The command palette (`components/CommandPalette.tsx:116`) handles its own Escape but doesn't close other popovers. The model picker does close on Escape (`LlmPicker.tsx:141`). Confirmed.
- **Fix:**
  1. While open, add a `keydown` listener: Escape → `setOpen(false)` and return focus to the bell button. Ctrl/⌘+K → `setOpen(false)`.
  2. Add `const { pathname } = useLocation(); useEffect(() => setOpen(false), [pathname])`.
- **Tests:** automated: `frontend/src/components/NotificationsBell.test.tsx`. Open the panel, then (a) press Escape: the panel is gone and focus is on the bell; (b) navigate with MemoryRouter: the panel is gone; (c) press Ctrl+K: the panel is gone. Manual: repeat A-20 → A-23.
- **Effort:** S
- **Depends on / related:** —

### AD-15 — Lay out the Home stat cards 2×2 on phones
- **Severity:** Medium
- **Evidence:** #5 · A-68..A-72
- **Problem:** At 390 px the four stat cards stay in one row, so labels clip ("Dashboar"), values wrap ("5 / minutes / ago") and subtitles truncate.
- **Root cause / where:** `frontend/src/pages/home/home.css:285` sets `.hm-stats { grid-template-columns: repeat(4, …) }` under 1100 px and has no smaller breakpoint (the base rule at `:51` is 2 columns but is overridden). Confirmed.
- **Fix:**
  1. Add `@media (max-width: 600px) { .hm-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } }` after the 1100 px block.
  2. Let the stat subtitle wrap to 2 lines (`line-clamp: 2`), as `.hm-qa small` does.
- **Tests:** automated: `frontend/src/pages/home/layout.test.ts`, following the existing CSS-regex convention: a `max-width: 600px` block sets `.hm-stats` to `repeat(2`. Manual: Home at 390×844.
- **Effort:** S
- **Depends on / related:** AD-20

### AD-16 — Show the demo weekly schedule (and paused or on-demand schedules) on Refresh & jobs, not "—"
- **Severity:** Medium
- **Evidence:** #20 · D-48..50
- **Problem:** "Demo — weekly regional performance" and the demo alert show "—" in the Schedule column.
- **Root cause / where:**
  - The seed data is deliberately inert: `backend/app/services/demo_use_cases.py:694-701` and `:92` set `INERT_INTERVAL = 0` with no calendar spec, while the subject says "weekly".
  - `frontend/src/pages/monitoring/MonitoringJobs.tsx:60-62` `interval()` renders `<= 0` as "—".
  - Confirmed. This is partly a seed artifact, but real "on demand" rows hit the same "—".
- **Fix:**
  1. `MonitoringJobs.tsx:62`: render `<= 0` as `t('pg.dataPages.jobs.paused')`, "Paused (not scheduled)" in en and ar.
  2. Demo seed: add a weekly calendar spec with `"paused": true` to the recipients JSON. Make `services/refresh_scheduler.py:271` `schedule_is_due` return False when `spec.get("paused")`, so the demo still never sends. The jobs page then reads "Weekly, Monday 09:00 (paused)" (append "(paused)" in `schedule()` at `MonitoringJobs.tsx:49`).
- **Tests:** automated:
  - `backend/tests/test_demo_use_cases.py`: the seeded schedule has a calendar spec and `schedule_is_due(...)` is False.
  - `backend/tests/test_refresh_scheduler.py` (or the existing scheduler test file): a paused calendar spec is never due.
  - `frontend/src/pages/monitoring/Monitoring.test.tsx`: `interval_minutes: 0` renders "Paused".
  - Manual: `/monitoring/jobs`.
- **Effort:** S
- **Depends on / related:** AD-17

### AD-17 — List automation runs and data-check runs in Monitoring
- **Severity:** Medium
- **Evidence:** #21, #24 · D-48..50, D-54/55
- **Problem:** The page says "Everything that runs", but today's automation runs and the quality-rule run are missing. No central place shows data-check results.
- **Root cause / where:**
  - `backend/app/routers/admin.py:606-686` `list_monitoring_jobs` collects only four kinds (dataset_refresh, dataflow, report_schedule, alert). `KIND_LABEL` in `MonitoringJobs.tsx:22-27` matches.
  - Manual "Run now" for checks is `routers/datasets.py:2050` `try_data_checks`, which is read-only by design and stores nothing.
  - Checks that run during a refresh are stored in `RefreshRun.checks` (`models/models.py` ~2202), but `RefreshHistory` (`MonitoringJobs.tsx:98+`) doesn't show them.
  - Confirmed.
- **Fix:**
  1. Add `GET /admin/monitoring/automation-runs` (org-scoped, newest first, status/started/finished/step/error), or add `kind:"automation"` rows to the jobs list. Render it as an "Automations" section linking to `/automation?run=<id>`.
  2. RefreshHistory: add a "Checks" column summarising `RefreshRun.checks` (for example "2 pass · 1 warn").
  3. Decision needed for manual "Run now": it's documented as read-only. Either record an audit entry `dataset.checks_run` with "Checked 2,000 rows · all pass" so it shows in Activity, or persist the result as a `RefreshRun(trigger="check")`.
- **Tests:** automated:
  - `backend/tests/test_monitoring_endpoints.py`: an automation run appears for org A only, with its status and dataset name. Refresh-runs include the `checks` summary.
  - `frontend/src/pages/monitoring/Monitoring.test.tsx`: the Automations section renders a row with a link.
  - Manual: start an automation and run checks, then open `/monitoring/jobs`.
- **Effort:** M
- **Depends on / related:** AD-03, AD-16, AD-19

### AD-18 — Write Activity details in plain words (no "key=None" or "grant:3:")
- **Severity:** Medium
- **Evidence:** #22 · D-52/53
- **Problem:** The Activity detail column shows raw strings such as "queries=None asks=None storage_mb=None…" and "grant:3: view…".
- **Root cause / where:** Writers build the detail strings from raw values:
  - `backend/app/routers/platform.py:141-145` (`platform.set_org_quota`, prints Python `None`)
  - `routers/publishing.py:222` and `routers/reports.py:786` (`grant:{id}`)
  - `MonitoringActivity.tsx:89` prints `r.detail` verbatim.
  - Confirmed.
- **Fix:**
  1. At these writers, format human text: omit unset limits, or write "no limit"; "Daily queries: 500 · AI asks: no limit…"; "Shared with Sales (view, no export)".
  2. Add a small frontend formatter in `pages/monitoring/MonitoringActivity.tsx` for **legacy** rows: `key=None` → "key: no limit", and split `key=value` pairs into "Label: value" chips.
  3. Do a grep audit of `audit(…, f"…={…}")` call sites for the same pattern.
- **Tests:** automated:
  - `backend/tests/test_audit_log.py`: setting an org quota with nulls writes a detail without "None".
  - `frontend/src/pages/monitoring/Monitoring.test.tsx`: a legacy row "queries=None asks=5" renders "no limit" and "5".
  - Manual: `/monitoring/activity`.
- **Effort:** M
- **Depends on / related:** AD-19

### AD-19 — Add paging, filters and row detail to Activity; decide on logging Ask AI
- **Severity:** Medium
- **Evidence:** #23 · D-52/53
- **Problem:** Activity loads one list of up to 200 rows, with no paging, no filters by user/action/date and no row detail. Ask AI questions and insight scans don't appear.
- **Root cause / where:**
  - `backend/app/routers/admin.py:487-506` `list_audit_log` takes only `limit` (max 1000) and has no offset or filters.
  - `frontend/src/pages/monitoring/MonitoringActivity.tsx:31` calls `monitoringApi.activity()` once (`services/api.ts:2624`).
  - `routers/agent.py:290` `ask` writes no audit row.
  - Confirmed.
- **Fix:**
  1. Backend: add `before_id` (keyset paging), `action`, `user_email`, `since`, `until` params.
  2. Frontend: add action and user selects plus a date range above the table, and a "Load more" button. Clicking a row expands the full detail, entity link and time.
  3. Decision needed for Ask AI logging: questions can contain sensitive text. Recommendation: audit `agent.ask` with the conversation id and dataset only (no question text), and `insights.scan` with the dataset id.
- **Tests:** automated:
  - `backend/tests/test_monitoring_endpoints.py`: `before_id` pages without overlap, and `action=` filters.
  - `backend/tests/test_agent_api.py` (if approved): an ask writes `agent.ask` without the question text.
  - `frontend/src/pages/monitoring/Monitoring.test.tsx`: "Load more" requests `before_id`.
  - Manual: Activity with more than 200 rows.
- **Effort:** M
- **Depends on / related:** AD-18, AD-17

### AD-20 — Stack the Monitoring tables (Activity, Jobs, Deliveries) as cards on phones
- **Severity:** Medium
- **Evidence:** #25 · D-59..62
- **Problem:** At 390 px, Activity shows only When/Who and Jobs only Kind/Name. Action, Entity, Schedule and Status are off-screen, with only a faint scroll shadow to hint at them.
- **Root cause / where:** `frontend/src/index.css:513-517`: `.dl-table-card > .dl-table { min-inline-size: 560px }`, with horizontal scroll inside the card below 700 px (`:525-541`). The stacked `data-label` pattern exists only for the LLM endpoints table (`index.css:3122`, `components/admin/LlmEndpointsPanel.tsx:180+`). Confirmed.
- **Fix:**
  1. Add a reusable `.dl-table--stack` modifier: under 600 px each `tr` becomes a card and each `td[data-label]::before` shows its column name. Generalise the LlmEndpointsPanel rule for this.
  2. Apply it with `data-label` on every `td` in `MonitoringJobs.tsx`, `MonitoringActivity.tsx` and `MonitoringDeliveries.tsx`.
- **Tests:** automated: new `frontend/src/styles/tableStack.test.ts` (CSS-regex convention, as in `pages/home/layout.test.ts`) checks that the stack rule exists. In `frontend/src/pages/monitoring/Monitoring.test.tsx`, every `td` has a `data-label` attribute. Manual: the three pages at 390×844.
- **Effort:** S
- **Depends on / related:** AD-15, AD-21

### AD-21 — Stop the automation row squeezing the dataset name to one letter per line on phones
- **Severity:** Medium
- **Evidence:** #26 · D-59..62
- **Problem:** On a phone, the run's dataset link "Demo — Feedback" wraps one letter per line and "Started 14 …" is truncated.
- **Root cause / where:** `frontend/src/pages/Automations.tsx:188-221`: one flex row (`flexWrap: 'wrap'`) holds the title block, status, step dots and buttons. `.dl-rows__main { flex: 1; min-inline-size: 0 }` (`index.css:2103`) lets the title shrink to zero width instead of wrapping the controls to the next line. Confirmed.
- **Fix:** In `index.css`, give `.dl-rows__row--stack .dl-rows__main` a `flex: 1 1 14rem` basis, or under 600 px set `flex-basis: 100%`. The status, dots and actions then drop to a second line, and the action span loses `marginInlineStart:auto` on phone.
- **Tests:** automated: a CSS-regex test in `frontend/src/pages/Automations.test.tsx` or a new `rowsLayout.test.ts`, asserting `.dl-rows__main` has a non-zero flex-basis in the stack variant. Manual: `/automation` at 390×844.
- **Effort:** S
- **Depends on / related:** AD-20

### AD-22 — Decide on automation management (name, edit, delete, schedule/trigger), and allow delete/retry for stopped runs
- **Severity:** Medium
- **Evidence:** #18 · D-42..46/56..58
- **Problem:** Automations can't be named, edited, deleted, scheduled or triggered any way other than a manual "Start automated analysis". Cancelled runs can't be removed or retried.
- **Root cause / where:** **Decision needed.** The product ships one manual "automated analysis" run type. `backend/app/routers/automation.py` exposes only start/list/get/approve/reject/cancel/retry (`:98-213`), and there is no automation definition model to name, edit or schedule. That is a feature gap, not a bug. One part is a small code gap: `retry_run` (`:200-213`) returns 409 unless the run status is `failed`, and no endpoint deletes a terminal run. Confirmed.
- **Fix:**
  1. Small (do now): add `DELETE /automation/runs/{id}` for `done`/`cancelled`/`failed` runs, which calls `discard_run_artifacts` and writes an audit entry. Let `retry` restart a `cancelled` run from its first step without an `output_ref`. Add Delete and Retry buttons in `pages/Automations.tsx:211-218`.
  2. Decision: whether to add saved automation definitions (name, dataset, schedule or trigger). If yes, that is a separate L-sized feature with a new model and scheduler hook.
- **Tests:** automated:
  - `backend/tests/test_automation_api.py`: deleting a cancelled run returns 204, and the run is gone along with its artifacts. Deleting a running run returns 409. Retrying a cancelled run sets it back to pending.
  - `frontend/src/pages/Automations.test.tsx`: a cancelled run shows Retry and Delete.
  - Manual: cancel a run, then retry it and delete it.
- **Effort:** S (management feature: L, decision needed)
- **Depends on / related:** AD-03

Coverage: worklist items 1..27 all mapped. Merged: #3+#4 (AD-14), #6+#7+#8 (AD-02), #9+#10 (AD-09), #17+#19 (AD-03), #21+#24 (AD-17); #7 and #17 also feed the shared gate AD-01; #13 is merged with QA INS-02 (AD-06). Decision needed: #18 (AD-22, automation management is a feature gap), the persistence of manual check runs in #24 (AD-17 step 3), Ask AI audit logging in #23 (AD-19 step 3), and the alternative Pinned section on Home for #15 (AD-05 step 2).


