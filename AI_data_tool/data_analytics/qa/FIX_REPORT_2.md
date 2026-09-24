# Datalytics — second fix pass on the QA run of 2026-09-21

`qa/FIX_REPORT.md` closed the nine scored failures. This one closes what that
pass left open: the rough edges logged against cases that *passed*, plus one
narrow-viewport defect found while looking at them. Every change below is in
the repo; every one carries a test.

| Original note | Where it was logged | Status |
|---|---|---|
| UP-06 — stray duplicated `qa_sample` in a batch dataset's name | pass, minor | Fixed, tested |
| BUILD-03 — KPI card clips the leading `$8` off the total | pass, minor | Fixed, tested |
| BUILD-14 — present-mode toolbar clipped at the top of the window | pass, minor | Fixed |
| ADM-12 — Custom Connectors' top bar reads "Home" | pass, minor | Fixed, tested |
| ASK-04 — `2010526.4600000004` in an Ask AI result | pass, minor | Fixed, tested |
| ASK-03 — "13 rows" for a 13-**column** dataset | pass, minor | Fixed, tested |
| SHARE-02 — a revoked link reported "2 views" | pass, flagged for a human | Cause found, fixed, tested |
| MOB-01 — login on a phone | blocked (no viewport control) | Fixed by inspection |
| MOB-02 — narrow rail drawer | blocked | One real defect found and fixed; rest still needs a human |

---

## UP-06 — the duplicated name fragment

Uploading `qa_sample.csv` + `qa_sample2.csv` produced a dataset called
**"qa_sample — qa_sample"**. Two halves of the same mistake:

- `pages/Upload.tsx` seeded the batch name from the **first file's whole
  stem**, with a comment claiming it was "the common prefix". It was not.
- `routers/datasets.py::_item_name` then appends each file's own stem to that
  base, so the file the base came from got its stem twice.

`batchBaseName()` now takes the prefix the picked files genuinely share,
trimmed of a trailing separator and discarded if it is too short to identify
anything. The server independently drops a stem that the base already *is*, so
a name typed by hand cannot reintroduce the duplicate.

`Q3` + `sales.csv`/`costs.csv` still yields `Q3 — sales` / `Q3 — costs`; the
existing test pinning that is untouched.

## BUILD-03 — the KPI card was hiding the most significant digits

The KPI value is a fixed 36px, centred, with no width handling. A number wider
than the tile overflows on **both** sides, and the widget's own clipping takes
the **leading** characters: `$8,632,597` rendered as `,632,597`. That is worse
than an obviously broken tile — it is a wrong number shown with full
confidence.

`WidgetBody.tsx` gains `fitFontSize()`, which steps the size down by length,
and the value now carries `text-overflow: ellipsis` so anything still too long
is cut at the **end**, where a cut is visible, with the full value on hover.
The multi-row `card` widget had the same shape and got the same treatment.

## BUILD-14 — the present-mode toolbar, and a narrow-width bug behind it

One hard-coded number. The builder bleeds to the edges of the shell's content
area with `margin: -28` and `height: calc(100% + 56px)` — against a shell
padding of `var(--dl-6)`, which is **32px**. So:

- desktop: a 4px sliver of padding survives (cosmetic);
- narrow (`< DRAWER_BREAKPOINT`, padding `var(--dl-4)` = 16px): the builder
  overhangs by 12px and clips its own toolbar — a real MOB-02 defect nobody
  could reach, because the viewport could not be resized;
- present mode (padding forced to 0): the builder is pulled 28px off the top of
  the window, which is what ate the top of the Stop button.

`Layout.tsx` now publishes the padding it applies as `--dl-shell-pad`, and the
new `.dl-bleed` class cancels *that value*, so the two cannot disagree at any
width or in any mode. Present mode zeroes the property alongside the padding.

## ADM-12 — pages that did not name themselves

`messageForPath` falls back to `nav.home` for a path it does not know. That is
right for the unknown, but `/admin/custom-connectors` and
`/admin/connection-rules` are routes the app itself declares — both were
missing from `PATH_MESSAGE`, so both titled themselves "Home", which reads as
if the navigation had failed.

Both added, in English and Arabic. `i18n/titles.test.ts` is the durable part:
it parses `App.tsx` and holds **every** routed page to having a title, so the
next page that forgets one fails on the day it is added rather than in a QA
pass.

## ASK-04 — floating-point noise

`ResultView` printed cells with `String(v)`, so a summed currency column
arrived as `2010526.4600000004`. `cellText()` rounds to 12 significant digits —
well inside a double's ~15–17 and well outside where the artefact lives — so
the tail goes and no value anyone typed is altered. Integers and ids pass
through untouched, and there are deliberately **no** thousands separators: this
grid shows whatever columns the question returned, and "2,024" for a year is
its own kind of wrong. The CSV export uses the same function, so the download
cannot disagree with the screen.

## ASK-03 — "13 rows" for 13 columns

Not a generation fluke. In single-object scope `catalog_overview` returns one
row per **column**, and `explain._facts` labelled every result "(n rows)". The
model was told there were 13 rows and said so — a true count of the wrong noun.

`_row_noun()` now states the unit the catalog step actually holds (columns for
one object in scope, tables for several), the label says the same, and the
prompt names the rule explicitly. Ordinary query results still count rows.

## SHARE-02 — the revoked link with two views

Not a leak and not a phantom visit. `GET /shared/{token}` records one
`ShareLinkAccess` row per request, and `SharedReport.tsx` fetched it from an
effect with no guard — React StrictMode double-invokes effects in development,
and a remount does it in any build. One open, two rows, "2 views".

Both ends are fixed: the page remembers the token it has loaded, and
`log_share_access_sync` drops an identical repeat (same link, viewer, ip hash
and user agent) inside a 10-second window. A reload a minute later is still a
real second visit, and two different readers at the same instant are still two
views. `test_repeated_renders_each_leave_one_row` pinned the old behaviour and
has been rewritten to pin the new one.

## MOB-01 — the login card on a phone

The card was a fixed `width: 360` with no gutter of its own: at 390px it
touched both edges, and below 360px it ran off the screen with no sideways
scroll to reach it. It now takes the width it is given up to 360, inside a
16px gutter, with padding that closes up on small screens.

This is inspection, not a measurement — MOB-01…04 still need a real device or
working viewport emulation.

---

## Files changed

```
frontend/src/pages/Upload.tsx                      batchBaseName() from the shared prefix
frontend/src/pages/Login.tsx                       card fits a phone
frontend/src/pages/SharedReport.tsx                one fetch per visit
frontend/src/pages/ReportBuilder.tsx               .dl-bleed instead of margin:-28
frontend/src/components/Layout.tsx                 publishes --dl-shell-pad
frontend/src/components/report/WidgetBody.tsx      fitFontSize() for KPI and card
frontend/src/components/chat/ResultView.tsx        cellText(), also used by the CSV
frontend/src/index.css                             .dl-bleed; present mode zeroes the pad
frontend/src/i18n/{index,en,ar}.ts                 two missing page titles
backend/app/routers/datasets.py                    _item_name drops a duplicate stem
backend/app/services/agent/nodes/explain.py        _row_noun() + prompt rule
backend/app/services/query_log.py                  share-access dedupe window

frontend/src/i18n/titles.test.ts                       NEW — every route has a title
frontend/src/components/report/WidgetBody.fit.test.ts  NEW
frontend/src/components/chat/ResultView.cellText.test.ts NEW
frontend/src/pages/Upload.test.tsx                     + batchBaseName cases
backend/tests/test_batch_upload.py                     + the duplicate-stem case
backend/tests/test_agent_explain.py                    + the unit-noun cases
backend/tests/test_share_link_access_log.py            rewritten for one-visit-one-row
```

## Verification

Run in a Linux sandbox against a copy of `frontend/src` (the checked-in
`frontend/node_modules` is a Windows install and vitest cannot start from it).

- `npx tsc --noEmit` — only the four pre-existing errors (`CopilotChat.test.tsx`,
  `geo/MapFrame.tsx`, `geo/worldGeometry.ts` ×2). No new ones.
- Frontend, run by file: `Upload` (18), `WidgetBody.fit` (4),
  `ResultView.cellText` (6), `titles` (29), `i18n/index` (3), `Layout` +
  `TopBar` + `Dashboard` (52), `ReportBuilder` (105) — **all passing**.
- `WidgetRenderer.test.tsx`: 142 passing, the same 4 map cross-filter failures
  as before these changes. `SharedReport.test.tsx`: 9 passing, the same 3
  failures — verified identical with the change reverted, so they are not
  mine. Both sets are the world-atlas/asset failures the first pass described.
- Backend: `test_agent_explain.py` + `test_share_link_access_log.py` 29 passed;
  `test_batch_upload.py` 15 passed; `test_query_runs.py`,
  `test_share_links.py`, `test_share_link_viewer_identity.py`,
  `test_upload_path_safety.py` 43 passed.
- A full `vitest run` of the whole suite could not be completed here — the run
  stalls partway in this sandbox's memory budget. **Run it locally before
  merging**, as the first pass also asked.

## Still open — needs a person, not a patch

- **MOB-01…04** beyond the login card. There are no width media queries in the
  stylesheet at all; responsiveness is the rail drawer's `narrow` state and
  nothing else. Whether that is enough at 390px is a judgement to make while
  looking at it.
- **BUILD-08 / MAP-04** — resize handles. Still unexercised; the previous run's
  tooling could not drive the gesture.
- **INS-03 / LIN-03** — preconditions that do not exist in this environment.
- **BUILD-09 / BUILD-15** — the first pass could not reproduce the blank canvas
  and fixed a real stale-ref bug in the same path. The "frozen renderer"
  explanation does not account for two things the original run recorded: that a
  hard reload did not recover the page, and that switching to a packed template
  did. Worth one human attempt with a real mouse before it is called closed.
- **DS-04** was re-verified on a 5-row QA dataset, not on Demo — Sales (dataset
  120), where "profit" and "qa_margin" were reported missing. The horizontal-
  scroll explanation fits, but it was not confirmed where the finding came from.
- **BUILD-05**'s re-test did not mention setting a widget to Isolated, which the
  original repro required.
- **I18N-02** — the notifications dropdown was never explicitly re-tested
  alongside the account and language menus.

`qa/_to_delete/_qa_tmp_frontend.tar.gz` is the previous pass's temporary
archive, already moved aside and safe to delete.
