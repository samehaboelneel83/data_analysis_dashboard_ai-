# responsive/ — capture manifest

*Sub-desktop layouts.*

**No images — blocked by tooling, not by effort.** `resize_window` reports success and the viewport never moves (re-confirmed 2026-09-23: requested 900x750, viewport stayed 1214x675). Page-zoom shortcuts are not accepted by the automation either, so no second viewport width was ever reachable.

To evidence the breakpoints, capture **V05** (`../visualizations/V05_rendered-chart-frequency-of-region.png`) at three browser widths by hand and drop the files here:

| File | Width | What should differ |
|---|---|---|
| `R01_editor-wide.png` | ~1600 px | Both rails expanded, chart at full width |
| `R02_editor-medium.png` | ~1100 px | Panes collapse to the icon rail |
| `R03_editor-narrow.png` | ~800 px | Single column; canvas above or below the panes |

Until then §M of `design-system.md` is the documented behaviour and is **unverified at a second width**.

| ID | Screen | Route | State | Action that produced it | Key elements | Described in |
|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — |

**Not observed.** The viewport could not be narrowed in the environment used for this crawl, so no sub-desktop state exists to capture. CSS breakpoints (768 / 992 / 1200) are recorded in `design-system.md`.
