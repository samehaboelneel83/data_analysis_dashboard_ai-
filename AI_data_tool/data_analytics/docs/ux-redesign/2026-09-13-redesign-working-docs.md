# Datalytics — working documents

Source of truth: `2026-09-13-application-analysis.md`. Nothing here adds a feature, route or behaviour that document does not state. Items marked **rec.** are my recommendation, not the document's.

---

## 1. CONSTRAINTS CARD

> Paste verbatim into every Stitch prompt.

**DATALYTICS — CONSTRAINTS (obey on every screen)**

1. Security is enforced by the server; the UI only mirrors it. Never show a control the server would refuse.
2. A view-only user gets no editing affordance anywhere — no left rail, no toolbar, no properties panel; one mode toggle is the only switch.
3. Subscribe is the exception: it stays visible to view-only users and never moves inside an edit-only toolbar.
4. Loading, empty and error are three distinct states. An error must never be drawn as an empty state.
5. "Try again" appears only when a data source was unavailable or a quota was hit. Never add a generic retry.
6. Secrets (embed secret, API key) are shown once at creation and never redisplayed.
7. Never distinguish expired / revoked / never-existed links, or "no permission" from "not found". One identical message.
8. Dropdown **labels** may be reworded. Dropdown **option values** may not — never rename an aggregation, level, mode or type value.
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

*Source: §19 of the application analysis. Anything not covered here must be checked against §14 before it moves.*

---

## 2. SCREEN TRACKER

Risk is taken from §20 (screen-level), not §7 (element-level): LOW → 🟢, LOW–MEDIUM / MEDIUM → 🟡, HIGH / CRITICAL → 🔴. Wave 1 (visual layer: tokens, type, spacing, buttons, cards, tables, toasts, the three state components) applies to **all 32 screens**; the wave column carries the *structural* wave.

| # | Screen | Route | Risk | Roles | Primary CTA | Required states | §14 rules it carries | Wave |
|---|---|---|---|---|---|---|---|---|
| 1 | Login | `/login` | 🟡 | public | Sign in | busy labels; all errors as toasts (8 SSO codes); no empty | 47, 48 | not in §22 — **rec. W3** (§23 lists it "first") |
| 2 | SSO callback | `/sso/callback` | 🟡 | public | automatic | whole screen is the loading state; failure → `/login` | 48 | not in §22 — **rec. W3**, with Login |
| 3 | Home | `/` | 🟢 | member | New dashboard | loading text; full-page error; pins error separate; per-section empty | 22, 27, 46 | W3 |
| 4 | Datasets | `/datasets` | 🟡 | member | + Upload | loading; error; empty (two CTAs); no-match | 27, 46 | W3 |
| 5 | Upload | `/upload` | 🟡 | member | Upload | loading with operation name; inline per-file failure list; no empty | 1, 4 | not in §22 — **rec. W3** |
| 6 | Dataset detail | `/datasets/:id` | 🔴 | member; Share admin-only | Run analysis / Apply | page loading + error; per-section busy/error; file-not-found recovery | 3, 7, 8, 16, 17, 18, 36, 37, 39, 40, 58 | W4 |
| 7 | Dashboards | `/reports` | 🔴 | member | + New dashboard | loading; error; empty; no-match | 22 | W3 |
| 8 | Report builder (+ properties rail, renderer, share/embed/subscribe dialogs) | `/reports/:id` | 🔴 | member; edit / data / admin gates | Edit mode toggle | loading; error; stale-revision banner; per-widget error / empty / retry | 2, 6, 9, 11, 12, 16, 19, 20, 22, 23, 27, 32, 34, 35, 38, 41, 42, 43, 44, 45, 51, 54, 55, 56, 57 | W5 |
| 9 | Print | `/reports/:id/print` | 🟡 | member (own RLS) | Print / Save as PDF | loading; error; no empty-pages state | 9, 20, 23 | not in §22 — **rec. W5** (a renderer surface with its own cross-filter mount, §16) |
| 10 | Connections | `/connections` | 🔴 | member reads; admin acts | + New connection | loading; error (with reload); empty; no-match | 4, 5, 30 | W3 |
| 11 | Source review | `/connections/:id/review` | 🔴 | any member by URL; link admin-only | Run sync | loading; error; per-tab error; "nothing awaiting review" | 21, 37 | not in §22 — **rec. W5** (§23: "not to touch until later") |
| 12 | Ask AI | `/ask` | 🔴 | member | Send | inline error bubble; Pending bubble; two distinct empties ("no data" vs "no scope") | 15, 46 | W4 |
| 13 | Insights hub | `/insights` | 🟡 | member | pick a dataset | loading; error; empty; DirectQuery cards disabled | 7, 39, 58 | not in §22 — **rec. W4** (anchor contract with #6; §23 rates it low, so W3 is defensible) |
| 14 | Dataflows | `/dataflows` | 🟡 | member; run needs edit, delete/permissions need data | New dataflow | loading; error; inline action error; empty | 28, 29 | W3 |
| 15 | Lineage | `/lineage` | 🟡 | member | click a node | loading; error; per-column empty | — | W3 |
| 16 | Admin: Users | `/admin/users` | 🔴 | org admin | + New User | loading; error (page, not toast); "create a role first"; empty | — | W3 |
| 17 | Admin: Roles | `/admin/roles` | 🔴 | org admin | + New Role | loading / empty / error | 13, 49 | W3 |
| 18 | Admin: Organization chart | `/admin/org-units` | 🔴 | org admin | Add top-level unit | loading / empty / error | 14 | W3 |
| 19 | Admin: Row security | `/admin/row-security-rules` | 🔴 | org admin | + New Rule | loading / empty / error; auto-generate scanning + empty | 10, 11, 12, 13, 14, 15, 17 | W3 — **§23: hold** |
| 20 | Admin: Connection rules (Ask AI) | `/admin/connection-rules` | 🔴 | org admin | Add rule | none today (inline red text only) — add the three shared states | 15 | W3 — **§23: hold** |
| 21 | Admin: Column security | `/admin/column-security-rules` | 🔴 | org admin | + New Rule | loading / empty / error | 13, 16, 17 | W3 — **§23: hold** |
| 22 | Admin: Export policy | `/admin/export-policy` | 🔴 | org admin | inline checkboxes | loading / empty / error; a per-dataset fetch failure currently reads as "no restriction" | 19, 20 | W3 — **§23: hold** |
| 23 | Admin: SSO | `/admin/sso` | 🔴 | org admin | Save | full-page loading / error; required-field toasts | 48 | W3 |
| 24 | Admin: Custom connectors | `/admin/custom-connectors` | 🔴 | org admin | + New | loading / empty / error | — | W3 |
| 25 | Admin: Audit trail | `/admin/audit` | 🟡 | org admin | Apply filter | loading / empty / error | — | W3 |
| 26 | Admin: API keys | `/admin/api-keys` | 🔴 | route admin-gated; keys are personal | Create key | loading / empty / error; revoke has its own error path | 50 | W3 |
| 27 | Platform: Organizations | `/platform/organizations` | 🔴 | super-admin | Create organization | loading / empty / error | 49, 51 | not in §22 — **rec. W3**, with the admin pages |
| 28 | Monitoring: Refresh & jobs | `/monitoring/jobs` | 🟢 | org admin | — (links) | loading / empty / error | 37 | W3 |
| 29 | Monitoring: Deliveries | `/monitoring/deliveries` | 🟢 | org admin | — | loading / empty / error | 35 | W3 |
| 30 | Monitoring: Activity | `/monitoring/activity` | 🟢 | org admin | — | loading / empty / error | — | W3 |
| 31 | Shared report | `/shared/:token` | 🔴 | public (token) | — | loading; ONE error message for every failure; no-pages; rate-limited placeholder | 9, 11, 23, 32, 33, 52 | W5 |
| 32 | Embedded report | `/embed?token=` | 🔴 | public (host JWT + origin) | — | missing-token; loading; invalid / expired / wrong-origin; no-pages | 9, 11, 23, 33, 34 | W5 |

**Shell (rail, workspace tree, top bar, notifications bell, account menu, command palette) — 🔴, wave 2.** Not one of the 32 screens, but it carries §14 rules **24, 25, 26, 31** (folder roles are menu-only; folder grants are view/edit only and publish the subtree; folder delete re-parents and never deletes a report; only a creator or admin may change a node), **46** (404 never 403, app-wide), **47** (7-day token, no revocation, logout is client-side) and **53** (every rail entry's permission must equal its route guard). §7's two component rows — notifications bell and account/theme/language/direction menu — live here, which is why this table has 32 rows and not 34.

---

## 3. WAVE PLAN

**Wave 1 — Visual layer, all 32 screens at once.**
Tokens (colour, type, spacing, radius, shadow, motion), buttons, cards, tables, toasts, skeletons, and the three shared state components. §22.1: the whole SAFE column, touching every screen without touching a contract.
*Cannot start before: nothing. This is the entry point.*

**Wave 2 — Shell.**
Rail, workspace tree, top bar, command palette, account/preferences page (client-side preferences only), a 404 route, and themed dialogs replacing the eight native `prompt`/`confirm` calls.
*Cannot start before W1:* the rail, dialogs and preferences page are assembled out of W1's button/card/dialog/state vocabulary. Built first, they would be rebuilt in W1.

**Wave 3 — List and admin pages.**
Home (3), Datasets (4), Dashboards (7), Connections (10), Dataflows (14), Lineage (15), Monitoring ×3 (28–30), the eleven admin pages (16–26). **rec. additions:** Login (1), SSO callback (2), Upload (5), Platform orgs (27).
*Cannot start before W2:* this wave's whole point is consistent confirmations, state components and post-action navigation (§18.1 items 2, 3, 4, 7). Those cannot be made consistent against unified dialogs and shell navigation that do not exist yet — W2 creates them.
*Note:* §22 puts all eleven admin pages here, but §23 says Row security (19), Connection rules (20), Column security (21) and Export policy (22) must not be touched until later. The conflict is in the document; it needs a ruling, not a silent choice.

**Wave 4 — Dataset detail (6) and Ask AI (12). rec. addition:** Insights hub (13).
*Cannot start before W3:* the document gives no code dependency here — the ordering is risk, not coupling (§22.3: W3 has "the fewest hidden contracts and the clearest backend gates"). The stated gate is therefore evidential: the new state, confirm and error conventions must be proven on the low-contract pages, and §21's before-and-after suite run must be green, before they are applied where §14 gates live.

**Wave 5 — Report builder (8), properties rail, widget renderer, and the public surfaces: Shared (31), Embedded (32). rec. additions:** Print (9), Source review (11).
*Cannot start before W4:* the builder consumes the measures, calculated columns, relationships and hierarchies that Dataset detail owns (§7 row 8), and its widget error/empty/retry vocabulary is the one W4 settles for the DirectQuery gates. §22.5 also requires a dedicated regression pass against §21 and the §19 security items, which is only meaningful once every non-builder surface has stopped moving.
