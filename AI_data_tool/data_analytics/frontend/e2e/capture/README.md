# UI reference captures

`capture_screens.mjs` takes a screenshot of every page and important state of the app: 106 screens at 1440×900, `deviceScaleFactor` 1. It replaces the lost `.ds-sync/capture.mjs` that produced the 2026-09-24 `design-screenshots` set. The first 102 file names are the same as in that set, so an old capture and a new one can be compared file by file. The extra four are Ask AI states added for the redesign (02-05 to 02-08).

## Run it

Start the stack first. The defaults expect the app at http://localhost:3001 and the API at http://localhost:8000. Then, from the repo root:

```
node AI_data_tool/data_analytics/frontend/e2e/capture/capture_screens.mjs          # all 106 screens
node AI_data_tool/data_analytics/frontend/e2e/capture/capture_screens.mjs 02 13    # only sections 02 and 13
node AI_data_tool/data_analytics/frontend/e2e/capture/capture_screens.mjs --list   # print the screen list
node AI_data_tool/data_analytics/frontend/e2e/capture/capture_screens.mjs --out /some/dir
```

Those are the only options: section numbers, `--list` and `--out`. Everything else is an environment variable (see Settings).

Playwright is resolved from `frontend/node_modules`, so run `npm install` and `npx playwright install chromium` in `frontend/` once. To use a different Chromium, set `PLAYWRIGHT_EXECUTABLE`.

By default, output goes to `screenshots_2/`, the folder next to the repo, and **overwrites** what is there. Use `--out` for a throwaway run.

- `<section>/<name>.png`: the screenshots
- `.results.json`: one entry per screen with its status, health counts and console errors. It has the same shape as the old run's file.
- `MANIFEST.md`: a table of the screens, with the dataset and dashboard ids that were used
- `_contact-sheets/contact-sheet-N.png`: thumbnails of every screen

A partial run (for example `02 13`) merges its results into the `.results.json` that is already there.

## Ask AI screens (section 02)

Every screen after 02-02 asks the live model, so the model server must be reachable. A screen whose question fails (error card or AI limit) is marked `PREP FAILED`; its screenshot is still written, so check `.results.json` before trusting a run.

| Screen | State | Question |
|---|---|---|
| 02-03 `clarification` | the model asks back for detail | `CAPTURE_ASK_CLARIFY` |
| 02-04 `answered` | an answer with its rows | `CAPTURE_ASK_ANSWER` |
| 02-05 `answer-chart` | an answer drawn as a chart, rows open | `CAPTURE_ASK_CHART` |
| 02-06 `answer-sql-open` | the same answer with "Show SQL" open | `CAPTURE_ASK_CHART` |
| 02-07 `answer-arabic` | a question and answer in the Arabic UI | `CAPTURE_ASK_ARABIC` |
| 02-08 `clarification-arabic` | a clarification in the Arabic UI | `CAPTURE_ASK_CLARIFY` |

The default questions are written to work on any dataset ("the first numeric column", "the first category column", an unknown column for the clarification). For a particular dataset, set `CAPTURE_DATASET_ID` and better questions, for example on Demo — Sales:

```
CAPTURE_DATASET_ID=1 CAPTURE_ASK_CHART="average margin_pct by region" node .../capture_screens.mjs 02
```

The model is not deterministic: 02-03 and 02-08 fail when it answers instead of asking back, and 02-05 fails when the answer is not charted. Re-run the section, or change the question.

`CAPTURE_ASK_TIMEOUT_S` sets how long to wait for each answer (default 150 seconds).

## Settings

All settings are environment variables. Each one is also described at the top of the script.

- **Logins:** `CAPTURE_EMAIL` and `CAPTURE_PASSWORD` set the admin login. The default is `admin@datalytics.local` / `demo-password`. `CAPTURE_ANALYST_*` sets the non-admin login, which defaults to `demo-emea@example.invalid`. That is a seeded analyst whose row security limits it to Europe.
- **Objects:** `CAPTURE_DATASET_ID`, `CAPTURE_CONNECTION_ID`, `CAPTURE_REPORT_ID` and `CAPTURE_MULTIPAGE_ID` choose which objects are shown. By default the script uses the old run's ids (170, 22, 127, 132) where they still exist. Otherwise it picks the richest object it finds through the API.
- **Ask AI:** `CAPTURE_ASK_CLARIFY`, `CAPTURE_ASK_ANSWER`, `CAPTURE_ASK_CHART`, `CAPTURE_ASK_ARABIC` and `CAPTURE_ASK_TIMEOUT_S`, as above.
- **Pacing:** `CAPTURE_API_BUDGET` (default 200) caps how many API requests the script makes per minute. The API's rate limit is 300 a minute per user, and one dashboard load fires more than 50 requests. If a screen still reports `RATE LIMITED`, lower the budget or raise `RATE_LIMIT_REQUESTS_PER_WINDOW` on the backend.

## Things that depend on the data

- The list search boxes appear only when a list has 8 or more items. With fewer, the screens `03-datasets-02`, `03-datasets-03` and `07-dashboards-02` fail with a message saying so.
- The source review screens (05-05 to 05-10) show empty states until the connection has been synced.
- The script mostly only reads. It makes two kinds of change:
  - Each Ask AI screen from 02-03 on creates a chat thread (six threads per run of section 02).
  - Screen 07-33 creates a guest link and revokes it when the run ends.

## When the UI changes

Selectors mostly use accessible names (`getByRole` and `getByLabel`) and the app's `data-testid`s. A few places have neither, or must work in both languages, so the script falls back to a class there: `.dl-panebar`, `.dl-conn`, `.dl-nomatch`, `.dl-answer-clarify`, `.dl-answer-error`, `.dl-chat__composer`, `.dl-result__rows-toggle`, `.dl-sql__code`, `.dl-loading` and reactflow's `.react-flow__node`. Each screen is one `add(...)` call. When a screen fails with `PREP FAILED`, look at its screenshot: the script still takes one, so you can see where it stopped.
