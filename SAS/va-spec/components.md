# Component Inventory

> Part of the Visual Analytics reverse-engineering deliverable. Sibling files: `application-map.md`, `screens.md`, `activities.md`, `components.md`, `visualizations.md`, `data-model.md`, `interaction-model.md`, `design-system.md`, `implementation-spec.md`, `screenshots/`.
> **Evidence labels:** OBSERVED (seen in the running app) · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.

## F. Component Inventory

| Component | Purpose | Location | Variants | States | Inputs | Outputs | Interactions | Responsive |
|---|---|---|---|---|---|---|---|---|
| App banner | Global identity + system actions | Top, full width, 38px | one | static | — | menu opens | click; opens side panels | Fixed height (UNKNOWN below 768px) |
| Report toolbar | Document-level actions | Below banner, 44px | edit / view variants | enabled, disabled (unsaved report) | — | commands | click; ⋮ opens menu | Fixed |
| Icon rail | Switch left panes | Left, 34px | 5 tabs; labels can be shown | selected, hover, focus ring | — | pane change | click; "»" toggles labels | Fixed |
| Side pane (left/right) | Hold panes | 338px left, 384px right | pinned / unpinned | pinned, auto-collapse | — | — | pin icon; collapse chevron; auto-collapse on canvas click | Fixed widths |
| Pane header + ⋮ | Pane-level config | Top of each pane | — | — | — | menu | click | — |
| Search / filter box | Narrow lists | Data, Objects, Options, Filters, dialogs | plain | empty, typing, cleared | text | filtered list | live filter; **text can persist across dialogs (defect)** | — |
| Data item row | Represent a column | Data pane | category / measure / aggregated / date / geography | default, hover (reveals Edit properties), **selected (a checkbox appears on every row once anything is selected, and the pane grows a `Clear selection (n)` link stating the count)**, badged (sensitive, outlier) | — | selection | click selects one; **Ctrl/Cmd+click toggles; Shift+click ranges**; selections span the Category/Measure groups and survive virtualised scrolling; right-click (20+ actions); hover card; **drag — single or multi-item** | `aria-selected` is lost for rows scrolled out of the virtualised list (defect 62) |
| Inline property editor | Rename/reclassify | Data pane | measure / category / date variants | expanded | name, classification, format, aggregation | item update | pencil toggles | — |
| Object library list | Insert objects | Objects pane | grouped, sortable | — | — | insert | double-click, drag | Scrolls to top after insert (defect) |
| Canvas | Host objects | Centre | page-scoped | empty, populated, maximized | drops | layout | drag, drop, resize handles, right-click | Scrolls; "Avoid scrollbars" option |
| Page tab strip | Switch pages | Above canvas | Basic / Hidden / Pop-up (eye-slash icon) | active, inactive | — | page change | click, ⋮ menu, "+" | Disappears in view mode when only one Basic page |
| Object frame | Wrap a visualization | Canvas | any object type | default, selected (border + handles), hover (⋮ + maximize), maximized, loading, error, capped | roles | queries | click, double-click, right-click, drag, resize, maximize | Extend/shrink width and height flags |
| Chart canvas | Render marks | Inside object frame | 30 graph types + 10 geo | placeholder, rendered, empty, capped | query result | pixels | hover tooltip, click select, double-click drill; **rendered to `<canvas>`**: the wrapper carries `role="application"` and a descriptive `aria-label` ("Frequency of Region, Bar chart"), but **no data values reach the DOM or the accessibility tree** | Redraws on resize |
| Data grid (crosstab / list table) | Tabular display | Inside object frame | crosstab (nested) / list table | with/without totals, row numbers, cell visualizations | rows | — | header menu (sort, aggregation, format, calculation), column resize, scroll | Fit columns to width ✓ |
| Role group | Bind columns | Data Roles | single-item / multi-item | required (red *), filled, greyed after limit | picks | assignment | "+ Add", right-click, drag | — |
| Type-filtered picker | Choose a column | Role "+ Add" | "Add Data Item" (single) / "Add Data Items" (multi, checkboxes) | empty ("No data items available for role.") | selection | assignment | click / check + Apply | — |
| Filter card | Constrain data | Filters pane | category (checkbox list + frequency bars), numeric (histogram slider), date (range slider) | default, edited, inverted, empty-result | values | filter | drag handles, check, ⋮ menu | — |
| Rank card | Top/Bottom N | Ranks pane | count / percent | — | count, measure | subset | selects + numeric entry | — |
| Control (prompt) | Reader-facing filter | Report strip / page strip / body | Drop-down, Button bar, List, Slider, Text input | required, empty, selected, cleared | user choice | filter or parameter | click, type, drag handles | Button bar overflows with arrows |
| Filter breadcrumb | Show active filters | Top of page | — | none / chips | — | remove filter | click chip ×, expand range chip | — |
| Property section | Group settings | Options pane | collapsible | expanded, collapsed, greyed | — | setting | chevron, controls | — |
| Dropdown / combobox | Choose a value | Everywhere | plain select, editable combo, colour picker, 9-point placement picker, dual-list picker | open, closed, typing, greyed | — | value | click; **Esc inside a dialog's dropdown closes the whole dialog (defect)** | — |
| Dual-list picker | Move items | Hierarchy, Custom sort, Show/Hide, Scope | — | — | selections | ordered list | arrows, double-click, reorder buttons | — |
| Expression editor | Author logic | Calculated items, filters, parameters | full / single-line | valid, invalid (count + squiggle), empty | text | expression | toolbar inserts skeletons; ⓘ popovers (**don't auto-close**) | Resizable split with Results grid |
| Results preview grid | Validate an expression | Expression editor | — | shows last valid result while invalid; "not available for aggregated measures" | — | rows | scroll | — |
| Modal dialog | Focused task | Overlay | small / large / blocking notice | — | fields | commit | OK/Cancel; × ; Esc | Centred, resizable (pop-up page) |
| Toast | Report a side effect | Bottom-left | with Undo | transient | — | undo | click Undo | — |
| Tooltip / hover card | Explain | Charts, data items, ⓘ icons | data tip / lineage card / help popover | — | — | — | hover or click | — |
| Context menu | Object/item actions | Right-click | object, data item, page tab, column header, canvas | items enabled/greyed, submenus | — | command | right-click; hover for submenu | Long menus scroll |
| Counter chips | Severity summary | Report Review | High / Medium / Low | 0..n | — | filter | click | — |
| Thumbnail card | Suggest or open | Suggestions, Landing | **suggestion card** (live `<canvas>` preview + caption + `••••` drag handle) / report card | no hover affordance at all — no ⋮, no insert button, no tooltip; caption truncates with no title | — | insert or open | **double-click inserts**; drag; right-click → Add to current page / Add to new page / Delete | Grid reflows |
| Container | Group objects in one frame | Canvas | Precision, Stacking (button-bar navigated), Tab, Prompt | empty (drop target), populated, one child visible (stacking/tab) | dropped objects | layout + navigation | **accepts objects by drag only** — double-click appends to the page instead (defect 27); the navigation control switches which child is visible | Children inherit the container box |
| In-object tab strip | Switch views of one analytic model | Inside an analytic object's frame | Decision tree: Decision Tree / Icicle / Variable Importance / Assessment | selected, scrollable | — | view change | click; ‹ › arrows scroll the strip | Arrows appear when the strip overflows |
| Model header line | State what the model fitted | Top of an analytic object | — | — | — | — | **Fit ▾** opens a criterion selector | Wraps |
| Viewport control cluster | Zoom and pan a free 2-D object | On hover, under ⋮ and maximize | map / network / path | shown on hover | — | viewport | fit, pan, zoom in, zoom out | — |
| Report prompt bar | Report-scoped controls | Above the page tab strip | any control types, in one row | expanded, **collapsed via ▲**, horizontally scrolled when narrow | user choices | report filters/parameters | click, type; ‹ › on an overflowing button bar | **Scrolls sideways; never stacks** |
| Insight popover | Flag outlier-driven numbers | Anchored to the viewer toolbar | — | idle, analysing (determinate bar), result | — | per-measure impact list | "Analyze Objects for Impact", then Details | — |
| What-if modal | Explore a forecast | Overlay | Scenario analysis / Goal seeking | Apply disabled until changed | dragged points, Adjust values, Bounds | revised forecast | drag points, Adjust ▾, Reset ▾, Bounds ▾ | Resizable |
| AI panel | Assistive chat | Right overlay | — | welcome, conversation | prompt | response | chips, type, attach | ~460px overlay |

**Stacking Container as the sanctioned "same chart, different measure" pattern (OBSERVED, session 6).** A production report offered an "Orders | Profit" toggle that looked like a parameter swapping a measure. It is a Stacking Container holding **two complete bar charts**, with a button bar navigating between them. Cost: one whole object per variant, each with its own roles and its own rank. A rebuild that supports a measure parameter directly would undercut this.

**Not present (OBSERVED absence):** breadcrumb navigation for pages, pagination controls (grids scroll virtually), a command palette, and any documented keyboard-shortcut surface (Help has no shortcut reference).
