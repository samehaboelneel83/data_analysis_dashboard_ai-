# SCREEN SPEC — #3 Home (route `/`)

Risk 🟢 (§20, LOW) · Roles: any member · Wave 3 structural, Wave 1 visual · Carries §14 rules 22, 27, 46
Source: §7 row 3, §8.1, §8.3, §9.1, §12, §14, §15, §16, §17, §18.1, §19, §20.

---

## A. Inventory

Everything below exists today and must survive. Home **modifies no data** (§7 row 3, "Data modified: none") — there is no form on this screen, which is why §13.1 has no Home entry.

| Element | Source | Classification |
|---|---|---|
| Page title "Home" (from the i18n title map) | §8.2 | [safe to restyle] |
| Primary CTA **New dashboard** → navigates to `/reports` | §7 row 3 | [safe to restyle] — the destination is the contract, not the button |
| Section: **Pins** (personal pinned tiles) | §7 row 3, §9.1 | [safe to restyle] |
| Section: **Recents** (recently opened dashboards) | §7 row 3, §17 | [safe to restyle] |
| Section: **My dashboards** | §7 row 3 | [safe to restyle] |
| Section: **Datasets** | §7 row 3 | [safe to restyle] |
| Section: **Explore** | §7 row 3 | [safe to restyle] |
| Collapse/expand control on each section | §18.1 item 10 | [safe to restyle] |
| Per-section collapse state persisted under `home.section.<Title>` | §16 | [value is an API contract] — the storage key is the section's **title text**; renaming a title silently resets every user's collapse state |
| `home.section.*` test ids | §16 | [value is an API contract] |
| Dashboard tile **"view" badge**, driven by server `my_capability === 'view'` | §12, §14.22 | [copy encodes a rule] — never re-derive the flag client-side (§19) |
| Dataset **"Live" chip** (DirectQuery) | §7 row 3 (🟡), §15 | [copy encodes a rule] — means *row count unknown*, never "0 rows" |
| Dataset list filtered by server visibility (own, unowned, shared, or reachable through a readable report) | §14.27 | [copy encodes a rule] — a dataset absent here but visible inside a dashboard is intended, not a bug |
| Full-page **LoadError** branch | §7 row 3 (🔴) | [copy encodes a rule] — must stay a distinct error, never an empty state |
| **Pins error shown as a separate alert**, page still renders | §7 row 3 | [copy encodes a rule] — a pins failure is non-fatal |
| Per-section empty states | §7 row 3 | [safe to restyle] — exact strings not given in the document |
| Any "not found" wording | §14.46 | [copy encodes a rule] — 404 never 403; never imply "exists but not yours" |

Out of scope for this screen (they belong to the shell, Wave 2): rail, workspace tree, top bar, notifications bell, account/theme/language/direction menu, command palette (§8.2).

---

## B. States

**Components.** Home currently hand-rolls its states instead of using the shared ones (§18.1 item 2). Adopting `LoadingState`, `EmptyState` and `LoadError` is permitted under §19 CHANGE-WITH-CARE, **provided the three-state distinction and the retry affordance survive** — and the `loadError` branch stays full-page (§7 row 3, 🔴).

| State | Content | Component |
|---|---|---|
| **Default** | Five sections — Pins, Recents, My dashboards, Datasets, Explore — each collapsible, each remembering its own collapse state. Dashboard tiles may carry a "view" badge; dataset entries may carry a "Live" chip. Primary CTA: New dashboard. | — |
| **Loading** | Today: plain text, no skeletons (§7 row 3, §18.1 item 10). Target: `LoadingState`, or skeletons (explicitly SAFE per §19). No partial render of real data while loading. | `LoadingState` |
| **Empty** | Not one page-level empty — **per-section** empties (§7 row 3). Each section shows its own message and, where one exists, a way forward (e.g. the Datasets section's two CTAs pattern on screen #4). Sections stay visible when empty; do not collapse or hide them. | `EmptyState` |
| **Error + retry** | Two distinct failures. (1) **Page load fails** → full-page `LoadError`, never an empty state (§7 row 3 🔴; §23 risk 3). (2) **Pins fail** → a separate inline alert; the other four sections render normally (§7 row 3). | `LoadError` (page) + inline alert (pins) |
| **Permission-reduced** | Home has no admin gate — it is member-only (§8.1), so no section is hidden by role. What changes is *content*: the dataset list is filtered by the server's visibility rule (§14.27); dashboards the user can only read show the "view" badge (§12). New dashboard stays available — every member may create (§12). Render this as the default board, not a separate layout. | — |

**Valid retry codes here.** The only widget-level retry the document permits anywhere is `source_unavailable` and `quota` (§9.1, §15) — a generic retry is forbidden because it hides deterministic refusals. Whether those codes can occur on Home depends on whether the pinned tiles fetch widget data; see *needs verification*. The page-level `LoadError` retry is separate and always valid.

---

## C. RTL notes

**Must mirror** (app-wide direction is real and first-class, §5.1; `DirectionContext`):
- Page and section layout, card order, text alignment, padding/margins.
- Navigational and disclosure arrows — section collapse chevrons, "open" affordances (§21, "arrows flipped").

**Must not mirror:**
- **Trend arrows** — up/down indicators keep their direction (§21, "arrows flipped, trend arrows not").
- **Chart surfaces**, which are pinned to LTR (`svg.recharts-surface { direction: ltr }`, §5.1); charts are mirrored through their own axis options, not by flipping the SVG.
- A widget's own `rtl` setting, where one applies: only an explicit `true` overrides the app direction; a stored `false` means "never set" (§14.44). Never add a global RTL switch that writes into widget configs.

**Conditional:** if Home's dataset entries show a file size in bytes, the `ltr()` bidi wrapper from §7 row 4 applies to that number. §7 row 3 does not say whether Home displays sizes — see *needs verification*.

**Chrome only:** ~170 chrome strings are translated; content stays English (§23 item 10). Do not design as though dataset or dashboard names will be Arabic.

---

## D. Stitch prompts

### D.1 — Default state (paste as-is)

```
Design the Home screen of Datalytics, a self-hosted enterprise business-intelligence
platform. Route: /. Audience: any signed-in member. Purpose: resume work.

LAYOUT REQUIREMENT — exactly five collapsible sections, no more, no fewer:
1. Pins — the user's personal pinned tiles.
2. Recents — dashboards the user recently opened.
3. My dashboards — dashboards the user owns or has been granted.
4. Datasets — datasets visible to this user.
5. Explore — entry points to the rest of the product.

Each section: its own heading, its own collapse/expand control, and its own empty
message. Sections remain visible when empty. Section order may be rearranged;
section TITLES must keep their current wording.

One primary call to action on the page: "New dashboard". It navigates away to the
dashboard list. It does not open a creation form on this screen.

Element details that must appear:
- Dashboard tiles may carry a small "view" badge meaning the user can read but not
  edit that dashboard.
- Dataset entries may carry a "Live" chip. "Live" means the row count is UNKNOWN.
  Never render "0 rows" or any row count for a Live dataset.
- Nothing on this screen creates, edits or deletes anything. Do not add reorder,
  resize, rename, delete, upload or share controls.

The page must not exist anywhere else in the design: no left rail, no top bar, no
notification bell, no account menu, no search — those are a separate shell design.
Design the page content area only.

NO NEW FEATURES, NO INVENTED NAVIGATION. Do not add sections, filters, tabs, charts,
KPIs, onboarding, search, settings, or links to screens not listed above.

--- CONSTRAINTS (obey on every screen) ---
1. Security is enforced by the server; the UI only mirrors it. Never show a control the server would refuse.
2. A view-only user gets no editing affordance anywhere — no left rail, no toolbar, no properties panel; one mode toggle is the only switch.
3. Subscribe is the exception: it stays visible to view-only users and never moves inside an edit-only toolbar.
4. Loading, empty and error are three distinct states. An error must never be drawn as an empty state.
5. "Try again" appears only when a data source was unavailable or a quota was hit. Never add a generic retry.
6. Secrets (embed secret, API key) are shown once at creation and never redisplayed.
7. Never distinguish expired / revoked / never-existed links, or "no permission" from "not found". One identical message.
8. Dropdown LABELS may be reworded. Dropdown OPTION VALUES may not — never rename an aggregation, level, mode or type value.
9. Settings-panel group titles are fixed strings, and every group must stay reachable from some tab.
10. Reproduce verbatim, never soften or shorten: the org-unit delete warning; "no dashboards are deleted"; "outputs are kept"; "recipients are not told"; "these rules do not apply to Ask AI"; the row-rule overlap notice; "columns cease to exist"; "structural, not access"; the pre-aggregated-dataset hints.
11. A folder's lock icon means "hidden from the menu", not "secured". Never present it as access control.
12. A blank quota field means unlimited; an empty embed origin list means open to any site. Never imply the opposite.
13. Shared and embedded pages are read-only dead ends: no navigation, no export, nothing saved, one error message.
14. Keep every route, URL parameter and page anchor exactly as it is — deep links and bookmarks depend on them.
15. Keep each rail entry's visibility rule. Never advertise a page a role cannot open.
16. The dashboard canvas is a fixed 12-column grid. Changing its geometry reflows every saved dashboard.
17. The chart palette lists exactly the chart types the product supports. Do not add, remove or invent types.
18. Live ("DirectQuery") datasets have an unknown row count and lose ten features. Never show them "0 rows" or offer those features.
19. Dashboards autosave: no Save button, no unsaved-changes prompt, and the "someone else saved" banner warns but never blocks.
20. Sensitivity badges, page tabs and the filter bar (even when empty) carry meaning. Never remove them for tidiness.
21. Do not add any new export, download or "export everything" control.
22. Free to change: colour, type, spacing, icons, layout, card and table styling, illustrations, labels, and help text that states no rule.

Support both light and dark themes, and both left-to-right and right-to-left
layouts. In RTL, mirror the layout and the collapse chevrons, but do not mirror
trend arrows.
```

### D.2 — Three one-line state prompts

1. **Loading** — `Same Home screen, loading state: the five section headings in place, skeleton placeholders instead of content, no real data, no error or empty messaging anywhere.`
2. **Empty** — `Same Home screen, first-run state: all five sections present and expanded, each showing its own empty message and next step, no skeletons, no error styling.`
3. **Error + retry** — `Same Home screen, two error variants on one board: (a) the whole page replaced by a full-page load-error with a retry action; (b) the page rendering normally with only the Pins section replaced by an inline non-blocking alert.`

*(The permission-reduced state needs no board of its own: it is the default board with "view" badges on some dashboard tiles and a shorter dataset list.)*

---

## E. Do-not-touch list (this screen)

| Item | Cited |
|---|---|
| The `loadError` branch — keep it as a full-page error, distinct from empty, on every failure path | §7 row 3 (🔴); §19 CHANGE-WITH-CARE; §23 risk 3 |
| The pins failure staying non-fatal and separate from the page error | §7 row 3 |
| The "Live" chip meaning "row count unknown" — never substitute 0 or a count | §7 row 3 (🟡); §15; Constraint 18 |
| `my_capability` / ownership flags — read them from the server, never re-derive | §12; §19 DO-NOT-CHANGE |
| Dataset visibility filtering — it is the server's rule, not a UI filter | §14.27 |
| Any "not found" wording — never imply the object exists but is off-limits | §14.46 |
| Route `/` itself: it must not 404, and it stays the landing target for login, SSO callback, schema-browser import, and a failed admin/super-admin guard | §8.1, §8 post-action navigation |
| Section **titles** — they are the localStorage collapse key `home.section.<Title>` and carry test ids. Reordering sections is explicitly safe; renaming them is not | §16; §19 SAFE ("section ordering on Home") |
| Recents comes from opening a dashboard, which is recorded server-side. Do not replace "open" with a preview or modal that never reaches the dashboard route | §17 (`recent_views`) |
| Home writes nothing. Do not add pin reorder/resize/unpin here — those live on the Datasets screen and carry the dense `position` renumbering and `size ∈ s\|m\|l` contracts | §7 rows 3 and 4; §13.2; §15 |
| If any refresh affordance is added, it must bump `refreshNonce` | §16 |

---

## Needs verification

1. **Do Home's pinned tiles fetch widget data, or are they links/previews?** §7 row 4 explicitly lists "per-pin widget data" for the Datasets screen; §7 row 3 lists only "pins" for Home, and §16's five `CrossFilterProvider` mounts name "Datasets pins", not Home. This decides whether `source_unavailable` / `quota` + "Try again" are reachable on Home at all.
2. **The literal section title strings.** The document names the sections (pins, recents, my dashboards, datasets, explore) but never quotes the rendered titles — and those titles are the `home.section.<Title>` storage key (§16).
3. **Do Home's dataset entries show a file size?** The `ltr()` bidi wrapper on byte sizes is documented for screen #4 only (§7 row 4).
4. **The per-section empty-state copy.** §7 row 3 says "per-section empties" without giving any string.
5. **What "Explore" contains.** §7 row 3 names the section; no element-level description exists anywhere in the document.
6. **Whether Home shows any cross-filtering or interactivity on pinned tiles.** Not stated; §16's provider list suggests not, but it is not asserted either way.
