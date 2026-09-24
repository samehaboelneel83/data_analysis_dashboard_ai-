# Session 20 — navigation pass for the screenshot capture

Twenty-first live session. Claude drove the app, the operator's own timer captured the screen every 3 seconds. Everything below was **observed** during that pass, in a new unsaved sandbox report (`Report 1`, three pages) on `RETAILDEMO_2` (2.3M rows). Nothing was saved; the close dialog was cancelled.

## Exact message strings (previously paraphrased)

| State | Verbatim string |
|---|---|
| Empty result | `No data matches the current filters.` |
| Row cap | `Only 3,000 rows of the data appear.` |
| Tie cap | `Only some of the data appears because there are too many ties associated with the rank.` |
| Unsaved close | `Do you want to save "Report 1" before it is closed?` — buttons **Save / Don't save / Cancel** |
| Copilot locale | `SAS Viya Copilot is currently available only in English.` — with a `Don't show this message again` checkbox and a single **Close** |

The row-cap and tie-cap strings are **not** banners. Both render as a small ⓘ glyph in the object's bottom-right corner; the text appears only on click/hover as a tooltip. An object can therefore be silently truncated with a 16×16 affordance as the only signal — worth copying as *placement*, not as *prominence*.

## Menu inventories

**Report ⋮ (toolbar).** Home · New · Open · Save · Save as · Reopen report · Close · View report · Export ▸ · ~~Share report~~ (greyed) · Copy link… · Copy embeddable markup… · Distribute report… · Localize report · Import pages from report.

**Page ⋮ (page tab).** Rename · Page type ▸ · Limit visibility to specified users… · Delete page · Duplicate page · Export as PDF · Copy link… · Copy embeddable markup… · Expand page controls · Expand all page controls · Save as page template · Manage page templates.

**+ New data item.** Hierarchy · Custom category · Calculated item · Geography item · Parameter · Interaction effect · Spline effect · Partition.

Note that the distribution surfaces exist at **two** scopes with near-identical wording — report-level (`Export ▸`, `Copy link…`, `Copy embeddable markup…`, `Distribute report…`) and page-level (`Export as PDF`, `Copy link…`, `Copy embeddable markup…`). A build that copies this should disambiguate them in the label, not rely on the menu's origin.

## Corrections to earlier entries

- **Page type ▸** offers ✓Basic / Hidden / Pop-up. Pop-up is enabled once the report has more than one page; the earlier note recorded it greyed, which is the single-page case only.
- **View mode hides pop-up pages from the tab strip.** With Page 1 (Basic), Page 2 (Basic) and Page 3 (Pop-up), the viewer showed two tabs. This confirms "tabs for Basic pages only" by construction rather than by inference.
- **Options pane has a settings-search box** (`Filter`, directly under the object selector), present on every object. Still not exercised.
- **Role pickers come in two shapes.** A single-value role (`Category` on a bar chart) opens a **single-select** list that applies on click. A multi-value role (`Rows`/`Columns` on a crosstab) opens a **multi-select** list with checkboxes, a `Select all` link and an explicit **Apply**. Same visual container, two different commit models — a real trap for anyone copying the pattern from one screenshot.

## New defect candidates

**85 — nested crosstab renders empty measure cells while its own totals compute.** With Rows = Department ▸ Region and Columns = Brand Name ▸ ChannelType over 2.3M rows, every intersecting measure cell rendered `——` while the `Total` column showed 2,339,245 and `Subtotal: electronics` / `Subtotal: grocery` / `Subtotal: Maple` all resolved to real numbers. The totals prove the data is present and the query succeeded; only the cross-cells are blank. Adding a third row level (City) made the rows render but did not fill the cross-cells. Either a cell-count cap with no notice, or a genuine rendering fault — the object shows no ⓘ either way, which is the part worth not copying.

**86 — a saved page link to a pop-up page has no affordance in the viewer.** Page 3 was set to `Page type → Pop-up`, and the Page 1 bar chart's `Actions → Page Links → Page 3` checkbox was ticked and persisted (still ticked on re-inspection). In the viewer the link was unreachable: single click selects the mark, double-click **zooms the axis**, and the right-click menu (Sort · Explain data · Generate graph summary · Grouping style · Labels · Hide legend · Maximize view · Export ▸ · Copy link greyed) offers no link entry. Whatever additional step arms the link is undiscoverable from the object itself.

**87 — no loading state is observable on re-render.** Deliberately provoked four times: page switches, a role addition on a 2.3M-row crosstab, and a 1.7M-category bar chart. Results are cached client-side, so a page switch never re-queries at all, and first-time queries completed inside a 3-second sampling window without ever painting a spinner. The documented `Loading…` state exists but is effectively unobservable at normal latency — which means it is also untested at normal latency.

## Still blocked by tooling

`resize_window` again reported success (`900x750`) while the viewport stayed at 1214×675. Responsive breakpoints cannot be evidenced from this automation. Unchanged from session 12.
