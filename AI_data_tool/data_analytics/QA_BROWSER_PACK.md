# QA browser pack (attach this one file)

This file is the full test plan plus the report template. Canonical copies also live at `qa/TEST_PLAN.md` and `qa/REPORT_TEMPLATE.md`.

Login: `admin@datalytics.local` / `demo-password`
App: http://localhost:3001

---

# Browser test plan

**129 cases** across auth, navigation, home, datasets, upload, Ask AI, dashboards, builder, maps, insights, connections, lineage, security, monitoring, admin, platform, share/print, i18n, and mobile.

An AI agent (or a human) runs these cases in a **real browser**, clicking like a user. Do not use CSS selectors, test ids, or API calls as the way to operate the app. Open DevTools Console and Network while you work.

**App:** http://localhost:3001  
**Accounts and fixtures:** `qa/TEST_DATA.md`  
**How to start and seed:** `CLAUDE.md`  
**Where to write results:** copy `qa/REPORT_TEMPLATE.md` to `qa/REPORT.md`

## Rules for the agent

1. Seed first (`qa/seed.ps1` or Settings â†’ Load demo content) so demo datasets and dashboards exist.
2. Run **high** cases before medium/low. Stop a flow if login itself fails.
3. Log in as **ADMIN** unless a case names another account.
4. Open dashboards and datasets **by name**, never by a remembered numeric id.
5. After each case: Pass / Fail, what you saw, and any **red console errors** (ignore benign extension noise).
6. Do not delete seeded Demo / Use case content. You may delete items named `QA â€¦`.
7. If a page shows **Try again** after a load error, that is a fail â€” not an empty state.
8. Empty state copy such as â€œNo dashboards yetâ€ is only a pass when the list is truly empty.

---

# AUTH â€” sign in / out

There is **no Sign Up**. The login screen has Email, Password, Sign in, and Sign in with SSO.

### AUTH-01 â€” Empty fields  `high`  `/login`
1. Open `/login` logged out.
2. Leave email and password empty. Click **Sign in**.
**Expect:** Stay on login. A message that both email and password are needed. No home page.

### AUTH-02 â€” Invalid email shape  `high`  `/login`
1. Type `not-an-email` and `demo-password`. Click **Sign in**.
**Expect:** Browser or app refuses; you are not signed in.

### AUTH-03 â€” Unknown user  `high`  `/login`
1. Type `nobody@example.invalid` / `demo-password`. Click **Sign in**.
**Expect:** Error such as invalid email or password. Still on `/login`.

### AUTH-04 â€” Wrong password  `high`  `/login`
1. Type ADMIN email and `wrong-password`. Click **Sign in**.
**Expect:** Same style of error as AUTH-03. Not signed in.

### AUTH-05 â€” Happy path  `high`  `/login`
1. Type ADMIN email and `demo-password`. Click **Sign in**.
**Expect:** Home (`/`) with the rail (Home, Ask AI, Datasets, Dashboards, â€¦) and an account menu.

### AUTH-06 â€” Protected URL while logged out  `high`  `/reports`
1. Log out (or a private window).
2. Open `/reports` directly.
**Expect:** Redirect to `/login`. After AUTH-05, `/reports` shows the dashboard list.

### AUTH-07 â€” Logout  `high`  `/`
1. Signed in, open the account menu in the top bar. Click **Log out** (or equivalent).
2. Try `/` again.
**Expect:** Back on `/login`. Home is not visible.

### AUTH-08 â€” SSO without email  `medium`  `/login`
1. Leave email empty. Click **Sign in with SSO** (wording may vary).
**Expect:** Message that an email is needed. No blank redirect.

### AUTH-09 â€” No Sign Up  `medium`  `/login`
1. Look at the login card.
**Expect:** No Sign Up / Register. Creating users is an admin action.

### AUTH-10 â€” Logged-in visit to login  `low`  `/login`
1. While signed in, open `/login`.
**Expect:** Bounced to Home. Login form does not stay on screen.

---

# NAV â€” shell, links, search

### NAV-01 â€” Rail destinations  `high`  `/`
1. Expand the left rail if it is collapsed.
2. Open each member item: Home, Ask AI, Datasets, Lineage, Upload, Connections, Dashboards, Insights.
**Expect:** Each destination loads its own page. The active item is highlighted. No blank crash.

### NAV-02 â€” Dashboards alias  `medium`  `/dashboards`
1. Open `/dashboards`.
**Expect:** Same list as `/reports` (URL may rewrite to `/reports`).

### NAV-03 â€” Command palette  `medium`  `/`
1. Press **Ctrl+K** (or the search control in the top bar).
2. Type `Dashboards` and choose it.
**Expect:** Palette opens, then you land on the dashboards list.

### NAV-04 â€” Admin hidden from analyst  `high`  `/`
1. Log in as EMEA or CONTOSO_ANALYST.
2. Look at the rail.
**Expect:** No Admin, Monitoring, or Platform section. Direct `/admin/users` is refused or bounced â€” not a working users table.

### NAV-05 â€” Admin visible  `high`  `/`
1. Log in as ADMIN.
**Expect:** Monitoring and Admin sections are present. If this account is super-admin, Platform â†’ Organizations is present.

### NAV-06 â€” Theme toggle  `low`  `/`
1. Click the sun/moon control in the top bar twice.
**Expect:** Light and dark both paint readable text (no white-on-white). Choice survives a refresh.

---

# HOME

### HOME-01 â€” Landing  `high`  `/`
1. Sign in as ADMIN. Land on Home.
**Expect:** Recent dashboards and/or datasets as cards, or an honest empty section â€” not a spinner forever, not â€œNo dashboards yetâ€ when demo content exists.

### HOME-02 â€” Open a recent dashboard  `high`  `/`
1. Click a recent dashboard card.
**Expect:** Designer or viewer for that dashboard opens.

### HOME-03 â€” Open a dataset card  `high`  `/`
1. Click a dataset card (or All datasets).
**Expect:** Dataset detail or the datasets list.

### HOME-04 â€” Collapse a Home section  `low`  `/`
1. Click a section heading chevron.
**Expect:** Cards hide; click again and they return.

---

# DATASETS

### DS-01 â€” List  `high`  `/datasets`
1. Open Datasets.
**Expect:** Demo datasets appear by name (at least Demo â€” Sales). Search appears if there are many. Load error uses **Try again**, not an empty list.

### DS-02 â€” Open Demo â€” Sales  `high`  `/datasets`
1. Open **Demo â€” Sales**.
**Expect:** Title, tabs: Overview, Data, Meaning, Analysis, Alerts, Models, Aggregates. **Ask about this data** is visible.

### DS-03 â€” Data tab  `high`  dataset detail
1. Open the **Data** tab.
**Expect:** A table of rows and columns. Not an endless loader. Horizontal scroll if many columns.

### DS-04 â€” Data tab calculated column  `high`  dataset detail
1. If Overview / calculations lists an `fx` column, switch to **Data**.
**Expect:** That column is in the table header (known regression: missing on dashboard Data tab vs dataset Data tab).

### DS-05 â€” Data filters  `medium`  dataset detail
1. On Data, add a filter if the UI offers one, or search.
2. Clear it.
**Expect:** Rows shrink then restore. Empty filter does not crash.

### DS-06 â€” Overview analysis  `medium`  dataset detail
1. On Overview, click **Run analysis** (or Re-run).
**Expect:** Stats / types appear. Button returns to idle. No uncaught exception.

### DS-07 â€” Analysis tab  `medium`  dataset detail
1. Open **Analysis**.
**Expect:** Analysis tools or an empty/honest state, not a crashed page.

### DS-08 â€” Meaning / Alerts / Models / Aggregates  `low`  dataset detail
1. Click each remaining tab.
**Expect:** Each tab has content or a clear empty message.

### DS-09 â€” Ask about this data  `high`  dataset detail
1. Click **Ask about this data**.
**Expect:** Ask AI opens scoped to this dataset (`/ask?dataset=â€¦`).

### DS-10 â€” Missing dataset  `medium`  `/datasets/999999`
1. Open a nonsense id.
**Expect:** Load error or not-found with a way back â€” not a white screen.

---

# UPLOAD

### UP-01 â€” Empty submit  `high`  `/upload`
1. Open Upload. Click the upload / submit control with no file.
**Expect:** Message to select a file and enter a name. No navigation.

### UP-02 â€” Happy CSV  `high`  `/upload`
1. Choose `qa/fixtures/qa_sample.csv`. Keep the suggested name (or `QA Sample NN`).
2. Submit.
**Expect:** Success toast. Dataset detail opens. Data tab shows `region`, `country`, `revenue`, `units`, `date`.

### UP-03 â€” Invalid file  `medium`  `/upload`
1. Choose `qa/fixtures/qa_not_a_dataset.txt`. Submit.
**Expect:** Error on this page. You are **not** sent away so you can still read the failure.

### UP-04 â€” Name required  `medium`  `/upload`
1. Pick the valid CSV. Clear the name field. Submit.
**Expect:** Validation message. No silent upload.

### UP-05 â€” Drag and drop  `low`  `/upload`
1. Drag the valid CSV onto the drop zone.
**Expect:** File is selected (name fills). Same as browsing.

### UP-06 â€” Two CSVs, separate datasets  `medium`  `/upload`
1. Select two copies / two CSVs if the picker allows multiple.
2. Choose **separate datasets**. Submit.
**Expect:** Two datasets, or a per-file result list. Failures listed without leaving the page.

### UP-07 â€” Two CSVs, one dataset  `low`  `/upload`
1. Same files, mode **a single dataset** / append.
**Expect:** One dataset. You stay on Upload if any file failed.

---

# ASK AI

Ask AI answers questions. It must **not** edit dashboards. Page copilot is a different control on a dashboard.

### ASK-01 â€” Scope required  `high`  `/ask`
1. Open Ask AI with no dataset chosen if the UI allows.
**Expect:** Prompt to pick a dataset or connection. Sending with no scope does not invent tables.

### ASK-02 â€” Greeting  `high`  `/ask`
1. Pick **Demo â€” Sales**. Send `hi`.
**Expect:** Short reply. No fake revenue number.

### ASK-03 â€” What is this data  `high`  `/ask`
1. Send `what is this data`.
**Expect:** Description of Demo â€” Sales / catalog. Not a crash if the model is off â€” then a clear â€œAI unavailableâ€ style message.

### ASK-04 â€” Aggregation question  `high`  `/ask`
1. Send `total revenue by region`.
**Expect:** Sentence + table. Numbers in the sentence match the table. Show SQL if offered.

### ASK-05 â€” Follow-up chart  `medium`  `/ask`
1. After ASK-04, send `show that as a bar chart`.
**Expect:** A chart of the last result, not a refusal that the chat cannot chart.

### ASK-06 â€” Refuse dashboard actions  `high`  `/ask`
1. Send `create a dashboard with a KPI`.
**Expect:** Refusal or â€œdo that in Dashboards / copilotâ€. No new dashboard on `/reports`.

### ASK-07 â€” New chat  `medium`  `/ask`
1. Click **New chat**. Send another question.
**Expect:** Fresh thread. Old thread still listed.

### ASK-08 â€” Empty send  `medium`  `/ask`
1. Send an empty message.
**Expect:** Nothing fires, or a nudge to type something. No error toast storm.

---

# DASHBOARDS LIST

### DASH-01 â€” List  `high`  `/reports`
1. Open Dashboards.
**Expect:** Seeded dashboards by name. Not â€œNo dashboards yetâ€ when demo exists.

### DASH-02 â€” Search  `medium`  `/reports`
1. If a search box is shown, type `World Sales`.
**Expect:** World Sales Map remains. Unrelated names hide. A nonsense search says nothing matches â€” not the empty-inventory card.

### DASH-03 â€” Open designer  `high`  `/reports`
1. Open **Demo â€” Sales Overview**.
**Expect:** Canvas with widgets, not an infinite load.

### DASH-04 â€” Create disabled until named  `high`  `/reports`
1. Click **+ New dashboard**.
2. Leave the name empty. Try create.
**Expect:** Create stays disabled or shows that the name is required.

### DASH-05 â€” Create dashboard  `high`  `/reports`
1. Name it `QA Dashboard NN`. Optional description. Dataset **Demo â€” Sales**. Create.
**Expect:** Card appears in the list (often at the top). Opening it shows an empty or starter canvas you can edit.

### DASH-06 â€” Create without dataset  `medium`  `/reports`
1. Create `QA Dashboard NN-nods` with no dataset.
**Expect:** Allowed. Card may say No dataset.

### DASH-07 â€” Delete QA dashboard  `medium`  `/reports`
1. On a `QA Dashboard` you created, Delete and confirm.
**Expect:** Gone from the list. Seeded Demo dashboards still there.

### DASH-08 â€” Cancel delete  `low`  `/reports`
1. Delete, then cancel.
**Expect:** Dashboard remains.

### DASH-09 â€” View-only chip  `medium`  `/reports`
1. As EMEA, look at a dashboard you cannot design (if any).
**Expect:** View-only / Open (not â€œOpen designerâ€) as documented. Opening does not show edit chrome you cannot use.

### DASH-10 â€” New folder  `low`  `/reports`
1. Create a folder if **New folder** exists. Drag a QA dashboard onto it if drag is offered.
**Expect:** Folder appears. Dashboard moves. No tree freeze.

---

# DASHBOARD BUILDER

Use `QA Dashboard NN` from DASH-05, or Demo â€” Sales Overview for viewing interactions. Prefer a QA dashboard for destructive edits.

### BUILD-01 â€” Empty canvas  `high`  `/reports/:id`
1. Open the QA dashboard.
**Expect:** Empty canvas or default widgets. Left gallery of chart types. Right properties when something is selected. **Edit mode** on.

### BUILD-02 â€” Add a bar chart  `high`  `/reports/:id`
1. Drag or click **Bar Chart** onto the canvas.
2. In properties, set dimension to a category (e.g. region) and measure to revenue if fields exist.
**Expect:** Bars render. Title is editable. No blank card once fields are set.

### BUILD-03 â€” Add a KPI  `high`  `/reports/:id`
1. Add **KPI Card**. Bind a measure.
**Expect:** A number, not `NaN` or a raw dump.

### BUILD-04 â€” Cross-filter  `high`  Demo â€” Sales Overview or Regional performance
1. Click a bar or pie slice.
**Expect:** Other tiles filter. Filter chips appear. Clear restores all tiles.

### BUILD-05 â€” Isolated widget  `medium`  `/reports/:id`
1. If Interaction mode exists, set one widget to Isolated and click another.
**Expect:** Isolated widget does not change.

### BUILD-06 â€” Packed layout / templates  `high`  `/reports/:id`
1. Open **Layout**. Apply Executive (or the default packed template).
**Expect:** Widgets fill the page without huge empty bands. They do not overlap.

### BUILD-07 â€” Swap widgets  `high`  `/reports/:id`
1. In packed mode, drag one chart onto another.
**Expect:** They swap. Pointer stays with the dragged card. No shrink-to-nothing.

### BUILD-08 â€” Resize minimum  `high`  `/reports/:id`
1. Drag the bottom-right resize handle as small as it will go.
**Expect:** Stops at a usable size. Data still visible.

### BUILD-09 â€” Free layout  `medium`  `/reports/:id`
1. Switch Layout to free-form if offered. Move a widget.
**Expect:** Moves with the pointer. Can switch back to packed.

### BUILD-10 â€” Page copilot add chart  `high`  `/reports/:id`
1. Open the page copilot (green chat on the dashboard).
2. Send `add a bar chart of revenue by region`.
**Expect:** A bar appears. Copilot does not say it lacks permission to edit the page.

### BUILD-11 â€” Copilot aggregation  `high`  `/reports/:id`
1. Ask to **sum** a measure, then to show **individual values / no aggregation**.
**Expect:** Both orders are obeyed. Sum is allowed on fx columns if present.

### BUILD-12 â€” Copilot calculated column  `medium`  `/reports/:id`
1. Ask to add or edit a calculated column.
**Expect:** Copilot uses dashboard data tools (unlike Ask AI). Data tab still lists the column.

### BUILD-13 â€” New page  `medium`  `/reports/:id`
1. Click **+ Page**.
**Expect:** A new tab. Widgets on page 1 unchanged.

### BUILD-14 â€” Present  `medium`  `/reports/:id`
1. Click **Present**.
**Expect:** Full-screen view. Edit chrome hidden. A way to exit.

### BUILD-15 â€” Save / dirty  `medium`  `/reports/:id`
1. Move a widget. Look for saved / unsaved.
**Expect:** Change persists after refresh, or a clear save control works.

### BUILD-16 â€” Properties empty widget  `low`  `/reports/:id`
1. Add a chart and leave fields blank.
**Expect:** Empty/placeholder state, not a thrown error overlay.

---

# MAPS

On **Demo â€” World Sales Map**. Collapse side panels if the canvas is cramped. Hard-refresh once if maps look like the old clipped world.

### MAP-01 â€” Shipping routes  `high`  World Sales Map
1. Find **Shipping routes**.
**Expect:** Full world in the tile. Routes visible. Asia not sliced off. Empty-looking Pacific is OK.

### MAP-02 â€” Origin density  `high`  World Sales Map
1. Find **Origin density**.
**Expect:** Bubbles fully inside the tile, counts readable.

### MAP-03 â€” Routes as a network  `high`  World Sales Map
1. Find **Routes as a network**.
**Expect:** London, Tokyo, Sydney, Los Angeles labels fully inside the tile.

### MAP-04 â€” Resize tile  `high`  World Sales Map
1. In edit mode, widen or shorten the shipping-routes widget.
**Expect:** Map refits. Still no clipped labels.

### MAP-05 â€” Collapse panels  `medium`  World Sales Map
1. Collapse the left fields rail and the right settings panel.
**Expect:** Maps grow with the canvas and stay unclipped.

### MAP-06 â€” Other map widgets  `medium`  World Sales Map
1. Scroll to point, bubble, choropleth, pie, layered maps.
**Expect:** Each draws; no permanent â€œLoading mapâ€¦â€.

---

# INSIGHTS

### INS-01 â€” Hub  `high`  `/insights`
1. Open Insights. Pick **Demo â€” Sales** if not selected.
**Expect:** Dataset picker. Top insights preview or a quiet empty preview (not a fake â€œyou have no datasetsâ€ when you do).

### INS-02 â€” View full scan  `high`  `/insights`
1. Click **View full scan**.
**Expect:** Dataset page Insights/Analysis section with the longer list.

### INS-03 â€” Empty org  `low`  `/insights`
Only if you have a user with zero datasets.
**Expect:** â€œNo datasets yet â€” upload oneâ€¦â€ â€” not a crash.

### INS-04 â€” DirectQuery chip  `low`  `/insights`
1. If Demo â€” Live Orders is listed, select it.
**Expect:** A live marker if the UI shows one. Preview either runs or explains why not.

### INS-05 â€” Search datasets  `low`  `/insights`
1. If 8+ datasets, search for `Sales`.
**Expect:** List filters. A typo does not trap you with an unusable dropdown.

---

# CONNECTIONS

### CONN-01 â€” List  `high`  `/connections`
1. Open Connections.
**Expect:** List or empty state â€œno connectionsâ€. Demo may include **Demo â€” Live SQLite**.

### CONN-02 â€” New connection name required  `high`  `/connections`
1. Open new connection. Leave name empty. Save.
**Expect:** â€œName is requiredâ€. Modal stays open.

### CONN-03 â€” Create then test  `medium`  `/connections`
1. Create `QA Conn NN` of type PostgreSQL (or the first type) with dummy host values.
2. If Test is offered before save, follow the on-screen rule (often save first).
**Expect:** Connection appears in the list. Failed test shows an error, not a hang.

### CONN-04 â€” Schema / review  `medium`  `/connections`
1. If a connection has **Browse** / **Review**, open it (`/connections/:id/review`).
**Expect:** Tables/columns or a clear empty/error. Confirm/reject controls do not crash.

### CONN-05 â€” Delete QA connection  `low`  `/connections`
1. Delete `QA Conn NN` with confirm.
**Expect:** Removed. Demo connection remains.

### CONN-06 â€” Non-admin list  `medium`  `/connections`
1. As EMEA, open Connections.
**Expect:** Page loads. Creating may be limited. No uncaught exception.

---

# LINEAGE

### LIN-01 â€” Graph  `high`  `/lineage`
1. Open Lineage.
**Expect:** Sources â†’ datasets â†’ reports columns or an empty/honest state. Seeded demo should show edges.

### LIN-02 â€” Click a node  `medium`  `/lineage`
1. Click a dataset node if clickable.
**Expect:** Navigate to that dataset or highlight related edges â€” not a JS exception.

### LIN-03 â€” Load error  `low`  `/lineage`
If the API is stopped (optional).
**Expect:** Try again, not a blank page pretending there is no lineage.

---

# SECURITY (two users, same report)

Use **Use case â€” Regional performance review**.

### SEC-01 â€” Global sees all  `high`  that report
1. Log in as GLOBAL. Open the report.
**Expect:** Multiple regions. `cost` (or margin inputs) present where the story includes cost.

### SEC-02 â€” EMEA row + column rules  `high`  same report
1. Log out. Log in as EMEA. Open the **same** report.
**Expect:** Europe only. `cost` gone (not a column of blanks). Totals smaller than GLOBAL.

### SEC-03 â€” Ask AI inherits RLS  `high`  `/ask`
1. As EMEA, Ask AI total sales on Demo â€” Sales.
**Expect:** Answer consistent with Europe-only data. No global total.

### SEC-04 â€” Row security admin page  `medium`  `/admin/row-security-rules`
1. As ADMIN, open Row security.
**Expect:** Rules list (demo has region Europe on the EMEA role) or empty + create. Expression field validates junk.

### SEC-05 â€” Column security admin page  `medium`  `/admin/column-security-rules`
1. Open Column security.
**Expect:** Page loads. Creating a rule without required fields is rejected.

### SEC-06 â€” Connection rules  `low`  `/admin/connection-rules`
1. Open this URL (may be absent from the rail).
**Expect:** Page or a guarded redirect â€” not an unhandled crash.

---

# MONITORING (admin)

### MON-01 â€” Refresh & jobs  `medium`  `/monitoring/jobs`
1. Open the page.
**Expect:** Job list or empty. Seeded jobs may be paused. Not â€œno jobsâ€ when a load failed.

### MON-02 â€” Deliveries  `medium`  `/monitoring/deliveries`
1. Open Deliveries.
**Expect:** Seeded weekly delivery may appear, paused. Recipients visible.

### MON-03 â€” Activity  `medium`  `/monitoring/activity`
1. Open Activity.
**Expect:** Recent actions or empty. Filter if present.

### MON-04 â€” Analyst blocked  `medium`  `/monitoring/jobs`
1. As EMEA, open the URL.
**Expect:** Not the admin jobs table.

---

# ADMIN

### ADM-01 â€” Users list  `high`  `/admin/users`
1. Open Users.
**Expect:** ADMIN and demo users listed.

### ADM-02 â€” New user validation  `high`  `/admin/users`
1. New user. Leave email and password empty. Save.
**Expect:** Email required; password required for a new user.

### ADM-03 â€” Create QA user  `medium`  `/admin/users`
1. Email `qa.user.NN@example.invalid`, password from TEST_DATA, pick a non-admin role. Save.
**Expect:** Toast success. User in the list. Log in as that user works (optional).

### ADM-04 â€” Roles validation  `medium`  `/admin/roles`
1. New role, empty name, save.
**Expect:** Name is required.

### ADM-05 â€” Create QA role  `low`  `/admin/roles`
1. Name `QA Role NN`. Save.
**Expect:** Appears in the list.

### ADM-06 â€” Organization chart  `medium`  `/admin/org-units`
1. Open Organization chart.
**Expect:** Tree or empty + add. No crash.

### ADM-07 â€” Export policy  `low`  `/admin/export-policy`
1. Open Export policy.
**Expect:** Policy form loads. Save without change is harmless or confirms.

### ADM-08 â€” API key name required  `medium`  `/admin/api-keys`
1. Create with empty name.
**Expect:** â€œName the key firstâ€.

### ADM-09 â€” Create API key  `medium`  `/admin/api-keys`
1. Name `QA Key NN`. Create.
**Expect:** Secret shown **once**. List updates.

### ADM-10 â€” SSO page  `low`  `/admin/sso`
1. Open Single sign-on.
**Expect:** Config form. Enable/save with empty required fields is rejected.

### ADM-11 â€” Audit trail  `low`  `/admin/audit`
1. Open Audit trail.
**Expect:** Events or empty. Filters if present.

### ADM-12 â€” Custom connectors  `low`  `/admin/custom-connectors`
1. Open Custom connectors.
**Expect:** List or empty + create. Name required.

---

# PLATFORM (super-admin)

### PLAT-01 â€” Organizations  `medium`  `/platform/organizations`
1. As ADMIN (allowlisted). Open Organizations.
**Expect:** Default org listed. Create form: name, admin email, admin password.

### PLAT-02 â€” Create validation  `medium`  `/platform/organizations`
1. Click create with all fields empty.
**Expect:** Name, admin email and password are required.

### PLAT-03 â€” Analyst blocked  `medium`  `/platform/organizations`
1. As EMEA, open the URL.
**Expect:** Not the platform org manager.

### PLAT-04 â€” Create org  `low`  `/platform/organizations`
1. Create `QA Org NN` with QA admin email/password from TEST_DATA.
**Expect:** Org appears. Do not create extras in a shared QA box.

---

# SHARE / PRINT / EMBED

### SHARE-01 â€” Share dialog  `high`  a dashboard you administer
1. Share (link icon). Create a link if offered.
**Expect:** A URL. Copy works.

### SHARE-02 â€” Open share link logged out  `high`  `/shared/:token`
1. Private window. Open the link.
**Expect:** That report only. No rail of the whole app. RLS of the share still applies (no extra columns).

### SHARE-03 â€” Print  `medium`  `/reports/:id/print`
1. Print from the builder, or add `/print` to a report URL.
**Expect:** Printable layout. Widgets visible.

### SHARE-04 â€” PDF  `medium`  dashboard
1. Click **PDF**.
**Expect:** Download or a progress/error toast â€” not a silent no-op.

### SHARE-05 â€” Publish  `low`  QA dashboard
1. Publish if you administer it.
**Expect:** Published chip. Unpublish restores.

---

# I18N / RTL

### I18N-01 â€” Language switcher on login  `medium`  `/login`
1. Switch language if a control exists. Switch back to English.
**Expect:** Labels change. Form still submits.

### I18N-02 â€” In-app language  `low`  `/`
1. Switch language in the top bar.
**Expect:** Rail labels translate. No layout overflow that hides Sign out.

### I18N-03 â€” RTL  `low`  `/`
1. If an RTL / direction control exists, turn it on, open a dashboard, turn it off.
**Expect:** Layout mirrors. Maps stay `ltr` enough that they are not clipped (maps force LTR internally).

---

# MOBILE / NARROW

Viewport **390 Ã— 844** (and one pass at **890 Ã— 800** for the rail drawer).

### MOB-01 â€” Login on a phone  `high`  `/login`
1. Narrow viewport. Sign in.
**Expect:** Form fits. Sign in is tappable. No clipped button.

### MOB-02 â€” Rail drawer  `high`  `/`
1. Width 890px or less. Open the menu button.
2. Go to Dashboards. The drawer should close.
**Expect:** Overlay menu, not a squeezed unusable canvas. Escape closes it.

### MOB-03 â€” Dashboard canvas  `high`  a seeded dashboard
1. Phone width. Scroll the canvas.
**Expect:** Widgets usable (scroll OK). No overlapping chrome that blocks charts. Maps not clipped worse than desktop.

### MOB-04 â€” Upload on mobile  `medium`  `/upload`
1. Page is usable; file picker works.
**Expect:** No overlapping buttons. Submit still visible.

---

# Suggested run order

1. AUTH-01 â€¦ AUTH-07  
2. NAV-01, NAV-04, NAV-05  
3. HOME-01 â€¦ HOME-03  
4. DS-01 â€¦ DS-04, DS-09  
5. UP-01, UP-02  
6. ASK-01 â€¦ ASK-06  
7. DASH-01, DASH-03, DASH-04, DASH-05  
8. BUILD-01 â€¦ BUILD-12  
9. MAP-01 â€¦ MAP-05  
10. INS-01, INS-02  
11. SEC-01 â€¦ SEC-03  
12. SHARE-01, SHARE-02  
13. MOB-01 â€¦ MOB-03  
14. Remaining medium/low  

If time is short, stop after step 13. Those are the flows a user actually feels.


---

# FILE 2 of 2: REPORT_TEMPLATE.md


# QA report

Copy this file to `qa/REPORT.md` and fill it in. Do not edit the template in place if you want a clean blank next run.

**Build / branch:**  
**App URL:** http://localhost:3001  
**Browser:**  
**Viewport:** (e.g. 1440Ã—900, plus mobile 390Ã—844)  
**Seeded:** yes / no (`qa/seed.ps1` or Load demo content)  
**Login used for most cases:**  
**Date:**  
**Tester:** (human or agent name)

## Summary

| | Count |
|---|---|
| Total run | |
| Passed | |
| Failed | |
| Blocked / skipped | |

**Top issues** (worst first):

1.
2.
3.

**Notes for the next run** (flakes, missing seed, AI model down):

-

---

## Results

Fill every case you ran. Leave unrun rows out, or mark them skipped with a reason.

| Test ID | Result | What actually happened | Console errors | Notes |
|---|---|---|---|---|
| AUTH-01 | pass / fail / skipped | | none / (paste) | |
| AUTH-02 | | | | |
| AUTH-03 | | | | |
| AUTH-04 | | | | |
| AUTH-05 | | | | |
| AUTH-06 | | | | |
| AUTH-07 | | | | |
| AUTH-08 | | | | |
| AUTH-09 | | | | |
| AUTH-10 | | | | |
| NAV-01 | | | | |
| NAV-02 | | | | |
| NAV-03 | | | | |
| NAV-04 | | | | |
| NAV-05 | | | | |
| NAV-06 | | | | |
| HOME-01 | | | | |
| HOME-02 | | | | |
| HOME-03 | | | | |
| HOME-04 | | | | |
| DS-01 | | | | |
| DS-02 | | | | |
| DS-03 | | | | |
| DS-04 | | | | |
| DS-05 | | | | |
| DS-06 | | | | |
| DS-07 | | | | |
| DS-08 | | | | |
| DS-09 | | | | |
| DS-10 | | | | |
| UP-01 | | | | |
| UP-02 | | | | |
| UP-03 | | | | |
| UP-04 | | | | |
| UP-05 | | | | |
| UP-06 | | | | |
| UP-07 | | | | |
| ASK-01 | | | | |
| ASK-02 | | | | |
| ASK-03 | | | | |
| ASK-04 | | | | |
| ASK-05 | | | | |
| ASK-06 | | | | |
| ASK-07 | | | | |
| ASK-08 | | | | |
| DASH-01 | | | | |
| DASH-02 | | | | |
| DASH-03 | | | | |
| DASH-04 | | | | |
| DASH-05 | | | | |
| DASH-06 | | | | |
| DASH-07 | | | | |
| DASH-08 | | | | |
| DASH-09 | | | | |
| DASH-10 | | | | |
| BUILD-01 | | | | |
| BUILD-02 | | | | |
| BUILD-03 | | | | |
| BUILD-04 | | | | |
| BUILD-05 | | | | |
| BUILD-06 | | | | |
| BUILD-07 | | | | |
| BUILD-08 | | | | |
| BUILD-09 | | | | |
| BUILD-10 | | | | |
| BUILD-11 | | | | |
| BUILD-12 | | | | |
| BUILD-13 | | | | |
| BUILD-14 | | | | |
| BUILD-15 | | | | |
| BUILD-16 | | | | |
| MAP-01 | | | | |
| MAP-02 | | | | |
| MAP-03 | | | | |
| MAP-04 | | | | |
| MAP-05 | | | | |
| MAP-06 | | | | |
| INS-01 | | | | |
| INS-02 | | | | |
| INS-03 | | | | |
| INS-04 | | | | |
| INS-05 | | | | |
| CONN-01 | | | | |
| CONN-02 | | | | |
| CONN-03 | | | | |
| CONN-04 | | | | |
| CONN-05 | | | | |
| CONN-06 | | | | |
| LIN-01 | | | | |
| LIN-02 | | | | |
| LIN-03 | | | | |
| SEC-01 | | | | |
| SEC-02 | | | | |
| SEC-03 | | | | |
| SEC-04 | | | | |
| SEC-05 | | | | |
| SEC-06 | | | | |
| MON-01 | | | | |
| MON-02 | | | | |
| MON-03 | | | | |
| MON-04 | | | | |
| ADM-01 | | | | |
| ADM-02 | | | | |
| ADM-03 | | | | |
| ADM-04 | | | | |
| ADM-05 | | | | |
| ADM-06 | | | | |
| ADM-07 | | | | |
| ADM-08 | | | | |
| ADM-09 | | | | |
| ADM-10 | | | | |
| ADM-11 | | | | |
| ADM-12 | | | | |
| PLAT-01 | | | | |
| PLAT-02 | | | | |
| PLAT-03 | | | | |
| PLAT-04 | | | | |
| SHARE-01 | | | | |
| SHARE-02 | | | | |
| SHARE-03 | | | | |
| SHARE-04 | | | | |
| SHARE-05 | | | | |
| I18N-01 | | | | |
| I18N-02 | | | | |
| I18N-03 | | | | |
| MOB-01 | | | | |
| MOB-02 | | | | |
| MOB-03 | | | | |
| MOB-04 | | | | |

---

## Failures in detail

For each fail, copy this block.

### (TEST ID)

- **Page:**
- **Account:**
- **Steps:**
- **Expected:**
- **Actual:**
- **Screenshot:** (path or none)
- **Console:**
- **Network:** (failed requests, status codes)

---

## Sign-off

- Short run (auth â†’ maps â†’ RLS â†’ mobile) complete? yes / no  
- Full plan complete? yes / no  
- Safe to demo to a user? yes / no / with caveats:
