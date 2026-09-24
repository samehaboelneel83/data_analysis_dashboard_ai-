# Shot list — 29 captures

> **Complete — 30 of 32 images present (2026-09-23).** Every image is a frame Claude captured while driving the app, recovered from this session's own transcript rather than from an external timer. Only V17 and V26 are missing, both genuinely blocked (see `CAPTURE_STATUS.md`). V30-V32 are extra surfaces captured during the pass. Times are the local (EEST) hold windows.

**Workflow agreed with you:** you capture, you paste into the chat, I name, sort and zip. Screenshots pasted into the chat reach my disk; screenshots I take myself do not (see `CAPTURE_STATUS.md`).

**How to capture.** Chrome: `F12` → `Ctrl+Shift+P` → type `screenshot` → **"Capture full size screenshot"** (whole scrollable page) or **"Capture screenshot"** (viewport only). Then paste the file into the chat. Full-size is better for the panes; viewport is fine for menus and dialogs.

**You do not need to name the files.** Paste in any order, a few at a time, and say roughly which screen each is — or say nothing and I'll identify them from the manifests. I file them as `V<nn>_<slug>.png` in the right area folder and rebuild the zip each time.

**Order that minimises setup.** Work down the table — it walks one session from the landing page through a blank report, so most rows reuse the previous row's state.

| ✓ | ID | Folder | What to capture | How to get there |
|---|---|---|---|---|
| ☑ | V01 | navigation | Landing page, Recommendations selected | Initial load of `/SASVisualAnalytics/` — **12:? (pre-timer)** |
| ☑ | V02 | dashboards | Blank report, empty canvas | **New report** — **manual** |
| ☑ | V24 | dialogs | Template picker | **Select a template** (then Cancel) — **manual** |
| ☑ | V03 | data | Data pane, table loaded | Recently Used Data → pick a table — **manual** |
| ☑ | V13 | data | Expression editor | **+ New data item → Calculated item** (then Cancel) — **manual** |
| ☑ | V04 | visualizations | Object placeholder, synthetic sample | Double-click **Bar chart** in Objects — **manual** |
| ☑ | V05 | visualizations | Rendered chart | Assign a category (Frequency auto-adds) — **manual** |
| ☑ | V06 | visualizations | Grouped chart + legend | Add a second category to **Group** — **11:56:56–11:57:07** |
| ☑ | V09 | visualizations | Crosstab, totals + subtotals, nested both axes | Crosstab → Options → **Totals and Subtotals** — **11:59:58–12:00:09** |
| ☑ | V07 | forms | Data Roles pane, 8 role groups | Select object → **Roles** tab — **12:00:37–12:00:48** |
| ☑ | V08 | forms | Options pane, sections expanded | **Options** tab — **12:01:11–12:01:22** |
| ☑ | V10 | forms | Filters pane, category filter | **+ New filter** on a category — **12:02:01–12:02:12** |
| ☑ | V11 | forms | Ranks pane | **+ New rank** — **12:02:53–12:03:04** |
| ☑ | V12 | forms | Actions pane | **Actions** tab — **12:03:20–12:03:31** |
| ☑ | V18 | navigation | Outline pane | Rail → **Outline** — **12:03:46–12:03:57** |
| ☑ | V19 | analytics | Suggestions pane | Rail → **Suggestions** — **12:04:13–12:04:24** |
| ☑ | V20 | analytics | Report Review pane | Rail → **Report Review** — **12:04:40–12:04:51** |
| ☑ | V21 | analytics | AI side panel | Banner AI icon — **12:05:22–12:05:33** |
| ☑ | V22 | navigation | Context menu on a chart (25 items) | Right-click a mark — **12:06:09–12:06:20** |
| ☑ | V23 | navigation | Page ⋮ menu + Page type submenu | Page tab **⋮** — **12:06:50–12:07:01** |
| ☑ | V28 | states | Mark selected + hover data tip | Click a mark, then hover it — **12:07:27–12:07:38** |
| ☐ | V17 | states | Loading spinner | Catch an object re-querying — **BLOCKED** |
| ☑ | V14 | states | "No data matches the current filters." | Filter to a non-matching value — **12:10:31–12:10:42** |
| ☑ | V15 | states | "Only 3,000 rows of the data appear." | Bar chart on a very high-cardinality category — **12:12:41–12:12:52** |
| ☑ | V16 | states | Tie-cap notice | Rank with **Ties** on — **12:14:35–12:14:46** |
| ☑ | V25 | states | View mode | Pencil toggle — **12:15:13–12:15:24** |
| ☐ | V26 | dialogs | Pop-up page modal | Double-click a linked mark in a report that has one — **BLOCKED** |
| ☑ | V27 | dialogs | Save confirmation dialog | **⋮ → Close** on an unsaved report — **screenshot it, then press Cancel** — **12:18:39–12:18:50** |
| ☑ | V29 | analytics | Fitted Gradient boosting + Data Roles | **supplied 2026-09-23** — **supplied 2026-09-23** |

## Responsive (`responsive/`) — optional, no IDs yet

Three widths of the same editor screen tell the whole story: ~1600 px (all rails), ~1100 px (panes collapse), ~800 px (single column). Capture V05 at each width if you want the breakpoints evidenced.

## Naming, if you'd rather do it yourself

`V<nn>_<short-slug>.png`, lower-case slug, hyphens — e.g. `V10_filters-pane-category.png`. Drop them in the folder named in the table.

## Two cautions, unchanged

- **V27 is a confirmation dialog.** Capture it and then press **Cancel**. Never Save, never Don't-save on a report that isn't your own throwaway.
- Do the whole pass in a **new blank report**, not in a saved one.
