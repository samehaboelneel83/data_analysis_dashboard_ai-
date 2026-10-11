# English still hard-coded in the app — inventory

Generated from `frontend/src/test/i18nBaseline.json` on 2026-10-11. The number for a file is how many
reader-visible English literals it still holds (JSX text, titles, placeholders, toasts, menu labels),
as found by `frontend/src/test/hardcodedStrings.ts`.

**0 literals in 0 files** (802 in 81 when the inventory was first taken). Every other screen is fully translated and is held there by a test.

## How it is kept

* `frontend/src/test/strings.inventory.test.ts` fails when a file has MORE English than its recorded number,
  or when a file not on the list has any — so new screens are born translated and a migrated file cannot slide back.
* It also fails when a file has FEWER than recorded, until the baseline is regenerated — the inventory stays true.
* After translating a file:

      UPDATE_I18N_BASELINE=1 npx vitest run src/test/strings.inventory.test.ts

* Configurable in the baseline file: `ignore` (folders or files never scanned) and `files` (the numbers).
* A literal that is not prose (a unit, a code sample) is marked `// i18n-ok` on its line (`{/* i18n-ok */}` inside markup).

## What the scanner does not see

* Sentences the **server** writes. Those travel as key + pieces (`services/readback.Said`, `rb.*` in the catalogue);
  what is covered is listed in docs/discovery/PLAN.md §Z–§AB. Still English from the server: the warnings of the
  older analyses, insight-detector card titles, the column profile facts.
* Text built in `.ts` helpers (only `.tsx` files are scanned), and text inside chart libraries (axis labels made from data,
  such as the weekday and month labels `1 Mon`, `01 Jan`).

## By area and by file

Nothing is left: the baseline's `files` list is empty, so the test now fails on any new hard-coded English in a `.tsx` file.

## Done so far

* `components/analysis/analysisResults.tsx` — every result view (66 → 0).
* `components/report/**` — the widget body, 35 chart renderers and overlays, the forecast's goal sentence (155 → 7).
* `components/dataset/**` — the Columns tab and profile facts, alerts, aggregates, data quality, the schema-break dialog (180 → 13).
* `pages/DatasetDetail.tsx` — the dataset page (66 → 1).
* `components/WorkspaceTree.tsx`, `FolderShareDialog.tsx`, `DatasetShareDialog.tsx`, `CommandPalette.tsx` — workspaces, sharing, the palette (143 → 0).
* `components/QueryBuilderDialog.tsx`, `QueryCanvas.tsx` — the query builder and its canvas (54 → 1).
* `components/review/SuggestFromSourceDialog.tsx`, `JoinGraph.tsx`, `pages/Upload.tsx`, `pages/SharedReport.tsx`, `components/chat/DashboardProposals.tsx` — suggesting from a connection, the join graph, upload, the shared page, chat proposals (61 → 5).
* `StatisticsPanel`, `NotebookSnippet`, `DynamicPinCard`, `EvidencePopover`, `ErrorBoundary`, `SchemaBrowser`, `EmbeddedReport`, `DatasetPickerDialog` — the smaller screens (50 → 0).
* The last 30 files — the language switcher, sync progress, chat history, lineage, the home list, insights, automations, the bell, the sign-in pages and others (46 → 0). 21 were translated; the rest are not prose and carry the `i18n-ok` mark: example addresses and expressions, SQL, a key name, the product's wordmark, a keyboard shortcut, a block of CSS, and the five brief headings in chat that follow the answer's language.

## What is still open

1. Opening the screens in the browser in Arabic — nothing translated in this pass has been looked at on screen.
2. What the scanner does not see (above): sentences the server writes in English, and text built in `.ts` helpers.
