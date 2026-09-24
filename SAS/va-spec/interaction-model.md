# Interaction Model

> Part of the Visual Analytics reverse-engineering deliverable. Sibling files: `application-map.md`, `screens.md`, `activities.md`, `components.md`, `visualizations.md`, `data-model.md`, `interaction-model.md`, `design-system.md`, `implementation-spec.md`, `screenshots/`.
> **Evidence labels:** OBSERVED (seen in the running app) · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.

## H. Interaction Model

### H.1 Pointer semantics (OBSERVED)
| Gesture | Target | Behaviour |
|---|---|---|
| Single click | Chart mark | Select/deselect; tooltip card; filters or highlights linked objects |
| Single click | Object frame | Select object → drives every right-pane tab |
| Single click | Canvas background | Deselect; auto-collapses unpinned panes |
| **Double click** | Chart mark (view mode) | **Triggers page links / drill** — a single click never does |
| Single click | **Underlined axis label** on a hierarchy | **Drills down one level.** Text-object hyperlinks also open on a single click; only chart *marks* require the double-click |
| Double click | Objects-pane entry | Insert object at the next free slot |
| Double click | Template / list-dialog row | Commit the selection (single click only highlights — a recurring trap) |
| Double click | Dual-list item | Move it across |
| Right click | Object, data item, page tab, column header | Context menu (20–25 items, submenus, greyed entries) |
| Hover | Data item row | Reveals "Edit properties" pencil and a lineage card |
| Hover | Chart mark | Data tip listing every assigned role |
| Hover | Object frame | Reveals ⋮ and maximize affordances |
| Drag | Data item → object / canvas / control strip | Assign role, create object, or create a prompt |
| Drag | Object edge / corner | Resize within the layout grid |
| Drag | Slider handle, overview-axis handle, filter range | Adjust a range (snaps to integers) |
| Scroll | Grids and long menus | Virtualized scrolling (grids are canvas-rendered) |

### H.2 Selection model
Single-select for chart marks and objects; multi-select checkboxes inside List controls and category filters. Selections persist across an edit↔view mode switch. Every automatic-action mode switch **clears control selections**.

**Data pane selection (OBSERVED, session 13 — corrects two earlier notes).** Click selects one; **Ctrl+click and Cmd+click toggle an item in or out**; **Shift+click selects a range**. Mixed selections **may span the Category and Measure groups**, and a selection **survives virtualised scrolling** — rows scrolled out of view stay selected and are carried by a later drag. Checkboxes appear on **every** row as soon as anything is selected, and the pane grows a **`Clear selection (n)`** link stating the count. The earlier notes that "ctrl-click didn't multi-select" and that "the checkbox only renders on hover" were both wrong; the first came from a dead click coordinate on the list's clipped last row.

### H.2b Drill-down (OBSERVED, session 6)
A hierarchy in a category role turns the axis labels into links. A single click drills one level; the object grows **its own breadcrumb** (`All Order Date Hierarchy › 2014 ˅`) with a level menu, and that breadcrumb **truncates to the current level when the object is narrow**. Drill is **per object** — nothing else on the page follows it.

### H.3 Undo / redo (a strength worth copying)
Undo works in **view mode as well as editing** (OBSERVED: *"Undo: Change Continent Selector from North America to Europe"*), so readers can step back through their own exploration — a strong pattern most viewers lack. Undo labels are fully descriptive and expose the exact operation: "Undo: Assign Customer Age, Sales to Crosstab - Region 1", "Add section with template", "Change label on data item from X to Y", "Change the option showRowNumbers for List table - City 1 to true". Rejected inputs create **no** undo entry. Redo is present. No auto-save of user edits during a session, but unsaved state is persisted for crash recovery.

### H.3b Drag-and-drop semantics (OBSERVED, session 13)

Drag is the product's primary construction gesture and it carries a **three-zone target model** — empty canvas, the gutter around an object, and the object itself — plus role slots and role chips. The full table, the multi-item drop resolver and the silent-refusal defects are in `visualizations.md` §G.2e–G.2f. Two interaction facts belong here:

- **A drop on an object's body resolves to a role, not to layout.** A drop *past* the object's border, in the canvas gutter, splits the layout instead. There is no in-object edge zone — 8px inside the border still behaves as a body drop.
- **Refusals are silent in both directions.** A body drop the resolver cannot place, and a type-mismatched drop on a role slot, both produce no change, no toast and no undo entry.

**Seven undo grammars exist for one operation family** — `Add <name> with data items <list>` (canvas drop), `Add object <name>` (Suggestions insert), `Replace <old> from <object> with <new>` (body drop), `Assign <item> to <object>` (role-slot drop), `Reorder items of <object> in <role> role` (chip reorder) `New page <name> with object types: <type>`, and — the least informative — `Change option "fitLineType"`, which exposes the **raw internal camelCase key** and drops both the object name and the new value (defect 71). Each is readable on its own — the product's real strength — but they share no sentence pattern (defect 63).

### H.4 Progressive disclosure
Panes auto-collapse unless pinned; property sections are collapsible; advanced settings hide behind ⋮ menus; the expression editor is the escape hatch behind every filter and calculation; a settings search box spans the Options pane.

### H.5 Confirmation and safety
Confirmations appear **only** for closing unsaved work and for actions that require a save. Destructive configuration changes (deleting links by switching action modes) use a toast with Undo instead of a prompt. Deleting objects and pages is immediate, undoable, and never confirmed.

### H.6 Filtering model (the product's core semantic)
Three independent layers, which the UI does not unify:
1. **Object filters** — defined per object in the Filters pane; can be promoted to **common filters** reusable across objects and pages.
2. **Controls (prompts)** — report-level (all pages), page-level (all objects on the page, cascading into other controls), or body-level (filter nothing until explicitly linked).
3. **Actions** — object links (Filter or Linked selection), page-wide automatic modes, page/report/URL links.

**Critical for reimplementation — and the disclosure is asymmetric (OBSERVED on a production report, session 6).** In the **editor's** Filters pane, filters arriving from controls and links are **invisible**. In the **viewer's** side pane they *are* disclosed: selecting a filtered object shows `Permanent Filters: None` and `Interactive Filters: Product Category = 'Clothes'`. So the reader can audit the filter stack and the author configuring it cannot. A rebuild should show one merged, inspectable filter stack in **both** modes.

**Missing values are handled inconsistently across the three layers (OBSERVED):**
| Surface | Default for missing |
|---|---|
| Object filter (numeric, category, date) | **Included** (`OR Missing(x)` in the generated logic) |
| List control | Present as a selectable value "(missing values)", unselected |
| Slider control | **Excluded, even at full range**, until "Missing values option" is enabled |
| Custom category grouping | Silently folded into "Other" |
| Invert selection | Also inverts the include-missing setting |

**Relative dates:** absent from filters and controls. Only expressions provide `Now()` and the five periodic functions. **A reimplementation should add first-class relative ranges (last N days, MTD/QTD/YTD, rolling windows).**

### H.6b Control cascades, and what the viewer discloses (OBSERVED, session 10)

**A control can filter another control.** In a parameter report, the *Benchmark Country Selector*'s own Filters pane read `Interactive Filters: Continent Name = 'Asia'`, and its value list held exactly the seven Asian countries. A control is an ordinary filter target like any chart, and the cascade is disclosed in the viewer (never in the editor — defect 11).

**A parameter change reprices everything downstream in one pass.** Switching the benchmark from Russian Federation to China recomputed the `+/- vs Benchmark` column for every row, re-sorted the bar chart and rescaled its axis, and produced one undo entry: *"Undo: Change Benchmark Country Selector from Russian Federation to China"* — the same label grammar as every other undo.

**Required controls drop the clear affordance.** An optional drop-down's value list opens with **`Clear filter`**; a control marked **(required)** offers no such entry. There is no "(All)" member either way.

### H.7 Keyboard
No shortcut reference exists in Help. Observed: Esc closes menus and dialogs — and **inside a dialog's dropdown it closes the entire dialog, discarding work** (a defect to avoid). Enter commits inline fields. Tab focus rings are drawn. Full shortcut map: **UNKNOWN**.

**Correction (OBSERVED, session 10).** "No documented keyboard-shortcut surface" is false as an absolute. The **Comments pane** ends with a literal instruction: *"Press **Ctrl+Enter** to expand or collapse replies for a comment. Press **F2** to interact with the comment or reply."* A second appears in the **Opened reports** panel, where every row carries *"Press **Delete** to close the report"* and the list ends with **Close all reports**. These are the only shortcuts the product discloses anywhere, and each is discoverable only by opening the one surface that prints it. Help still carries no shortcut reference. For the rebuild: the shortcuts should exist **and** be listed in one place.
