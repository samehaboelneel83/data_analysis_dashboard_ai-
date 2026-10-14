# Guided setup v2 — what was built, how it was tested, how useful it is

Date: 2026-10-10 · Branch: `emad` (nothing committed) · Plan: [PLAN_V2.md](PLAN_V2.md)

## 1. What was built

| Plan part | Built |
|---|---|
| **Flows** — steps 2–4 several times on one connection | Table `setup_flows` (alembic 0061); every step route takes `flow=`; "Your analyses" strip on the setup page with **New analysis**; Home lists each unfinished analysis; old journeys keep their progress (copied into their first flow on first read). |
| **The Demand** — what the person wants, written once and checked | `services/guided_setup/demand.py`. One sentence shown back ("What you want"), the questions, and the part of the data asked for — found in the rows, never trusted from the model. A subject the data does not hold is said plainly with what the data does hold. "Not right? Change it" rewrites it and the dashboard is designed again for it. |
| **Step 2** — the subject first | The first suggested dataset is exactly what was asked ("only Express"), the broad one second; never narrowed by what is being measured (late, returned), so shares can be shown; never named after something the database does not hold. |
| **Step 3** — cleaned for you | `services/guided_setup/cleaning.py`. One summary: "Your data is ready — N rows. We fixed 3 things for you… 2 things to know…". Everything else under **Show details and undo**: each automatic fix with Undo / Apply again, the other findings with Fix it, the full report link. Fixes are ordinary prep steps marked `origin: setup`; an undone fix is never re-applied. Only datasets the analysis itself made are cleaned. |
| **Step 4** — pages that answer | `services/guided_setup/answer.py`. Every chart answers one of the person's questions; simple charts first (number, sorted bar, line, table), an advanced chart only under its stated condition; the asked-for part of the data applied to every chart; charts that say nothing (flat, one bar, zero, mostly "unknown") refused and replaced; each page opens with the answer in words, every number checked against the charts. Several pages are suggested (different angles); **the ones ticked become the pages of ONE dashboard**, and more can be added to the same dashboard later. |

## 2. How it was tested

* **Automated:** backend guided-setup tests 150 pass (about 50 new: demand, cleaning, answer, flows, dashboard routes); frontend setup, home and lib tests 538 pass; type check clean. The full backend and frontend suites were **not** run (the backend suite must not run in the live container while the app is in use).
* **As a user, on a database never connected before:** `nile_express`, a courier company generated for this test (`qa/fixtures/generate_logistics_db.py`: 6 tables, 64,420 shipments, deliberate mess and known truths). The connection was created in the browser with only its name and connection details.
* **Seven analyses on that one connection**, different people, wording and languages. Scenarios 1 and 2 were done end to end in the browser; 3–7 were driven through the same API the screens call (to save waiting time), then their dashboards were created and opened in the browser.

## 3. Results, as the user would judge them

Truth in the data: Express late 17.4%; Same Day late 31.6%; returns 11.2% of shipments; cash on delivery returned ~3× as often as prepaid; Upper Egypt slowest; a peak every November.

| # | Who / how they wrote | Asked | Got | Useful |
|---|---|---|---|---|
| 1 | Operations manager, English | "I need Express shipments only — how many are late and in which governorates?" | Dataset of Express only (17,427 rows). Dashboard, 3 pages: 2,971 late = **17.2%**; late by governorate; late **rate** by region (Upper Egypt 26.6%, Canal 14.8%); typical delay; the list. | **95%** |
| 2 | Customer-service manager, Egyptian Arabic | "عايز المرتجعات بس — ايه اسبابها وانهي محافظات وطرق دفع فيها مرتجعات اكتر؟" | Arabic throughout. Returns only (7,203). Reasons, governorates (Cairo 1,891), payment (cash on delivery 6,142 of them), categories. Counts, not rates: a returns-only dataset cannot give a rate. No "total returns" number on the first page in this run (rule added afterwards). | **85%** |
| 3 | Finance, careless typing | "revenue 2025 only — delivery fees per month, top customers, wich service makes most money" | 2025 only (24,988). Total 4.35M; fees per month (November peak visible); top 10 customers; International earns most (1.92M); average fee per service. | **95%** |
| 4 | Quality officer, formal Arabic | "أحتاج شكاوى الطرود التالفة فقط — أي الفروع أكثر؟ كم نعوّض؟ كم ساعة يستغرق الحل؟" | Damaged-parcel complaints only (252), joined to branch names. 252 complaints, 109,858 EGP paid, typical 23.1 hours; by branch; open vs resolved; over time. | **95%** |
| 5 | Branch supervisor, chose the **broad** dataset | "same day deliveries to Giza — are they on time? what do customers rate them?" | Dataset of all Giza parcels; every chart narrowed to Same Day, said on the page ("Showing only service type: Same Day — 2,641 of 11,586 rows"). Late **32.4%**, rating 3.83, rating when late 2.83 vs on time 4.32, by driver and vehicle, over time. | **90%** |
| 6 | Asked for what does not exist | "drone deliveries only — how many and where" | No pretending: dataset named "All deliveries by location"; the card says "We could not find 'drone deliveries' in this data… Did you mean one of these?"; each page says "This data has nothing called 'drone deliveries', so this page shows everything it holds." | **90%** (it cannot give what the database lacks; it says so and offers what exists) |
| 7 | Skipped "About you" | nothing | A sensible general dashboard: 62,662 shipments, delivery time by service, late rate 17.7%, **return rate 11.2%**, late rate by region, reasons for returns. | **85%** |

**Overall: about 90% — not 100%.** The person now gets their subject and their answers instead of everything and a filter. What is missing is listed in section 5.

Parallel flows: all seven analyses sit side by side on the connection, each with its own dataset, check and dashboard; five dashboards were made, one of them with a page added later to the same dashboard.

## 4. Weaknesses found by testing as a user — and fixed

| # | What the user would have seen | Fix |
|---|---|---|
| 1 | "Only Express" produced a dataset of *late* Express only: no share could be shown | Narrow by the subject, never by what is measured |
| 2 | "Express" reported as not found when the dataset was made for it but did not keep the column | A subject the dataset's own query narrows to is recognised |
| 3 | A chart filter comparing a column with another column's *name* — silently ignored, chart drawn unfiltered | Such filters are refused (unknown column, column-as-value, value the column never holds) |
| 4 | A table repeating what a bar already showed | The same numbers in another shape are one reading |
| 5 | Shares shown as 0.174 | Yes/no columns get a percent column (17.4%), created on the dataset when the page is built |
| 6 | Counts only where the question was "where is the problem" | The share per group is asked for beside the count |
| 7 | "On-time rate 32%" on a chart of the **late** share | Both directions exist as columns; titles must match; rows with no outcome yet are left out |
| 8 | "Share of shipments returned — 6,993" (a count under a share title) | A title that promises a share is drawn as a percentage |
| 9 | "Drone deliveries": every shipment relabelled as a drone delivery | See scenario 6 |
| 10 | 311 late Same Day parcels removed automatically as "contradictions" | A broken promise is never a contradiction; an AI rule is applied by itself only under 1% of rows, otherwise it waits under "Fix it" |
| 11 | "Giza" matched the branch "Giza East Hub" (origin) instead of the destination | Outside the named column only a whole value in the person's words counts |
| 12 | Insights such as "Delivered carries 89% of delivery days" and guessed causes | Dropped when they only restate a group's size, total a non-amount, or concern empty values; no guessed causes |
| 13 | A date column filled with "Unknown"; "branch_id has extreme values" | Dates are not filled; identifiers have no extremes |
| 14 | Step 1: dates as "1704099000 to 1790802000"; a phone column read as a date; a text column under "Numbers" | Fixed in `understand.py` |
| 15 | Long page names cut off in the tabs; empty space beside charts; the answer's note cut off | Two-to-four-word page names; rows filled; answer block sized to its text |
| 16 | A daily line over three years | Drawn by month |

## 5. Closed after the first report (same day)

| Gap | Now |
|---|---|
| No drawn preview in step 4 | Each suggested chart is drawn small in its card (a number, sorted bars, a line, parts of a whole, the first rows) from what the server drew (`MiniChart`, `answer.preview_of`). |
| No one-click "Show all" | The asked-for part is ONE filter on the dashboard (the report's own common filter), shown in its filter bar — "service_type is one of Same Day" — and removed there; the charts no longer carry it. |
| "True / False" in charts and answers | A yes/no column gets a label column ("Late" / "Not late"); charts split by it and the answer text use the words. This also removed an inverted answer ("on time: 2.83" was the late parcels). |
| A "share" of 100% | A share of an outcome can no longer be filtered to that same outcome. |
| Speed | The pages are designed while the person reads step 3; step 4 usually opens ready. |

## 6. What is still not 100% (honest list)

1. **Counts where a rate is needed, when the data has no base.** "Which branches have more complaints?" on a complaints dataset shows counts; Cairo leads because it is the biggest. This is the largest remaining weakness, it is general, and it needs new metadata: plan in [../meaning-map/PLAN.md](../meaning-map/PLAN.md).
2. **Technical captions** under numbers ("avg(is_late_pct)") come from the builder's own widget.
3. **Depends on the model's answer.** Two runs of the same request differ: one gives the headline share as a number, another as a split. With the AI off, step 4 falls back to the statistics designer, narrowed to the subject but not question-led.
4. **"Did this answer what you wanted?"** in the builder (plan 4e) is not built; changing a page by chat exists in step 4 only.
5. **Not tested:** a non-admin user, uploaded files, a live (DirectQuery) dataset in the new steps, more than one dataset in one analysis. The full backend and frontend suites were not run.
6. **Left on the machine:** the test database `nile_express`, a second connection "Nile Express (smoke)" used for API smoke tests with its datasets, and archived trial analyses.
