# Testing the new work on two real databases

Two public datasets were loaded into the local Postgres on 2026-10-12. This guide gives the
connection details and the steps to try everything built since `main`, as a user, in the browser.

## 1. The two databases

| | Online retail | NYC taxi |
|---|---|---|
| What it is | Real transactions of a UK online retailer, 1 Dec 2009 to 9 Dec 2011 | Real yellow taxi trips in New York City, January 2024 |
| Source | UCI Machine Learning Repository, "Online Retail II" | NYC Taxi & Limousine Commission trip records |
| Database name | `online_retail` | `nyc_taxi` |
| Tables (rows) | `invoice_lines` (1,067,371), `invoices` (53,628), `customers` (5,942), `products` (5,131), `countries` (43) | `trips` (2,964,624), `zones` (265), `vendors` (4), `payment_types` (7), `rate_codes` (7) |
| Good for | Dashboards, templates, sharing by team, row rules by country | Large data: import against live, speed |

Both are as published: the retail data has cancellations (negative quantities) and guest orders
(no customer); the taxi data has faulty meter records (zero distance, dates outside January). That
is intended, so the data checks have something to find.

## 2. Connection settings

In the app: **Connections → New connection → PostgreSQL**.

| Field | Value |
|---|---|
| Host | `postgres` |
| Port | `5432` |
| Database | `online_retail` (second connection: `nyc_taxi`) |
| Username | `analytics_reader` |
| Password | in `qa/new_databases.env` (kept out of git) |
| Schema | leave empty |
| SSL | default |

`analytics_reader` can only read these two databases. From a tool on your own machine (not the
app) use host `localhost`, port `5433`.

Suggested connection names: **Online retail** and **NYC taxi**. Give each a one-line description
when you create it (it is used in step 5).

## 3. Sign-ins for the tests

- Administrator: the seeded account in `CLAUDE.md`.
- For sharing you need a second person who is **not** an administrator. Create one in
  **Admin → Users** (for example a "Reader" role), and put them in a team in **Admin → Org chart**.
  Use a private browser window for the second person.

## 4. Large data (NYC taxi)

1. Create the **NYC taxi** connection. Choose the `trips` table and make a dataset in
   **DirectQuery (live)** mode. Expected: it is ready at once, no copy is made.
2. Make a second dataset from `trips` in **Import** mode. Expected: a progress line while about
   3 million rows are copied; the server stays responsive (open another page meanwhile).
3. Build one dashboard on each (a bar of trips by pickup borough, a line by pickup day, a total of
   `total_amount`). Expected: the same numbers on both; note how long each takes.
4. On the imported dataset open the data checks. Expected: they report on the whole table and say
   so when a check used a sample.
5. Refresh the imported dataset. Expected: it finishes and the row count is unchanged; the
   dashboard keeps working during the refresh.
6. Export the `trips` table to a CSV from any SQL tool, then use **Upload** with that file.
   Expected: the upload is read in pieces (memory does not jump) and ends as a dataset.

## 5. Suggested dashboards, with and without AI (Online retail)

1. In your **Profile**, fill **About you** (your job and what you care about).
2. Create the **Online retail** connection with a description. Make a dataset joining
   `invoice_lines`, `invoices`, `products`, `customers`, `countries`; give the dataset a
   description, and a description to two or three columns.
3. Ask for a suggested dashboard with AI on. Expected: charts that fit what you wrote (for example
   revenue by country and by month), a from-to date control on `invoice_date`, and more than bars
   and lines among the suggestions.
4. Turn AI off (the model picker in the top bar) and ask again. Expected: still a sensible
   dashboard with controls, built without AI.
5. In the suggestions panel, add one suggestion, then use the button that adds them all.
6. Open the dashboard's style and try the looks. Expected: headline numbers with a gradient trend
   line, the whole dashboard area changes, text stays readable on the dark looks.

## 6. Templates

In **Templates**:

1. **Executive summary** → **Use template** on the retail dataset. Map revenue (`line_total`),
   date (`invoice_date`), a group (`country_name`). Expected: a finished dashboard that is yours to edit.
2. **What goes together** on `invoice_lines` (basket = `invoice_no`, item = `description`).
   Expected: rules of items bought together, and the role views.
3. Kind **Analysis**: try **What is in the data**, **A number through time**,
   **What is out of the ordinary** and **What a number depends on**. Expected: each makes a
   dashboard that explains itself in plain words.
4. On a **Key influencers** widget, open its settings and switch between the display options
   (bubbles, bars, with and without details).

## 7. Publishing and sharing

Use a dashboard from step 5 or 6. Open **Share** on it.

1. **Share with a person**: type the second person's email, level *Can view*, **Invite**. As that
   person, open **My dashboards → Shared with me**. Expected: it is there and opens.
2. **More options**: share again with an end date of today and *May download* off. Expected: the
   row shows "Ends …" and "No downloads"; as that person, Export is greyed with the reason, and a
   direct download link answers "forbidden".
3. **A team**: choose the second person's team. Expected: you are asked first; afterwards the
   dashboard is under **My team** for them.
4. **Remove access** (the ×). Expected: you are asked first; then the person's link to the
   dashboard says not found.
5. **Publishing** tab: set a category and tags, **Save**. Publish the dashboard (People tab →
   *Everyone in your organisation*). Edit the dashboard, publish the update, then in
   **Published versions** use **Go back to this** on version 1. Expected: readers see version 1,
   your draft keeps your edit.
6. **Archive**. Expected: a message saying how many shares, links and schedules stop; afterwards
   only you and administrators can open it. **Restore** brings it back as a draft.
7. **Owner → Hand over** to the second person. Expected: they now manage sharing; you keep editing.
8. As administrator, tick **Ask for approval before anything is published**, then try to publish
   as the owner. Expected: refused until **Ask for approval** and an administrator's **Approve**.
   Untick it when done.
9. **Links without sign-in**: in the Share dialog the guest-link part says they are switched off.
   Turn on *Allow links that open without signing in* in **Platform settings → Security**, create
   a link, open it in a private window; then remove the maker's access or archive the dashboard.
   Expected: the link says not found.
10. **Row rules** (Admin → Row security): limit the Reader role to `country_name = 'Germany'` on
    the retail dataset. Expected: the second person sees only Germany in the shared dashboard and
    in any export, whatever filters the dashboard has.
11. **My dashboards**: try each section, the search box, the category / tag / owner filters, the
    star (Favourites), and **Reports sent** after creating a schedule in Share → Schedule.
12. Switch the language to Arabic and look at **My dashboards** and the Share dialog again.

## 8. What to note down

For each step: worked / did not, what you saw instead, and for section 4 the times. Anything a
reader could open, download or see that they should not is the most important thing to report.
