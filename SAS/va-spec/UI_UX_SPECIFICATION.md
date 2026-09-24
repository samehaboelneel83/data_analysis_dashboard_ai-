# UI/UX Specification — analytics platform

A build-ready design specification. Every measurement is from the live subject product; every *rule* is the one I would write for your platform, which in places is deliberately not what the subject does. Where the two differ, the subject's behaviour is shown as **Observed** and the rule as **Spec**.

Companion documents: `RECOMMENDATIONS.md` (product judgement) · `PLATFORM_BLUEPRINT.md` (engineering) · `screens.md`, `components.md`, `interaction-model.md`, `design-system.md` (raw findings).

---

## 1. Design principles

Eight principles, each earned from something that worked or failed across seventeen sessions.

1. **Typed, not free-form.** The user picks a column; the system decides where it can go. A date cannot land on a measure axis. This is what lets a novice build a correct chart in four clicks.
2. **Render immediately, refine after.** Drop one field and something appears — a measure auto-fills with a row count, an unconfigured object draws example data. Never show an empty frame and a form.
3. **Say the number behind the picture.** Every object that samples, caps, bins or drops rows declares it in its header, in the same words, every time.
4. **Never act silently.** Every refusal has a reason. Every substitution is announced. Every disabled control says which of its causes applies.
5. **Everything is reversible, and the reversal is a sentence.** One undo grammar — *verb, item, role, object, value* — across the whole product, including for readers.
6. **Disclosure is symmetric.** Whatever a reader can learn about why a number looks the way it does, an author can learn too. And vice versa.
7. **Density with air.** This is a professional tool used for hours. Small type, hairline borders, 8px rhythm, no decorative chrome — but never crowded to the point of misreading.
8. **One model, two renderings.** Every visual emits pixels and an accessible projection from the same scene graph, so they cannot drift.

---

## 2. Information architecture

### 2.1 Top-level surfaces
```
Landing  ──▶  Report (Edit)  ⇄  Report (View)
   │              │
   │              ├── Page 1..n   (Basic | Hidden | Pop-up)
   │              └── Object 1..n
   └── Content browser (Recent · Favorites · My Folder · Shared · Recycle Bin · Recommendations)
```

### 2.2 The two-mode model
| | Edit | View |
|---|---|---|
| Purpose | construct | consume |
| Left rail | Data · Objects · Outline · Suggestions · Review | — |
| Right pane | Options · Roles · Actions · Rules · Filters · Ranks | Roles · Rules · Filters · Ranks · Comments (read-only) |
| Undo | full | **yes — reader interactions are undoable too** |

**Spec:** one mode switch, always visible, always one click, and state (selections, drill, prompts) survives the switch in both directions.

### 2.3 Navigation rules
- **Spec:** every surface is addressable — `/reports/{id}/pages/{pageId}?mode=view&filters=…`. Back and forward work. Deep links open exactly what was shared.
- **Observed (defect 24):** the subject has one route for the entire application, no history, no deep links. This cannot be retrofitted; decide it on day one.
- Page tabs appear above the canvas; hide the strip in View mode when a report has one Basic page.
- Pop-up pages open as modals from links, never as navigation.

---

## 3. Layout system

### 3.1 Application shell
```
┌──────────────────────────────────────────────────────────┐
│ Banner                                            38px   │
├──────────────────────────────────────────────────────────┤
│ Report toolbar                                    44px   │
├────┬──────────────┬──────────────────────┬───────────────┤
│Rail│  Left pane   │       Canvas         │  Right pane   │
│34px│    338px     │        fluid         │     384px     │
└────┴──────────────┴──────────────────────┴───────────────┘
```

| Region | Size | Behaviour |
|---|---|---|
| Banner | 38px | fixed; identity, global search, notifications, help, account |
| Toolbar | 44px | document actions; title left, actions right |
| Icon rail | 34px | 5 tabs, ~53px hit height; a **»** toggle reveals labels |
| Left pane | 338px | pinned or auto-collapse on canvas click |
| Right pane | 384px | same |
| Canvas | fluid | ~16px gutter around objects |
| AI / assistant panel | ~460px | overlay, not a pane |

**Spec:** panes are resizable and their width persists per user. The subject's are fixed — a 338px data pane truncates most real column names.

### 3.2 Canvas layout
- Objects fill the page in a flex/grid layout; page direction vertical by default.
- Per object: *Specify / Extend if available / Shrink if necessary* for width and height.
- Page: *Avoid scrollbars*. Report: *Set fixed report size*. Plus a **Precision container** for absolute placement.

**Spec:** keep these author-controlled flags — layout behaviour should be an authoring decision — and add a page-level **reflow mode** for narrow viewports (§11).

---

## 4. Design tokens

Measured at 1214×731, light theme. Substitute your own hues; copy the *system*.

### 4.1 Type
| Token | Value |
|---|---|
| `font.family.ui` | one humanist sans throughout (Inter / Source Sans 3 / system-ui) |
| `font.size.xs` | 12px — small control text, captions |
| `font.size.sm` | 14px — **base body, buttons, inputs, list rows** |
| `font.size.md` | 16px — pane titles, rail labels |
| `font.lineHeight.default` | 1.4 (22.4px at 16px) |
| `font.weight.regular` / `.bold` | 400 / 700 — **no light weights** |
| `font.family.chart` | must equal `font.family.ui` |

> **Observed defect 25:** crosstab display-rule text defaults to a different family from the report font. One type system, no exceptions.

### 4.2 Colour
| Token | Value | Use |
|---|---|---|
| `color.brand` | `#0664D0` | banner, links, primary actions |
| `color.text.primary` | `#1B1D22` | |
| `color.text.secondary` | `#6D7585` | axis and legend labels |
| `color.text.disabled` | `#C3C8D0` | |
| `color.surface` | `#FFFFFF` | panes, cards, menus |
| `color.surface.subtle` | `#F9FAFB` | rail |
| `color.background` | `#F4F4F6` | canvas surround |
| `color.border` | `#DDDFE4` | 1px hairlines — **elevation comes from borders, not shadows** |
| `color.accent.single` | `#4398F9` | default single-series mark |
| `color.categorical[0..7]` | `#EC80CE` · `#54B6A4` · `#F28D44` · `#97C03F` · `#A570E8` · `#4398F9` · (+2 unsampled) | assignment order; each mark outlined ~10% darker than its fill |
| `color.data.missing` | reserved slot | **a dedicated Missing colour — copy this** |
| `color.data.other` | grey | the "Other" bucket |
| `color.gradient.continuous` | 2-stop light → brand | continuous colour roles |
| `color.status.success/warning/danger` | **UNKNOWN in subject** | **Spec: define all three.** The subject has none; validation is red text plus a red outline and severity counters are monochrome |

### 4.3 Spacing
Base **4px**, rhythm **8px**. Observed distribution: `8px` dominant, then `16`, `6`, `4`, `2`, `32`.

`space.1`=4 · `space.2`=8 · `space.3`=12 · `space.4`=16 · `space.6`=24 · `space.8`=32

### 4.4 Shape, border, elevation
| Token | Value |
|---|---|
| `radius.default` | **2px** everywhere — buttons, inputs, cards |
| `border.width` | 1px |
| `elevation.flat` | none — panes and cards use borders |
| `elevation.overlay` | light drop shadow — menus, modals, popovers only |

### 4.5 Motion
**Observed:** only 18 of 375 sampled elements have any transition, and all use the same one:

```
duration: 100ms
easing:   cubic-bezier(0, 0.5, 0.2, 1)
property: background-color, border-color
```

No entrance, exit or layout animation anywhere.

**Spec — keep this discipline.** Motion exists to soften state change, not to narrate. Token set:
`motion.fast` 100ms (hover, active, focus) · `motion.default` 160ms (disclosure, pane collapse) · `motion.slow` 240ms (modal in/out). Same easing. **Respect `prefers-reduced-motion`** and drop to 0ms.

### 4.6 Layering
Observed z-indices are shallow — `0`, `1`, `2`, `4`, `5` — with stacking handled by DOM order and portals.

**Spec — name the layers:** `base` 0 · `sticky` 100 · `dropdown` 200 · `overlayPane` 300 · `modal` 400 · `toast` 500 · `tooltip` 600. Never write a raw z-index.

### 4.7 Sizing
| Token | Value |
|---|---|
| `size.control.height` | 28px (buttons, inputs, selects) |
| `size.control.padding` | 4px 8px |
| `size.icon.glyph` | 16px |
| `size.icon.target` | 22–24px |
| `size.checkbox` | 16px |
| `size.row.condensed` | list and grid rows, condensed by default |

> **Spec:** 24px is below the 44px comfortable touch target. Under the touch breakpoint, scale `size.icon.target` to 44px.

---

## 5. Component library

Each entry: **anatomy → variants → states → behaviour → accessibility**. Components marked ★ are the ones that carry the product.

### 5.1 Application chrome

**App banner** — identity · global search · notifications · help · account avatar. Fixed 38px. *Spec:* at narrow widths the product title truncates with an ellipsis; never wrap the banner.

**Report toolbar** — title (left) · action cluster (right) · overflow ⋮. 44px.
*States:* every action is enabled, or disabled **with a reason** (§7.5).
*Spec:* at narrow widths the title moves to its own row above the toolbar (the subject does this and it is the right call).

**Icon rail** ★ — 5 tabs, 34px wide, ~53px hit height, **»** toggles labels.
*States:* selected (left accent bar + tint), hover, focus ring.
*A11y:* `role="tablist"`, arrow-key navigation, `aria-selected`.

**Side pane** — header (title + ⋮) · body · pin/unpin · collapse chevron.
*Variants:* left (338px), right (384px), overlay (~460px).
*Behaviour:* auto-collapse on canvas click unless pinned.
*Spec:* resizable, width persisted per user.

### 5.2 Data

**Data item row** ★ — icon (classification) · label · distinct count · badges (sensitivity, outlier) · hover affordances.
*Variants:* category · measure · aggregated measure · date · geography · hierarchy.
*States:* default · hover (reveals edit) · **selected (checkbox appears on every row once anything is selected)** · badged · dragging.
*Behaviour:* click selects one; **Ctrl/Cmd+click toggles; Shift+click ranges**; selection spans classification groups and **survives virtualised scrolling**; right-click opens a 20+ item menu; drag — single or multi-item.
*A11y:* **Spec — the selection must survive virtualisation in the accessibility tree.** The subject's `aria-selected` exists only on rendered rows, so a live three-item selection can report as zero (defect 62). Maintain a live region announcing "*3 items selected*".

**Hover card** — name · distinct values · **name in data** (physical column) · format · sensitivity explanation in plain language.
*Spec:* this is the mapping surface. Show both halves of the mapping always.

**Selection summary** — `Clear selection (n)` at the foot of the pane.
*Spec:* also expose the count as a live region.

### 5.3 Objects

**Object frame** ★ — title · hover ⋮ · maximize · resize handles · body · footer notices.
*States:* default · selected (border + handles) · hover · maximized · **loading** · **error** · **truncated** · **placeholder (example data)**.
*Behaviour:* click selects; double-click drills; right-click menu; drag to move; drop target for data items (§6.2).

**Object header line** ★ — for analytic objects: `<Title> · Event: <level> ▾ · Fit: <statistic> <value> ▾ · Observations: <used> of <total> · <Action> ▾`.
*Spec:* **generalise this to every object.** Any object that samples, caps, bins or drops rows prints `Rows: <used> of <total>` in the same slot, in the same words. This single pattern retires defects 3, 6, 59, 60, 75.

**Chart canvas** — the drawing surface.
*Spec:* emits **both** a painter pass and an ARIA projection from one scene graph (§10).

**Data grid** — crosstab (nested headers) or list table. Column header menu: sort · replace · remove · aggregation · format · new calculation · cell visualization · indent · totals · row numbers.
*Behaviour:* virtualised scroll, column resize, fit-to-width.

**In-object tab strip** — for analytic objects with several views of one fit (*Tree · Icicle · Variable Importance · Assessment*). ‹ › arrows when it overflows.

**Viewport control cluster** — fit · pan · zoom in · zoom out, on hover, for objects laid out in free 2-D space (map, network, path). Not for category/value grids.

### 5.4 Configuration

**Role group** ★ — label · required marker · items · `+ Add`.
*States:* required-unfilled · filled · greyed (single-item role at capacity) · **drop target**.
*Spec:* a required marker means *this role*. For "any one of these N", use a bracketed group marker and say which are outstanding — the subject puts `*` on four roles when one suffices (defect 72).

**Typed picker** — single (`Add Data Item`) or multi (`Add Data Items` + checkboxes + Apply). Empty state: *"No data items available for role."*
*Spec:* filter by type **and** semantic type. Never offer a latitude as a summable measure.

**Property section** — collapsible group in the Options pane, with a settings search box spanning the pane.

**Filter card** — category (checkbox list + frequency bars) · numeric (histogram slider) · date (range slider) · per-card ⋮.

**Rank card** — subset · count · rank-by · ties · All Other.

**Expression editor** — toolbar of skeletons · text area · inline error count · red squiggle · gutter marker · resizable results preview.
*Spec:* validate per keystroke, report position, keep the last valid result visible while invalid.

### 5.5 Controls (reader-facing)

**Drop-down · List · Button bar · Slider · Text input.**
*States:* empty · selected · **required** · cleared · overflowing.
*Behaviour:* an optional control's list opens with **`Clear filter`**; a **required** control omits it. Button bars overflow with ‹ › arrows.
*Spec:* controls are ordinary filter sources and may cascade — and the cascade must be visible in the filter stack.

**Report / page prompt bar** — controls in a row above the page tabs, collapsible by a ▲ chevron.
*Spec:* **stacks** below the breakpoint. The subject scrolls it sideways (defect 46).

### 5.6 Feedback

**Toast** — bottom-left, transient, with **Undo**. Used for reversible side effects.

**Modal** — small · large · blocking notice. Esc closes **only the innermost layer**.
> **Observed defect 14:** Esc inside a dropdown closes the whole dialog and discards the work.

**Tooltip / data tip** — hover, one row per assigned role plus data-tip values.

**Inline notice (ⓘ)** — object-level disclosure: truncation, unmapped values, fabricated ordering.
*Spec:* promote these from a tiny ⓘ to a visible line in the object header.

**Empty state** — icon · one sentence saying what this surface needs · a primary action.
> **Observed defect 48:** the Suggestions pane renders a disabled control and blank space.

---

## 6. Interaction patterns

### 6.1 Selection
| Gesture | Result |
|---|---|
| Click | select one |
| Ctrl/Cmd + click | toggle one in or out |
| Shift + click | select a range |
| Click a chart mark | select that mark (single-select) |
| Click a control value | apply a filter |

Selections persist across mode switches and across virtualised scrolling.

### 6.2 Drag and drop ★
A **three-zone target model**:

| Target | Result |
|---|---|
| Empty canvas | create an object (resolver, §6.3) |
| **Gutter around an object** | create an object, split in that direction |
| **Object body** | assign to a compatible role — replace a filled single role, append to a multi role |
| **Role slot** | assign to that role directly |
| **Chip inside a role** | reorder within the role |

*Spec additions:*
- **Fall through to the next compatible empty role** rather than no-op. The subject ignores a drop when its preferred role is full even though an empty compatible role exists (defect 58).
- **Show the drop target.** Highlight the receiving zone, name the role it will fill, and show an insertion indicator for reorder. *(The subject's mid-drag feedback could not be captured; specify it rather than copy it.)*
- Keyboard equivalent: focus a data item, `Space` to pick up, arrow to a role, `Space` to drop.

### 6.3 Automatic object selection
One resolver, called from every surface (canvas drop, object conversion, suggestions).

| Dropped set | Object |
|---|---|
| 1 category | bar (measure auto-filled with row count) |
| 1 category + n measures | bar, measures stacked into the measure role |
| 1 date + measure | time series |
| ≥2 categories | table, everything as columns |
| 2–3 measures | binned scatter / heat map |
| ≥4 measures | correlation matrix |

*Spec:* the resolver must (a) consult **semantic type**, never offering coordinates, years or identifiers as measures; (b) **explain its choice** on request; (c) be **deterministic** for the same input.

### 6.4 Undo ★
A command log over the document. **One sentence grammar:**

```
<Verb> <item> <preposition> <role> of <object> [from <old> to <new>]
```

Examples: `Assign Supplier Continent to Group of Bar – Supplier Country` · `Replace Frequency with Cost in Measure of Bar – Supplier Country` · `Change Fit line type of Scatter 1 from None to Linear`.

> **Observed:** seven competing grammars, the worst being `Change option "fitLineType"` — a raw internal key with no object and no value (defect 71).

Rules: every mutation produces exactly one entry; rejected input produces none; **dismissals are undoable too** (the subject's suggestion-card delete is not — defect 50); undo works in View mode.

### 6.5 Progressive disclosure
Panes auto-collapse unless pinned · property sections collapse · advanced settings behind ⋮ · the expression editor as the escape hatch behind every filter and calculation · a settings search spanning the Options pane.

### 6.6 Confirmation and refusal
- **Confirm** only destructive-and-irreversible actions and closing unsaved work.
- **Everything else** uses a toast with Undo.
- **Never no-op.** A refused action states why, in the object or beside the control.

---

## 7. State catalogue

Every object and pane implements all nine.

| State | Rule |
|---|---|
| **Empty (unconfigured)** | draw **example data** plus a central `Assign data` action, so the layout teaches the object |
| **Empty (no data matches)** | *"No data matches the current filters."* + a clear-filters action |
| **Loading** | spinner over the greyed placeholder; never a blank frame |
| **Partial** | first results drawn, remainder loading, stated |
| **Truncated** ★ | **visible header line**: `Rows: 3,000 of 748,213 — row limit`, plus a one-click *rank top N instead* |
| **Substituted** ★ | `Binned: 748K points rendered as a heat map` — never silent |
| **Error** | what failed, why, what to try; keep the object's identity and roles inspectable |
| **Refused** | reason beside the control: `not saved` · `no permission` · `not licensed` · `no content` · `nothing selected` |
| **Disabled** | as refused — **the cause is always named**. The subject has five causes behind one grey (defect 29) |

---

## 8. Content and microcopy

**Voice:** plain, specific, second person for actions, no exclamation marks, no blame.

**One naming function** produces the object title, the accessible name and any undo label. The subject has at least three and they disagree — a card reading `Department by Frequency` creates an object titled `Frequency of Department` (defect 54).

| Surface | Pattern | Example |
|---|---|---|
| Object title (auto) | `<measure> by <category>[ grouped by <group>]` | `Cost by Supplier Country grouped by Supplier Continent` |
| Accessible name | `<title>, <object type>` | `Cost by Supplier Country, Bar chart` |
| Undo | §6.4 grammar | |
| Truncation | `<used> of <total> — <reason>` | `646K of 2.3M — rows with missing values excluded` |
| Validation | `The value must be …` with the bound | `Bin count must be between 2 and 100.` |
| Empty pane | what it needs, then what it does | `Add data to see suggested charts.` |
| Refusal | reason first, then remedy | `Share is turned off for this deployment.` |

**Numeric limits are always stated in the control.** The subject states `Bin count (2-100)` in one place and silently rejects `0` and `9999` in another (defect 73).

---

## 9. Iconography

One line-weight set, 16px glyph on a 22–24px target, 1.5px strokes, square terminals to match the 2px radius. Classification icons (category · measure · date · geography · hierarchy) are the highest-traffic glyphs in the product — they appear on every data row, every role chip and every picker — so design those five first and test them at 16px on a `#FFFFFF` and a `#F9FAFB` surface.

---

## 10. Accessibility specification

This is where the subject is weakest and where a newcomer can win outright.

| Requirement | Spec |
|---|---|
| **Charts** ★ | every visual emits a painter pass **and** an ARIA projection from one scene graph: a real `<table>` of the plotted values, a one-sentence summary, and focusable marks in visual order. Non-negotiable, and cheap only if designed in on day one |
| Accessible names | one naming function (§8); never fall back to an internal object id |
| Selection | announced in a live region and correct under virtualisation |
| Keyboard | full operation without a pointer, including drag (§6.2), and a **discoverable shortcut map** — the subject discloses exactly two shortcuts, inside one pane (defect 23) |
| Focus | 3px `:focus-visible` outline, 2px offset, contrast ≥ 3:1 against both adjacent surfaces. *(Observed: the subject defines a 3px outline and applies it on `:focus-visible` — correct.)* |
| Contrast | text ≥ 4.5:1, UI and graphical objects ≥ 3:1. Verify the categorical palette against `#FFFFFF` **and** the subtle surface |
| Colour independence | never encode meaning in hue alone — pair with shape, pattern or a label. The subject's Model comparison greys the losing bar, which is good, but it is the only signal |
| Motion | honour `prefers-reduced-motion` |
| Theme | a genuine High Contrast theme, including a high-contrast basemap for maps |
| Targets | 44px under the touch breakpoint |

---

## 11. Responsive specification

**Observed:** the subject re-lays-out its chrome by **measured container width in JavaScript, not CSS media queries** (`matchMedia` never fired while the layout visibly changed). The report canvas **never reflows** at any width; the prompt strip scrolls sideways and the banner title truncates.

**Spec — container queries, and a real reflow mode.**

| Breakpoint | Shell | Canvas |
|---|---|---|
| ≥1200px | rail + left pane + canvas + right pane | as authored |
| 992–1199px | panes overlay instead of push | as authored |
| 768–991px | rail collapses to icons; one pane at a time | **reflow: single column, objects at minimum legible height** |
| <768px | View mode only; toolbar becomes an overflow menu; **prompt bar stacks** | reflow, vertical scroll |

Authors choose per page between **as-authored** (absolute placement preserved, pan/zoom below the breakpoint) and **reflow**. Print gets its own stylesheet and uses the export path.

---

## 12. Theming

Light (default) · Dark · High Contrast · custom brand.

- All tokens resolve through CSS custom properties on a single root scope; components never hardcode a hex.
- **Charts read the same tokens** — the theme must reach the drawing layer, not just the DOM.
- The **basemap follows the theme** (a high-contrast tileset under High Contrast). The subject does this and it is excellent.
- A theme editor exposes: report font, 8 fill swatches, 8 line/marker swatches, plus the reserved **Missing** and **Other** colours.
- Theme is a report-level property so a shared report looks the same for every reader.

---

## 13. Definition of done

A component ships when:

1. All nine states in §7 are implemented and screenshotted.
2. It uses only tokens — no literal colours, sizes or z-indices.
3. Keyboard operation is complete, and the focus ring passes contrast on every surface it sits on.
4. Its accessible name comes from the shared naming function.
5. Every refusal and every disabled state names its cause.
6. Every mutation emits one undo command in the §6.4 grammar.
7. If it renders data: truncation, substitution and population are disclosed in the header, and an ARIA projection exists.
8. It behaves at 360px, 768px and 1440px, and under `prefers-reduced-motion`.
9. Microcopy matches §8, including the numeric bound in any validation message.
10. Nothing in it fails silently.
