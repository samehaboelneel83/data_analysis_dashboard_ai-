# Guided setup — final evaluation report

Date: 2026-10-07 · Branch: `emad` (nothing committed) · Plan: [PLAN.md](PLAN.md)

## 1. What was built

The user journey agreed with the owner, end to end:

**Connect → Understand → Choose data → Check & discover → Dashboard**

| Step | What the user gets |
|---|---|
| Connect | New connection goes straight into the setup. "Let AI read a few sample rows" is ticked by default (can be unticked). |
| Understand | Plain description of the database, tables ranked by usefulness (main / lists / system), **measured** date ranges, sample rows (row rules applied, personal values masked), questions the data can answer, edit any description, "Ask AI again". |
| Choose data | Optional "About you" (work, focus, what to know, what to leave out; asked once, reused everywhere). 2–3 AI datasets, each **Includes / Leaves out / Why**, each test-run on the database before it is shown; preview; change it by chatting; use existing datasets; build it myself; create (import job) and continue. |
| Check & discover | Per dataset: what is wrong → why it matters → what to do, with **Fix it** (prep step) and **Warn me on every refresh** (saved check); rules across columns proposed by the AI and **verified on the rows**; insights reworded for the person's work, nonsense filtered out. |
| Dashboard | 3 designs from the app's designer, told the brief and the findings; every chart drawn before it is offered and says why; change by chatting; or start blank. Opens in the builder (suggestion pane + copilot keep helping). |

Old pages kept, plain first on top: dataset **Columns** and **Rules & alerts** tabs ("What you should know", works for uploaded files too), **review page** (database summary), **Insights page** (what the setup found). `nan` now reads **Empty**. "Guided setup / Continue setup · step n of 4" on every connection, "Continue setting up" on Home, "Always show details" in the account menu. English and Arabic everywhere.

Security (decision D1): the AI reads exactly what the logged-in user may read — connection visibility, connection row rules parsed into every SQL it runs, personal values masked. Creating datasets stays admin-only (as the app's import already is). A security hole was closed on the way: any member could read the review catalog of a connection hidden from them.

## 2. How it was tested

* **Automated:** backend 120+ new tests (guided setup: access, journeys, understand, datasets, health, dashboard); frontend ~70 new tests. Frontend suite: **3,922 / 3,923 pass** (the one failure, `ExportDialog`, is an existing timing-flaky test that passes alone; not touched). Type check clean, production build OK. Backend full suite: see section 6.
* **As a real user, in Chrome (Claude in Chrome extension), on databases of different shapes:**
  * **EGX Stocks** — a database never connected before (Egyptian Exchange: 2 tables, 642,725 rows), persona: long-term private investor. Full run: new connection → Understand → About you → datasets → import (621,835 rows) → check → fix → dashboard.
  * **Cars DB** — listings + real estate (4 tables, 58,498 rows), persona: used-car dealer in Cairo. Full run via the API and UI, including a chat change and an Arabic run.
  * **Non-admin user** (`demo-emea`) — sees only their connection; hidden connections 404; cannot edit descriptions (403) or create datasets; offered existing datasets.
  * **Arabic / right-to-left** — UI and AI text (dataset names, purposes, reasons in Arabic; queries valid).

## 3. Problems found while testing as a user — and fixed

| # | What a user would have seen | Cause | Fix |
|---|---|---|---|
| 1 | Understand waited **5+ minutes** on a blank screen | All AI endpoints were down; the page waited for them | Facts answer at once (~0.04 s); AI words written in the background; the page says when the AI is slow |
| 2 | Leaving and returning re-asked the AI; switching language re-asked | Answer kept per one key only | Asked **once per language**, kept until "Ask AI again"; corrections never trigger a re-ask |
| 3 | "Covers 1998 through **2011**" — real data runs to 2026 | Model guessed the period from sample rows | Exact MIN/MAX measured per main table (as the user); model told to use only those periods |
| 4 | Stock table "May 2009 – May 2023 (approximate)"; real: **Jan 2000 – Dec 2023** | Sync statistics come from a sample | Same measurement; "approximate" disappears once measured |
| 5 | Dataset suggestions **never appeared** (EGX) | A date in the preview rows could not be saved as JSON; the step stayed "pending" and every visit restarted it | Rows made JSON-safe; **every background job now records its own failure** on a fresh session — nothing can stay pending |
| 6 | Whole app **froze** | A background job held a DB transaction open while waiting for the AI; the dev server's startup ALTER queued behind it, everything else behind the ALTER | Every job ends its transaction before any long wait (AI call, remote query) |
| 7 | Three near-identical dataset suggestions | Prompt | One broad dataset + different angles, each saying what it adds |
| 8 | Dataset names like `daily_stock_performance` | Prompt | Plain names ("Daily individual stock prices") |
| 9 | Investor asked to compare stocks with the index; got "join it later yourself" | Joins limited to declared relationships | Join on shared same-meaning columns (date); EGX now offers "Stocks vs EGX30 market comparison" |
| 10 | AI "repair" crashed on a suggestion missing its SQL | Unchecked model output | Safe reads + strict structured output |
| 11 | Check said "**10%** of rows: stock dropped more points than its price" — false | AI compared a **percentage** with prices | Percentage columns labelled for the model; a rule broken by >10% of rows is treated as a wrong rule |
| 12 | Insights: "closing price in Nov-2023 reached **1.4M**", "outliers carry **113%** / **−33%**" | Statistics engine **sums** prices/index levels; impossible shares | `sensible()` drops shares outside 0–100% and totals/trends of level-like measures |
| 13 | A "Yes or empty" column called "the same value in every row" | Constant check ignored blanks | Only constant when almost no blanks |
| 14 | −1 ages reported twice; "blanks misread as No" on a number column; 66.5% shown as 66% | Wording / rounding | Fixed |
| 15 | Four near-identical "extreme values" lines | Noise | Merged into one line naming the columns |
| 16 | Market data called "**your inventory**" | Model framing | Instructed: describe the data as what it is |
| 17 | Empty insights section with no word why | — | Plain note; dashboard step still charts the questions asked |
| 18 | "Fix it" looked like plain text | Styling | Primary button |
| 19 | Arabic screen showing English suggestions with no hint | Kept answer in another language | Hint: "Suggest again / Check again to get it in Arabic" |
| 20 | "EGX30 index trend" line **stopped at 2004** on data running to 2026 | The designer put a 20-row limit on a time axis (keeps the earliest periods) — also affects the Dashboards page's "With AI" | A grouped time axis never gets a row limit (`suggest_dataset_dashboard.polish_widget`) |

## 4. Evaluation as a user — honest scores

| Step | Score | Why |
|---|---|---|
| Connect | 9/10 | Simple, tested, goes straight into the setup. |
| Understand | 8.5/10 | Clear, fast, correct after fixes 3–4; ranking puts business tables first; edits and sample rows work. Questions it suggests are generic. |
| Choose data | 8.5/10 | Strong: plain names, Includes / Leaves out / Why, real joins, chat changes, verified queries, Arabic. Takes 15–60 s. |
| Check & discover | 7.5/10 | Data health is very good (found real problems: 254 old cars with < 10,000 km, 225 "New" cars older than a year, 57 stock rows with price 0 but change ≠ −100%). Insights depend on the statistics engine, which is weak on non-additive data (filtered, but then sometimes nothing is left). |
| Dashboard | 6.5/10 | Fast, every chart runs, follows the findings (medians, excludes unknown ages). But on time-series data it misses the obvious question: "Top 10 stocks by **median daily** change" ≈ 0 for all → alphabetical order; a "median change = 0" KPI; a meaningless "stock price ÷ index level = market share". |
| Old pages, plain first | 8/10 | Works on Columns, Rules & alerts, review, Insights; uploads get it too. |
| Overall | **8/10** | The journey a non-technical user needed now exists and is understandable. The remaining weakness is chart **meaning** in the dashboard designer, not the flow. |

## 5. What to do next to make it better (priority order)

1. **Dashboard designer — reject charts that say nothing.** After drawing a chart, check its result: all values (nearly) equal, a "top N" where the values tie, a KPI that is exactly 0 on a change measure → drop or replace. Apply to the dataset designer the result checks the brief-first designer already has (`source_brief.assess`).
2. **Support "growth over a period"** (first vs last value per entity: stock, product, branch) as a measure the designer can propose. It is the first question of investors, managers and analysts on any time-series data.
3. **Teach every engine what a number means, once.** In Understand, let the AI (verified by the user) mark each numeric column as *amount* (sum it), *level* (average it: price, index, balance), *percentage/change* or *identifier*, stored in column meta. The statistics engine, designer and checks then stop summing prices — for every database, not just the setup.
4. **Block meaningless derived measures** (dividing a price by an index level, summing percentages) in the designer, using the classification above.
5. **Keep AI rewording honest.** Check that each reworded insight keeps the original numbers and column names; show the original under Show details. (Seen: "cars with missing age data have an average age of 6.5" — the source finding was about missing mileage.)
6. **Per-entity outliers.** On data with a key like ticker/branch, compute extreme values within each entity; across different stocks, "prices go from 0 to 30,848" is expected, not a problem.
7. **Speed.** AI steps take 15–90 s. Show which part is running ("trying query 2 of 3"), and pre-compute Understand words during the first sync.
8. **Mark stale results.** Kept results written by an older version of the checks keep their old wording until "Check again"; store a version and offer a refresh when it changes.
9. **Guided setup for uploads.** Uploaded files get the quick health; give them the full Understand → Check → Dashboard journey too.
10. **Non-admins.** They cannot create datasets (by design); add "Ask an admin to create this dataset" so the journey does not dead-end.
11. **Test environment.** Do not run the backend test suite inside the live backend container while the app is in use (some tests run startup migrations against the live DB); the Chrome extension's mouse clicks were intermittently dropped on some buttons (DOM clicks worked — verify with a real mouse).
12. **Commit** the work (nothing is committed yet).

## 6. Test results (final)

| Suite | Result |
|---|---|
| Backend, full (inside the backend container) | **7,162 passed**, 23 failed, 25 errors — the same 23 + 25, in the same files, as on the untouched last commit (container-only: files outside `backend/` are not mounted there, environment settings). No new failure. |
| Backend, guided setup + layer rules + metadata + designer | all pass |
| Architecture docs test (full repo layout) | 35 / 35 (counts were already stale before this work; updated) |
| Frontend, full | 3,922 / 3,923 — the one failure (`ExportDialog`) is an existing timing-flaky test, untouched, passes alone |
| Type check / production build | clean / OK |

## 7. Follow-up, 2026-10-08 — "the dashboard needs a column the dataset left out"

**Owner's test:** on "Pricing & Inventory Health" (dataset "Cars 2015+"), a dealer wanted each car's link. The database has `item_url`; the dataset left it out (links are left out by default). Ask AI said it is not available, and the dataset page offered no way to add it — only rebuilding a dataset by hand and the dashboard on it.

**Built — "Change the data"** (dataset page, next to "Refresh from source"):
* **Tick columns** of the source table the dataset does not have yet, each with its plain description ("item_url — the direct web link to view the specific car listing"); no AI needed.
* **Or ask in plain words** ("I need the link of each car"): the AI edits the dataset's query; it is checked and run as the person.
* The person sees **Adds / Removes / rows** and a preview, then applies. The dataset is re-imported **in place** (same dataset), so its dashboards keep working; a column a chart, filter or alert uses can **never** be removed (refused with the reason).
* Admin-only (as importing already is); uploads and live datasets say plainly why it does not apply.

**Tested as the user in Chrome:** typed "I need the link of each car" → Adds: item_url, Removes: nothing, 9,319 rows → applied → dataset 12 columns, dashboard's 8 charts untouched; `item_url` now in the dashboard's field list.

**Two more bugs found on the way, fixed (they affected every dashboard):**
| What the user saw | Cause | Fix |
|---|---|---|
| Dashboard assistant: "Added a table showing price, make, model and the link" — the table showed **price only** | The assistant's settings are single values; a table's column list was silently dropped | Columns travel as one comma-separated value, checked name by name (`report_copilot._clean_config`); the assistant is told never to claim a column it did not set |
| Same table, even with columns set | A raw table with a measure listed the measure alone, ignoring the named columns | Named columns win (`widget_data`) |
| Links in tables were plain text | — | Web addresses in table cells are clickable (new tab, safe `rel`, short label, no cross-filter on click) |

