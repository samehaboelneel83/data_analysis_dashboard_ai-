# Design System and Responsive Behaviour

> Part of the Visual Analytics reverse-engineering deliverable. Sibling files: `application-map.md`, `screens.md`, `activities.md`, `components.md`, `visualizations.md`, `data-model.md`, `interaction-model.md`, `design-system.md`, `implementation-spec.md`, `screenshots/`.
> **Evidence labels:** OBSERVED (seen in the running app) · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.

## L. Design System

All values measured from live computed styles at a 1214×731 viewport, light theme.

### L.1 Typography
| Token | Value |
|---|---|
| Family | A single humanist sans across the whole product (vendor font `Anova UI`; substitute your own — Inter, Source Sans 3 or system-ui behave equivalently) |
| Base body | 14px / weight 400 / colour `#1B1D22` |
| Banner and pane titles | 16px / 400 / line-height 22.4px (1.4) |
| Rail tab labels, section labels | 16px and 12–14px |
| Buttons | 14px / 400 |
| Small control text | 12px |
| Crosstab heading style default | 9pt **bold** |
| Weights in use | 400 regular, 700 for headings/totals; no light weights observed |
| Alternate font (defect) | Crosstab display-rule text defaults to a different family from the report font — unify this in a rebuild |

### L.2 Colour
| Role | Value | Notes |
|---|---|---|
| Primary / brand bar | `#0664D0` | Banner background and avatar |
| Link / interactive text | `#0664D0` | Same hue as primary |
| Text primary | `#1B1D22` | |
| Text disabled | `#C3C8D0` | Greyed menu items keep full opacity |
| Chart label grey | `#6D7585` | Axis and legend text |
| App background | `#F4F4F6` | Canvas surround |
| Rail / subtle surface | `#F9FAFB` | |
| Surface / cards / panes | `#FFFFFF` | |
| Border / divider | `#DDDFE4` | 1px |
| Single-series accent | `#4398F9` | Default bar/line colour |
| Categorical palette (6 sampled, in assignment order) | `#EC80CE` pink · `#54B6A4` teal · `#F28D44` orange · `#97C03F` green · `#A570E8` purple · `#4398F9` blue | Sampled from a 6-category legend; the theme editor offers **8 fill swatches** and 8 line/marker swatches, so the palette is at least 8 long and the remaining entries were not sampled. Each mark is outlined in a ~10% darker shade of its fill (e.g. `#D272B7` under `#EC80CE`) |
| Dedicated **Missing** colour | theme-level swatch | A palette slot reserved for missing values — worth copying |
| Dedicated **Other** colour | grey | For the "Other" bucket |
| Gradient | 2-stop light → blue | For continuous colour roles |
| Semantic success / warning / error | **UNKNOWN** | No success, warning or error colour appeared in any observed state; validation uses red text with a red field outline, and severity counters are monochrome |
| Themes | Dark / **Light** (default) / High Contrast / custom | Theme switching is report-level |

### L.3 Layout
| Token | Value |
|---|---|
| Banner height | 38px |
| Toolbar height | 44px |
| Left icon rail width | 34px (expands to show labels) |
| Left pane width | 338px |
| Right pane width | 384px |
| AI side panel width | ~460px overlay |
| Rail tab hit height | 53px |
| Canvas gutter | ~16px around objects |
| Object padding | 8–16px; padding is an explicit per-object option (off by default) |
| Grid | Objects fill the page in a flex/grid layout with Extend/Shrink width and height flags; page direction vertical by default |

### L.4 Components
| Token | Value |
|---|---|
| Border radius | **2px** everywhere (buttons, inputs, cards) — a deliberately square, dense look |
| Border width | 1px, `#DDDFE4` |
| Shadows | None on panes or cards; elevation comes from borders. Menus and modals use a light drop shadow |
| Button height | 28px, padding 4px 8px |
| Icon buttons | 22–24px targets, ~16px glyphs |
| Input height | ~28px |
| Checkbox | ~16px |
| Table row height | Condensed by default; alternating row background on; horizontal and vertical rules on |
| Focus | Visible focus ring; disabled items remain focusable |

### L.4b Spacing, motion and layering (OBSERVED, session 18)

**Spacing** — base **4px**, rhythm **8px**. Measured distribution of left padding across app elements: `8px` dominant, then `16`, `6`, `4`, `2`, `32`. Scale: 4 · 8 · 12 · 16 · 24 · 32.

**Motion** — the product is almost motionless. Of 375 sampled elements **only 18 carry any transition**, and every one is the same:

| Token | Value |
|---|---|
| duration | **100ms** |
| easing | **`cubic-bezier(0, 0.5, 0.2, 1)`** |
| property | `background-color, border-color` |

There is **no entrance, exit or layout animation anywhere**. Motion exists only to soften hover and active colour changes. For a dense information tool this is a defensible and fast choice — copy the discipline, add `prefers-reduced-motion` support, and keep the set to three durations (100 / 160 / 240ms) on one easing.

**Layering** — observed z-indices are shallow (`0`, `1`, `2`, `4`, `5`); stacking is handled by DOM order and portals rather than a numeric scale. A rebuild should name its layers (`base` · `sticky` · `dropdown` · `overlayPane` · `modal` · `toast` · `tooltip`) and never write a raw z-index.

**Focus** — a **3px outline applied on `:focus-visible`** (programmatic focus does not trigger it), which is the correct modern implementation.

**Theme mechanism** — no `data-theme` attribute or theme class was found on the document root, and the app's own CSS custom properties were not separable from browser-extension variables in this environment. **UNKNOWN**; specify it rather than copy it.

### L.5 Visual language summary for the rebuild
Dense, flat, information-first: one saturated brand blue used sparingly for the banner and links, near-black text, 2px radii, hairline borders instead of shadows, generous use of grey surfaces to separate rails from canvas, and a soft mid-saturation categorical palette that stays legible against white. Copy the *system*; choose your own hues.

---

## M. Responsive Behaviour

**Directly observed:** the 1214×731 desktop viewport, plus two narrower effective widths reached by page zoom (see below). Real tablet and phone devices, and the PWA, were **not** observed.

**Observed from the stylesheets (OBSERVED):** breakpoints at **`min-width: 768px`, `992px`, `1200px`**, plus a **print** stylesheet.

| Breakpoint | Layout change | Components hidden | Components collapsed | Navigation | Charts | Tables |
|---|---|---|---|---|---|---|
| ≥1200px | Three-column: rail + left pane + canvas + right pane | — | Panes auto-collapse when unpinned | Full rail with optional labels | Canvas-rendered, redraw on resize | Virtualized, fit-to-width |
| 992–1199px | **UNKNOWN** | | | | | |
| 768–991px | **UNKNOWN** | | | | | |
| <768px | **UNKNOWN** | | | | | |
| Print | Dedicated stylesheet exists; page "Export as PDF" is the sanctioned path | | | | | |

**Narrow-width behaviour, measured by shrinking the effective CSS viewport (OBSERVED, session 10).** The browser window could not be resized in this environment — `resize_window` reported success while `window.outerWidth` stayed at 1600 — so the viewport was narrowed with page zoom instead.

| Effective width | Observed |
|---|---|
| ~1214px | Report title and toolbar icons share one 44px row |
| **~607px** | The report title moves to **its own row above the toolbar**; a **button-bar control overflows with ‹ › arrows**; the prompt bar stays in one row; the canvas is unchanged |
| **~405px** | The banner title truncates (*"SAS® Visual Analytics - E…"*); the **report prompt strip becomes horizontally scrollable**; the canvas is unchanged with a vertical scrollbar only |

**Nothing ever stacks.** Controls overflow or scroll sideways and the report canvas keeps its absolute layout at every width. Throughout, `window.matchMedia('(max-width:768px)')` stayed **false** while the chrome visibly re-laid-out — so this responsiveness is driven by **measured container width in JavaScript, not CSS media queries** (OBSERVED for the behaviour; INFERRED — confidence High — for the mechanism). The `768 / 992 / 1200` breakpoints in the stylesheet therefore do not govern what was seen here.

Real device and PWA rendering remain unobserved.

**Author-controlled responsiveness (OBSERVED):** per-object *Specify / Extend / Shrink* width and height flags, page-level *Avoid scrollbars*, report-level *Set fixed report size*, and a *Precision container* for absolute placement. These make layout behaviour an authoring decision rather than a purely automatic one — a pattern worth reproducing.

**Recommendation:** treat the authoring experience as desktop-only (≥1200px) and build a separate, genuinely responsive **read-only viewer** for tablet and phone.
