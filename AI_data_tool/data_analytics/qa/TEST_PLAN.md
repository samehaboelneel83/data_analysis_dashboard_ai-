# Browser test plan

**129 cases** across auth, navigation, home, datasets, upload, Ask AI, dashboards, builder, maps, insights, connections, lineage, security, monitoring, admin, platform, share/print, i18n, and mobile.

An AI agent (or a human) runs these cases in a **real browser**, clicking like a user. Do not use CSS selectors, test ids, or API calls as the way to operate the app. Open DevTools Console and Network while you work.

**App:** http://localhost:3001  
**Accounts and fixtures:** `qa/TEST_DATA.md`  
**How to start and seed:** `CLAUDE.md`  
**Where to write results:** copy `qa/REPORT_TEMPLATE.md` to `qa/REPORT.md`

## Rules for the agent

1. Seed first (`qa/seed.ps1` or Settings → Load demo content) so demo datasets and dashboards exist.
2. Run **high** cases before medium/low. Stop a flow if login itself fails.
3. Log in as **ADMIN** unless a case names another account.
4. Open dashboards and datasets **by name**, never by a remembered numeric id.
5. After each case: Pass / Fail, what you saw, and any **red console errors** (ignore benign extension noise).
6. Do not delete seeded Demo / Use case content. You may delete items named `QA …`.
7. If a page shows **Try again** after a load error, that is a fail — not an empty state.
8. Empty state copy such as “No dashboards yet” is only a pass when the list is truly empty.

---

# AUTH — sign in / out

There is **no Sign Up**. The login screen has Email, Password, Sign in, and Sign in with SSO.

### AUTH-01 — Empty fields  `high`  `/login`
1. Open `/login` logged out.
2. Leave email and password empty. Click **Sign in**.
**Expect:** Stay on login. A message that both email and password are needed. No home page.

### AUTH-02 — Invalid email shape  `high`  `/login`
1. Type `not-an-email` and `demo-password`. Click **Sign in**.
**Expect:** Browser or app refuses; you are not signed in.

### AUTH-03 — Unknown user  `high`  `/login`
1. Type `nobody@example.invalid` / `demo-password`. Click **Sign in**.
**Expect:** Error such as invalid email or password. Still on `/login`.

### AUTH-04 — Wrong password  `high`  `/login`
1. Type ADMIN email and `wrong-password`. Click **Sign in**.
**Expect:** Same style of error as AUTH-03. Not signed in.

### AUTH-05 — Happy path  `high`  `/login`
1. Type ADMIN email and `demo-password`. Click **Sign in**.
**Expect:** Home (`/`) with the rail (Home, Ask AI, Datasets, Dashboards, …) and an account menu.

### AUTH-06 — Protected URL while logged out  `high`  `/reports`
1. Log out (or a private window).
2. Open `/reports` directly.
**Expect:** Redirect to `/login`. After AUTH-05, `/reports` shows the dashboard list.

### AUTH-07 — Logout  `high`  `/`
1. Signed in, open the account menu in the top bar. Click **Log out** (or equivalent).
2. Try `/` again.
**Expect:** Back on `/login`. Home is not visible.

### AUTH-08 — SSO without email  `medium`  `/login`
1. Leave email empty. Click **Sign in with SSO** (wording may vary).
**Expect:** Message that an email is needed. No blank redirect.

### AUTH-09 — No Sign Up  `medium`  `/login`
1. Look at the login card.
**Expect:** No Sign Up / Register. Creating users is an admin action.

### AUTH-10 — Logged-in visit to login  `low`  `/login`
1. While signed in, open `/login`.
**Expect:** Bounced to Home. Login form does not stay on screen.

---

# NAV — shell, links, search

### NAV-01 — Rail destinations  `high`  `/`
1. Expand the left rail if it is collapsed.
2. Open each member item: Home, Ask AI, Datasets, Lineage, Upload, Connections, Dashboards, Insights.
**Expect:** Each destination loads its own page. The active item is highlighted. No blank crash.

### NAV-02 — Dashboards alias  `medium`  `/dashboards`
1. Open `/dashboards`.
**Expect:** Same list as `/reports` (URL may rewrite to `/reports`).

### NAV-03 — Command palette  `medium`  `/`
1. Press **Ctrl+K** (or the search control in the top bar).
2. Type `Dashboards` and choose it.
**Expect:** Palette opens, then you land on the dashboards list.

### NAV-04 — Admin hidden from analyst  `high`  `/`
1. Log in as EMEA or CONTOSO_ANALYST.
2. Look at the rail.
**Expect:** No Admin, Monitoring, or Platform section. Direct `/admin/users` is refused or bounced — not a working users table.

### NAV-05 — Admin visible  `high`  `/`
1. Log in as ADMIN.
**Expect:** Monitoring and Admin sections are present. If this account is super-admin, Platform → Organizations is present.

### NAV-06 — Theme toggle  `low`  `/`
1. Click the sun/moon control in the top bar twice.
**Expect:** Light and dark both paint readable text (no white-on-white). Choice survives a refresh.

---

# HOME

### HOME-01 — Landing  `high`  `/`
1. Sign in as ADMIN. Land on Home.
**Expect:** Recent dashboards and/or datasets as cards, or an honest empty section — not a spinner forever, not “No dashboards yet” when demo content exists.

### HOME-02 — Open a recent dashboard  `high`  `/`
1. Click a recent dashboard card.
**Expect:** Designer or viewer for that dashboard opens.

### HOME-03 — Open a dataset card  `high`  `/`
1. Click a dataset card (or All datasets).
**Expect:** Dataset detail or the datasets list.

### HOME-04 — Collapse a Home section  `low`  `/`
1. Click a section heading chevron.
**Expect:** Cards hide; click again and they return.

---

# DATASETS

### DS-01 — List  `high`  `/datasets`
1. Open Datasets.
**Expect:** Demo datasets appear by name (at least Demo — Sales). Search appears if there are many. Load error uses **Try again**, not an empty list.

### DS-02 — Open Demo — Sales  `high`  `/datasets`
1. Open **Demo — Sales**.
**Expect:** Title, tabs: Overview, Data, Meaning, Analysis, Alerts, Models, Aggregates. **Ask about this data** is visible.

### DS-03 — Data tab  `high`  dataset detail
1. Open the **Data** tab.
**Expect:** A table of rows and columns. Not an endless loader. Horizontal scroll if many columns.

### DS-04 — Data tab calculated column  `high`  dataset detail
1. If Overview / calculations lists an `fx` column, switch to **Data**.
**Expect:** That column is in the table header (known regression: missing on dashboard Data tab vs dataset Data tab).

### DS-05 — Data filters  `medium`  dataset detail
1. On Data, add a filter if the UI offers one, or search.
2. Clear it.
**Expect:** Rows shrink then restore. Empty filter does not crash.

### DS-06 — Overview analysis  `medium`  dataset detail
1. On Overview, click **Run analysis** (or Re-run).
**Expect:** Stats / types appear. Button returns to idle. No uncaught exception.

### DS-07 — Analysis tab  `medium`  dataset detail
1. Open **Analysis**.
**Expect:** Analysis tools or an empty/honest state, not a crashed page.

### DS-08 — Meaning / Alerts / Models / Aggregates  `low`  dataset detail
1. Click each remaining tab.
**Expect:** Each tab has content or a clear empty message.

### DS-09 — Ask about this data  `high`  dataset detail
1. Click **Ask about this data**.
**Expect:** Ask AI opens scoped to this dataset (`/ask?dataset=…`).

### DS-10 — Missing dataset  `medium`  `/datasets/999999`
1. Open a nonsense id.
**Expect:** Load error or not-found with a way back — not a white screen.

---

# UPLOAD

### UP-01 — Empty submit  `high`  `/upload`
1. Open Upload. Click the upload / submit control with no file.
**Expect:** Message to select a file and enter a name. No navigation.

### UP-02 — Happy CSV  `high`  `/upload`
1. Choose `qa/fixtures/qa_sample.csv`. Keep the suggested name (or `QA Sample NN`).
2. Submit.
**Expect:** Success toast. Dataset detail opens. Data tab shows `region`, `country`, `revenue`, `units`, `date`.

### UP-03 — Invalid file  `medium`  `/upload`
1. Choose `qa/fixtures/qa_not_a_dataset.txt`. Submit.
**Expect:** Error on this page. You are **not** sent away so you can still read the failure.

### UP-04 — Name required  `medium`  `/upload`
1. Pick the valid CSV. Clear the name field. Submit.
**Expect:** Validation message. No silent upload.

### UP-05 — Drag and drop  `low`  `/upload`
1. Drag the valid CSV onto the drop zone.
**Expect:** File is selected (name fills). Same as browsing.

### UP-06 — Two CSVs, separate datasets  `medium`  `/upload`
1. Select two copies / two CSVs if the picker allows multiple.
2. Choose **separate datasets**. Submit.
**Expect:** Two datasets, or a per-file result list. Failures listed without leaving the page.

### UP-07 — Two CSVs, one dataset  `low`  `/upload`
1. Same files, mode **a single dataset** / append.
**Expect:** One dataset. You stay on Upload if any file failed.

---

# ASK AI

Ask AI answers questions. It must **not** edit dashboards. Page copilot is a different control on a dashboard.

### ASK-01 — Scope required  `high`  `/ask`
1. Open Ask AI with no dataset chosen if the UI allows.
**Expect:** Prompt to pick a dataset or connection. Sending with no scope does not invent tables.

### ASK-02 — Greeting  `high`  `/ask`
1. Pick **Demo — Sales**. Send `hi`.
**Expect:** Short reply. No fake revenue number.

### ASK-03 — What is this data  `high`  `/ask`
1. Send `what is this data`.
**Expect:** Description of Demo — Sales / catalog. Not a crash if the model is off — then a clear “AI unavailable” style message.

### ASK-04 — Aggregation question  `high`  `/ask`
1. Send `total revenue by region`.
**Expect:** Sentence + table. Numbers in the sentence match the table. Show SQL if offered.

### ASK-05 — Follow-up chart  `medium`  `/ask`
1. After ASK-04, send `show that as a bar chart`.
**Expect:** A chart of the last result, not a refusal that the chat cannot chart.

### ASK-06 — Refuse dashboard actions  `high`  `/ask`
1. Send `create a dashboard with a KPI`.
**Expect:** Refusal or “do that in Dashboards / copilot”. No new dashboard on `/reports`.

### ASK-07 — New chat  `medium`  `/ask`
1. Click **New chat**. Send another question.
**Expect:** Fresh thread. Old thread still listed.

### ASK-08 — Empty send  `medium`  `/ask`
1. Send an empty message.
**Expect:** Nothing fires, or a nudge to type something. No error toast storm.

---

# DASHBOARDS LIST

### DASH-01 — List  `high`  `/reports`
1. Open Dashboards.
**Expect:** Seeded dashboards by name. Not “No dashboards yet” when demo exists.

### DASH-02 — Search  `medium`  `/reports`
1. If a search box is shown, type `World Sales`.
**Expect:** World Sales Map remains. Unrelated names hide. A nonsense search says nothing matches — not the empty-inventory card.

### DASH-03 — Open designer  `high`  `/reports`
1. Open **Demo — Sales Overview**.
**Expect:** Canvas with widgets, not an infinite load.

### DASH-04 — Create disabled until named  `high`  `/reports`
1. Click **+ New dashboard**.
2. Leave the name empty. Try create.
**Expect:** Create stays disabled or shows that the name is required.

### DASH-05 — Create dashboard  `high`  `/reports`
1. Name it `QA Dashboard NN`. Optional description. Dataset **Demo — Sales**. Create.
**Expect:** Card appears in the list (often at the top). Opening it shows an empty or starter canvas you can edit.

### DASH-06 — Create without dataset  `medium`  `/reports`
1. Create `QA Dashboard NN-nods` with no dataset.
**Expect:** Allowed. Card may say No dataset.

### DASH-07 — Delete QA dashboard  `medium`  `/reports`
1. On a `QA Dashboard` you created, Delete and confirm.
**Expect:** Gone from the list. Seeded Demo dashboards still there.

### DASH-08 — Cancel delete  `low`  `/reports`
1. Delete, then cancel.
**Expect:** Dashboard remains.

### DASH-09 — View-only chip  `medium`  `/reports`
1. As EMEA, look at a dashboard you cannot design (if any).
**Expect:** View-only / Open (not “Open designer”) as documented. Opening does not show edit chrome you cannot use.

### DASH-10 — New folder  `low`  `/reports`
1. Create a folder if **New folder** exists. Drag a QA dashboard onto it if drag is offered.
**Expect:** Folder appears. Dashboard moves. No tree freeze.

---

# DASHBOARD BUILDER

Use `QA Dashboard NN` from DASH-05, or Demo — Sales Overview for viewing interactions. Prefer a QA dashboard for destructive edits.

### BUILD-01 — Empty canvas  `high`  `/reports/:id`
1. Open the QA dashboard.
**Expect:** Empty canvas or default widgets. Left gallery of chart types. Right properties when something is selected. **Edit mode** on.

### BUILD-02 — Add a bar chart  `high`  `/reports/:id`
1. Drag or click **Bar Chart** onto the canvas.
2. In properties, set dimension to a category (e.g. region) and measure to revenue if fields exist.
**Expect:** Bars render. Title is editable. No blank card once fields are set.

### BUILD-03 — Add a KPI  `high`  `/reports/:id`
1. Add **KPI Card**. Bind a measure.
**Expect:** A number, not `NaN` or a raw dump.

### BUILD-04 — Cross-filter  `high`  Demo — Sales Overview or Regional performance
1. Click a bar or pie slice.
**Expect:** Other tiles filter. Filter chips appear. Clear restores all tiles.

### BUILD-05 — Isolated widget  `medium`  `/reports/:id`
1. If Interaction mode exists, set one widget to Isolated and click another.
**Expect:** Isolated widget does not change.

### BUILD-06 — Packed layout / templates  `high`  `/reports/:id`
1. Open **Layout**. Apply Executive (or the default packed template).
**Expect:** Widgets fill the page without huge empty bands. They do not overlap.

### BUILD-07 — Swap widgets  `high`  `/reports/:id`
1. In packed mode, drag one chart onto another.
**Expect:** They swap. Pointer stays with the dragged card. No shrink-to-nothing.

### BUILD-08 — Resize minimum  `high`  `/reports/:id`
1. Drag the bottom-right resize handle as small as it will go.
**Expect:** Stops at a usable size. Data still visible.

### BUILD-09 — Free layout  `medium`  `/reports/:id`
1. Switch Layout to free-form if offered. Move a widget.
**Expect:** Moves with the pointer. Can switch back to packed.

### BUILD-10 — Page copilot add chart  `high`  `/reports/:id`
1. Open the page copilot (green chat on the dashboard).
2. Send `add a bar chart of revenue by region`.
**Expect:** A bar appears. Copilot does not say it lacks permission to edit the page.

### BUILD-11 — Copilot aggregation  `high`  `/reports/:id`
1. Ask to **sum** a measure, then to show **individual values / no aggregation**.
**Expect:** Both orders are obeyed. Sum is allowed on fx columns if present.

### BUILD-12 — Copilot calculated column  `medium`  `/reports/:id`
1. Ask to add or edit a calculated column.
**Expect:** Copilot uses dashboard data tools (unlike Ask AI). Data tab still lists the column.

### BUILD-13 — New page  `medium`  `/reports/:id`
1. Click **+ Page**.
**Expect:** A new tab. Widgets on page 1 unchanged.

### BUILD-14 — Present  `medium`  `/reports/:id`
1. Click **Present**.
**Expect:** Full-screen view. Edit chrome hidden. A way to exit.

### BUILD-15 — Save / dirty  `medium`  `/reports/:id`
1. Move a widget. Look for saved / unsaved.
**Expect:** Change persists after refresh, or a clear save control works.

### BUILD-16 — Properties empty widget  `low`  `/reports/:id`
1. Add a chart and leave fields blank.
**Expect:** Empty/placeholder state, not a thrown error overlay.

---

# MAPS

On **Demo — World Sales Map**. Collapse side panels if the canvas is cramped. Hard-refresh once if maps look like the old clipped world.

### MAP-01 — Shipping routes  `high`  World Sales Map
1. Find **Shipping routes**.
**Expect:** Full world in the tile. Routes visible. Asia not sliced off. Empty-looking Pacific is OK.

### MAP-02 — Origin density  `high`  World Sales Map
1. Find **Origin density**.
**Expect:** Bubbles fully inside the tile, counts readable.

### MAP-03 — Routes as a network  `high`  World Sales Map
1. Find **Routes as a network**.
**Expect:** London, Tokyo, Sydney, Los Angeles labels fully inside the tile.

### MAP-04 — Resize tile  `high`  World Sales Map
1. In edit mode, widen or shorten the shipping-routes widget.
**Expect:** Map refits. Still no clipped labels.

### MAP-05 — Collapse panels  `medium`  World Sales Map
1. Collapse the left fields rail and the right settings panel.
**Expect:** Maps grow with the canvas and stay unclipped.

### MAP-06 — Other map widgets  `medium`  World Sales Map
1. Scroll to point, bubble, choropleth, pie, layered maps.
**Expect:** Each draws; no permanent “Loading map…”.

---

# INSIGHTS

### INS-01 — Hub  `high`  `/insights`
1. Open Insights. Pick **Demo — Sales** if not selected.
**Expect:** Dataset picker. Top insights preview or a quiet empty preview (not a fake “you have no datasets” when you do).

### INS-02 — View full scan  `high`  `/insights`
1. Click **View full scan**.
**Expect:** Dataset page Insights/Analysis section with the longer list.

### INS-03 — Empty org  `low`  `/insights`
Only if you have a user with zero datasets.
**Expect:** “No datasets yet — upload one…” — not a crash.

### INS-04 — DirectQuery chip  `low`  `/insights`
1. If Demo — Live Orders is listed, select it.
**Expect:** A live marker if the UI shows one. Preview either runs or explains why not.

### INS-05 — Search datasets  `low`  `/insights`
1. If 8+ datasets, search for `Sales`.
**Expect:** List filters. A typo does not trap you with an unusable dropdown.

---

# CONNECTIONS

### CONN-01 — List  `high`  `/connections`
1. Open Connections.
**Expect:** List or empty state “no connections”. Demo may include **Demo — Live SQLite**.

### CONN-02 — New connection name required  `high`  `/connections`
1. Open new connection. Leave name empty. Save.
**Expect:** “Name is required”. Modal stays open.

### CONN-03 — Create then test  `medium`  `/connections`
1. Create `QA Conn NN` of type PostgreSQL (or the first type) with dummy host values.
2. If Test is offered before save, follow the on-screen rule (often save first).
**Expect:** Connection appears in the list. Failed test shows an error, not a hang.

### CONN-04 — Schema / review  `medium`  `/connections`
1. If a connection has **Browse** / **Review**, open it (`/connections/:id/review`).
**Expect:** Tables/columns or a clear empty/error. Confirm/reject controls do not crash.

### CONN-05 — Delete QA connection  `low`  `/connections`
1. Delete `QA Conn NN` with confirm.
**Expect:** Removed. Demo connection remains.

### CONN-06 — Non-admin list  `medium`  `/connections`
1. As EMEA, open Connections.
**Expect:** Page loads. Creating may be limited. No uncaught exception.

---

# LINEAGE

### LIN-01 — Graph  `high`  `/lineage`
1. Open Lineage.
**Expect:** Sources → datasets → reports columns or an empty/honest state. Seeded demo should show edges.

### LIN-02 — Click a node  `medium`  `/lineage`
1. Click a dataset node if clickable.
**Expect:** Navigate to that dataset or highlight related edges — not a JS exception.

### LIN-03 — Load error  `low`  `/lineage`
If the API is stopped (optional).
**Expect:** Try again, not a blank page pretending there is no lineage.

---

# SECURITY (two users, same report)

Use **Use case — Regional performance review**.

### SEC-01 — Global sees all  `high`  that report
1. Log in as GLOBAL. Open the report.
**Expect:** Multiple regions. `cost` (or margin inputs) present where the story includes cost.

### SEC-02 — EMEA row + column rules  `high`  same report
1. Log out. Log in as EMEA. Open the **same** report.
**Expect:** Europe only. `cost` gone (not a column of blanks). Totals smaller than GLOBAL.

### SEC-03 — Ask AI inherits RLS  `high`  `/ask`
1. As EMEA, Ask AI total sales on Demo — Sales.
**Expect:** Answer consistent with Europe-only data. No global total.

### SEC-04 — Row security admin page  `medium`  `/admin/row-security-rules`
1. As ADMIN, open Row security.
**Expect:** Rules list (demo has region Europe on the EMEA role) or empty + create. Expression field validates junk.

### SEC-05 — Column security admin page  `medium`  `/admin/column-security-rules`
1. Open Column security.
**Expect:** Page loads. Creating a rule without required fields is rejected.

### SEC-06 — Connection rules  `low`  `/admin/connection-rules`
1. Open this URL (may be absent from the rail).
**Expect:** Page or a guarded redirect — not an unhandled crash.

---

# MONITORING (admin)

### MON-01 — Refresh & jobs  `medium`  `/monitoring/jobs`
1. Open the page.
**Expect:** Job list or empty. Seeded jobs may be paused. Not “no jobs” when a load failed.

### MON-02 — Deliveries  `medium`  `/monitoring/deliveries`
1. Open Deliveries.
**Expect:** Seeded weekly delivery may appear, paused. Recipients visible.

### MON-03 — Activity  `medium`  `/monitoring/activity`
1. Open Activity.
**Expect:** Recent actions or empty. Filter if present.

### MON-04 — Analyst blocked  `medium`  `/monitoring/jobs`
1. As EMEA, open the URL.
**Expect:** Not the admin jobs table.

---

# ADMIN

### ADM-01 — Users list  `high`  `/admin/users`
1. Open Users.
**Expect:** ADMIN and demo users listed.

### ADM-02 — New user validation  `high`  `/admin/users`
1. New user. Leave email and password empty. Save.
**Expect:** Email required; password required for a new user.

### ADM-03 — Create QA user  `medium`  `/admin/users`
1. Email `qa.user.NN@example.invalid`, password from TEST_DATA, pick a non-admin role. Save.
**Expect:** Toast success. User in the list. Log in as that user works (optional).

### ADM-04 — Roles validation  `medium`  `/admin/roles`
1. New role, empty name, save.
**Expect:** Name is required.

### ADM-05 — Create QA role  `low`  `/admin/roles`
1. Name `QA Role NN`. Save.
**Expect:** Appears in the list.

### ADM-06 — Organization chart  `medium`  `/admin/org-units`
1. Open Organization chart.
**Expect:** Tree or empty + add. No crash.

### ADM-07 — Export policy  `low`  `/admin/export-policy`
1. Open Export policy.
**Expect:** Policy form loads. Save without change is harmless or confirms.

### ADM-08 — API key name required  `medium`  `/admin/api-keys`
1. Create with empty name.
**Expect:** “Name the key first”.

### ADM-09 — Create API key  `medium`  `/admin/api-keys`
1. Name `QA Key NN`. Create.
**Expect:** Secret shown **once**. List updates.

### ADM-10 — SSO page  `low`  `/admin/sso`
1. Open Single sign-on.
**Expect:** Config form. Enable/save with empty required fields is rejected.

### ADM-11 — Audit trail  `low`  `/admin/audit`
1. Open Audit trail.
**Expect:** Events or empty. Filters if present.

### ADM-12 — Custom connectors  `low`  `/admin/custom-connectors`
1. Open Custom connectors.
**Expect:** List or empty + create. Name required.

---

# PLATFORM (super-admin)

### PLAT-01 — Organizations  `medium`  `/platform/organizations`
1. As ADMIN (allowlisted). Open Organizations.
**Expect:** Default org listed. Create form: name, admin email, admin password.

### PLAT-02 — Create validation  `medium`  `/platform/organizations`
1. Click create with all fields empty.
**Expect:** Name, admin email and password are required.

### PLAT-03 — Analyst blocked  `medium`  `/platform/organizations`
1. As EMEA, open the URL.
**Expect:** Not the platform org manager.

### PLAT-04 — Create org  `low`  `/platform/organizations`
1. Create `QA Org NN` with QA admin email/password from TEST_DATA.
**Expect:** Org appears. Do not create extras in a shared QA box.

---

# SHARE / PRINT / EMBED

### SHARE-01 — Share dialog  `high`  a dashboard you administer
1. Share (link icon). Create a link if offered.
**Expect:** A URL. Copy works.

### SHARE-02 — Open share link logged out  `high`  `/shared/:token`
1. Private window. Open the link.
**Expect:** That report only. No rail of the whole app. RLS of the share still applies (no extra columns).

### SHARE-03 — Print  `medium`  `/reports/:id/print`
1. Print from the builder, or add `/print` to a report URL.
**Expect:** Printable layout. Widgets visible.

### SHARE-04 — PDF  `medium`  dashboard
1. Click **PDF**.
**Expect:** Download or a progress/error toast — not a silent no-op.

### SHARE-05 — Publish  `low`  QA dashboard
1. Publish if you administer it.
**Expect:** Published chip. Unpublish restores.

---

# I18N / RTL

### I18N-01 — Language switcher on login  `medium`  `/login`
1. Switch language if a control exists. Switch back to English.
**Expect:** Labels change. Form still submits.

### I18N-02 — In-app language  `low`  `/`
1. Switch language in the top bar.
**Expect:** Rail labels translate. No layout overflow that hides Sign out.

### I18N-03 — RTL  `low`  `/`
1. If an RTL / direction control exists, turn it on, open a dashboard, turn it off.
**Expect:** Layout mirrors. Maps stay `ltr` enough that they are not clipped (maps force LTR internally).

---

# MOBILE / NARROW

Viewport **390 × 844** (and one pass at **890 × 800** for the rail drawer).

### MOB-01 — Login on a phone  `high`  `/login`
1. Narrow viewport. Sign in.
**Expect:** Form fits. Sign in is tappable. No clipped button.

### MOB-02 — Rail drawer  `high`  `/`
1. Width 890px or less. Open the menu button.
2. Go to Dashboards. The drawer should close.
**Expect:** Overlay menu, not a squeezed unusable canvas. Escape closes it.

### MOB-03 — Dashboard canvas  `high`  a seeded dashboard
1. Phone width. Scroll the canvas.
**Expect:** Widgets usable (scroll OK). No overlapping chrome that blocks charts. Maps not clipped worse than desktop.

### MOB-04 — Upload on mobile  `medium`  `/upload`
1. Page is usable; file picker works.
**Expect:** No overlapping buttons. Submit still visible.

---

# Suggested run order

1. AUTH-01 … AUTH-07  
2. NAV-01, NAV-04, NAV-05  
3. HOME-01 … HOME-03  
4. DS-01 … DS-04, DS-09  
5. UP-01, UP-02  
6. ASK-01 … ASK-06  
7. DASH-01, DASH-03, DASH-04, DASH-05  
8. BUILD-01 … BUILD-12  
9. MAP-01 … MAP-05  
10. INS-01, INS-02  
11. SEC-01 … SEC-03  
12. SHARE-01, SHARE-02  
13. MOB-01 … MOB-03  
14. Remaining medium/low  

If time is short, stop after step 13. Those are the flows a user actually feels.
