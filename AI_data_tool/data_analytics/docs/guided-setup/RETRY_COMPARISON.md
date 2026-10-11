# Guided setup — the same seven requests, before and after the Meaning map

Date: 2026-10-10 · Branch: `emad` (nothing committed) · Plans: [PLAN_V2.md](PLAN_V2.md), [../meaning-map/PLAN.md](../meaning-map/PLAN.md) · First round: [EVALUATION_REPORT_V2.md](EVALUATION_REPORT_V2.md)

Same connection ("Nile Express", `nile_express`), same people, same words, same choice of suggestion. The first round's analyses keep their names; the second round's end in **-retry-1**, and so do their datasets. Both sets of dashboards are in the app to open side by side.

Truth in the data: Express late 17.4%; Same Day late 31.6%; returns 11.2% of shipments; cash on delivery returned 15.2% vs about 4.3% prepaid; Upper Egypt latest.

## What changed between the two rounds

1. **The Meaning map** (`services/guided_setup/meaning.py`, table `meaning_facts`): measured once per connection — which rows happen to which (complaints → shipments: 36 per 1,000, found by counting, with no declared join), what became of a row (status, is_late), what each number is and which way is good. Shown in step 1 as "How to read this database", correctable.
2. **Step 2 brings the base along:** asked about events or an outcome and comparing groups → the first suggestion keeps every base row with the event or outcome attached; an events-only dataset is marked "Counts only".
3. **An outcome is measured, not filtered to:** "only the returns" on data that keeps every shipment no longer narrows the dashboard to the returned rows.
4. **The size check** (no AI): every count-per-group chart gets the share per group beside it; when the count merely follows group size the share comes first and the count says "(follows the size of each group)"; groups under 30 rows are left out of the ranking.
5. From the first report's open list: chart previews in step 4, one removable dashboard filter for the scope, "Late / Not late" instead of "True / False", reader captions under numbers, pages designed during step 3, Ask AI reads the same map.

## Side by side

| # | Request | First round | -retry-1 | Better? |
|---|---|---|---|---|
| 1 | Express only: how many late, which governorates | 2,971 late = 17.2%; **count** by governorate (Cairo 727); rate by region only | 2,971 late = **17.4%**; rate by governorate — **Assiut 28.1%, Alexandria 16.2%** — beside the count, which "follows the size of each group"; same for parcel category | **Yes** — the "where" is now answered by rate |
| 2 | (Egyptian Arabic) returns only: reasons, which governorates and payment methods have more | Returns-only data: counts. Cairo 1,891; cash on delivery 6,142 | All shipments with their status. **Return rate 11.2%**; by payment **cash on delivery 15.2% vs wallet 4.2%**; by governorate **Suez 13.1%** leads while Cairo leads only by count | **Yes, most of all** — the first round's "Cairo" and "cash on delivery 6,142" said who is big; this says who returns more |
| 3 | Revenue 2025 only: fees per month, top customers, best-earning service | 4.35M; per month; top 10 customers; International 1.92M | Same, plus fees by customer segment (e-commerce sellers 3.46M) | Same (was already right) |
| 4 | (Formal Arabic) damaged-parcel complaints only: which branches, compensation, hours to resolve | Complaints-only data (252 rows): Cairo Central 63 — a count; 109,858 EGP; 23.1 hours typical | All 64,000 shipments with a "has damaged complaint" flag. Count by branch (Cairo 63) **and rate by branch: Assiut 1.2%, Alexandria 0.3%**; by service: Standard has most (124) but Same Day the highest rate. 109,858 EGP. **Resolution hours missing** — the new dataset did not carry them | **Yes for the owner's example** (Cairo's count is its size); **worse on one question** (hours to resolve) |
| 5 | Same Day to Giza (broad dataset chosen): on time? ratings? | 32.4% late, rating 3.83, late 2.83 vs on time 4.32 (first shown as True/False) | 844 late of 2,642 as a split "Late / Not late"; rating 3.83; scope is one dashboard filter. No single "% late" number on the first page in this run | About the same; labels and filter better, headline share missing this time |
| 6 | Drone deliveries (not in the data) | Says the data has none; shows all deliveries | Same honesty; adds late share and returned share by region | Slightly better |
| 7 | No "About you" | General page; return rate 11.2%, late 17.7% | Late 17.7% with **late rate by region and by origin branch (Minya 24.6%, Cairo Central 17.6%)**, ratings by branch | Better |

As a user I would now rate the seven at roughly 95 / 95 / 95 / 90 / 88 / 90 / 90 — about **92%**, up from about 90%, with the real gain on the two requests that compare groups (2 and 4), which is what the Meaning map was for.

## Still not 100% (honest)

1. **Runs vary.** The pages depend on the AI's answer: the same request gave a headline "% late" in one run and a split in another (scenario 5). Several retries had to be designed twice — some because my own code edits restarted the server mid-run, some because of faults the retry exposed (below).
2. **A base-grain dataset can lose a detail of the events.** Scenario 4's new dataset did not carry resolution hours, so that question went unanswered where the first round answered it. The rule now asks for every number the questions need; it was not re-verified on that scenario.
3. **Rates are per 100, not "per 1,000"** in the charts (1.2%, 0.3%); for rare events a per-1,000 figure would read better.
4. **The Meaning map has been run on one database only.** Its logic is counting, not names, and the unit tests cover it, but a second database of a different shape is still to be tested. Inferred links need an id-like column of the same name in both tables.
5. **Not built from the meaning-map plan:** the "we need the base — add it" one-click repair (the card sends the person back to Choose data instead), named measures as ready-made fields in the builder, the builder's "Show per <base>" button, the Insights page and the Dashboards page's own designer reading the map.
6. **Not built:** the "Did this answer what you wanted?" line in the builder.
7. **Not tested:** a non-admin user, uploads, live datasets, several datasets in one analysis; the full backend and frontend suites (only the guided-setup, meaning and Ask AI context tests: 225 backend, 547 frontend, types clean).

## Faults the retry itself exposed, and fixed

| Seen | Fix |
|---|---|
| The new "Late / Not late" label column made the title check refuse every share chart | Label columns join the rows after the profile is taken |
| The dashboard was narrowed to `has_damaged_complaint = True`, leaving no base | A yes/no column is never a scope |
| "Only the returns" narrowed a full dataset to the returned rows | An asked-about outcome is measured over all rows |
| Every chart refused: "filter column 'status' is not in this data" | The map shown for a dataset names only columns it kept; a filter for what the dataset already is, is dropped |
| `has_x = 1` refused | 1 / yes / true mean the column's True |
| "Share late: 100%" | A share of an outcome is never filtered to that outcome or its label |
| "Top customer paid 1,299" (really 1.3M) passed the number check | A bare number no longer passes as a scaled one |
| "Reasons — share of each group: 100% / 0%" | A rate that is all 100s and 0s is not added |
| Complaints listed as counted against customers as well as shipments | One base per kind of event: the finest |
