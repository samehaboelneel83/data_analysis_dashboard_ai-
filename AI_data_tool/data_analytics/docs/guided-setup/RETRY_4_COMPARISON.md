# Guided setup — the same seven requests, retry-4 against retry-1

Date: 2026-10-12 · Branch: `emad` · Earlier rounds: [RETRY_COMPARISON.md](RETRY_COMPARISON.md) (retry-1, 2026-10-10), [RETRY_2_COMPARISON.md](RETRY_2_COMPARISON.md) (retry-2 and -3, 2026-10-11)

Same connection ("Nile Express"), same seven people, same words. Each scenario was run **once**, from an empty start, with nobody intervening; settings were the defaults. This round's analyses and datasets end in **-retry-4**.

Truth in the data (unchanged): Express late 17.4%; Same Day late about 32%; returns about 11.2% of shipments; cash on delivery returned about 15.2% against about 4.2% for a prepaid wallet; Upper Egypt latest.

## Side by side

| # | Request | retry-1 | retry-4 | Verdict |
|---|---|---|---|---|
| 1 | Express only: how many late, which governorates | 2,971 late = 17.4%; rate and count by governorate; typical days; by parcel category. 10 charts, 5 of 5 questions | 2,971 late; rate by region (Upper Egypt 26.9%) and by governorate (Assiut 28.1%); count by governorate marked "follows the size of each group"; late against on time as a split; typical days by governorate; the late shipments listed. 9 charts, 4 of 5 | **About the same.** The facts are all there and right. Two small steps back: the share late is shown as a split, not as one "17.4%" number; and one question ("which governorates have the most") is listed as "could not answer" although the chart beside it answers it |
| 2 | (Egyptian Arabic) returns only: reasons, which governorates and payment methods | Return rate 11.2%; reasons; Suez 13.1% by rate, Cairo by count; cash on delivery 15.2%. 7 charts, 5 of 5 | Return rate 11.3%; reasons; Suez 13.2% by rate **and** Cairo 1,890 by count, the count marked as following size; cash on delivery 15.3% against wallet 4.3%; reasons by governorate; the returned shipments listed. 9 charts, 5 of 5 | **Same, fuller.** The 0.1-point difference is deliberate: shipments still in transit are now left out of the share (they are not yet delivered or returned) |
| 3 | Revenue 2025: fees per month, top customers, best-earning service | 4.37M; per month; top customers (745,900 leads); International 1.92M; by segment. 9 charts, 5 of 5 | The same numbers, plus cash collected beside the fees (12.87M), fees and cash by segment and by region, and month-by-month as a filled trend (+52% January to December). 13 charts, 5 of 5 | **A little better** in reach; two of the page summaries open with a clumsy sentence ("this page does not list fees by service type or by month") |
| 4 | (Formal Arabic) damaged-parcel complaints: which branches, compensation, hours to resolve | 63 at the top branch; 109,858 paid; rate by branch (1.2% against 0.3%); **hours not answered**. 9 charts, 4 of 5 | 252 complaints; 109,858 paid; **hours answered: 29.4 on average**; count, rate (1.2% against 0.3%) and compensation by branch; by service; three monthly trends. 17 charts, 5 of 5 | **Better** — the question retry-1 could not answer is answered. One fault: "share open 0.0% / share resolved 0.4%" are shares of all shipments, not of complaints, so they mislead |
| 5 | Same Day to Giza: on time? ratings? | 844 late of 2,642 as a split; rating 3.83; **no single "% on time"**. 4 charts, 2 of 5 | **On time 67.6%** as the headline; rating 3.83; both by parcel category and by month. 15 charts, 5 of 5 | **Clearly better** — the largest gain of the seven. (A chart titled "complaint rate by category" shows counts) |
| 6 | Drone deliveries (not in the data) | Says the data has none; shows all deliveries with late and returned shares by region. 9 charts, 4 of 4 | The same honesty, word for word in spirit ("this data has nothing called drone deliveries, so this page shows everything it holds"); totals, by governorate and region, late rate by region. 10 charts, 5 of 5 | **Same** |
| 7 | No "About you" | Delivery time by service; late 17.7%, highest in Upper Egypt; ratings by region and branch. 12 charts, 6 of 6 | Outcomes (54,885 delivered, 277 lost); late rate by service (Same Day 31.5%); delivery time by service; fees by month; cash by parcel category; return reasons. 11 charts, 6 of 6 | **Same quality, different choice of subject** — with nothing said about the person, each round picks its own six questions |

Every figure I checked against the truth above is right in both rounds.

## The measurable differences

| | retry-1 | retry-4 |
|---|---:|---:|
| Scenarios that produced a dashboard on the first run | not all (several designed twice) | **7 of 7** |
| Product faults that had to be fixed during the round | 9 | **0** |
| Questions the pages answer | 31 of 35 | **35 of 36** |
| Charts (not counting filters and links) | 60 | **84** |
| Pages | 20 | **28** — every dashboard gained a page for looking at one branch, service or category at a time |
| Kinds of chart used | 6 | **10** (added: filled trend, two-scale bar and line, list of headline numbers, treemap) |
| Filters on the pages | 0 | **22**, each the control that suits it (buttons for a few values, a dropdown for many) |
| Links between pages | 0 | 7 per dashboard |
| Time per scenario | 134–379 s, 204 s on average | 179–234 s, **198 s** on average |

## My evaluation

**As a user I would rate retry-4 at about 94%, against about 92% for retry-1.** Scenario by scenario: 93 / 96 / 94 / 93 / 95 / 92 / 93, against 95 / 95 / 95 / 90 / 88 / 90 / 90.

1. **What a dashboard *says* improved a little; what it *is* improved a lot.** The answers were already mostly right in retry-1. The clear content gains are the two requests retry-1 left partly unanswered (4: hours to resolve; 5: the on-time share). Everything else is the same facts. What changed visibly is the dashboard around them: filters, a detail page, links between pages, trends, more kinds of chart — a reader can now question the page, not only read it.
2. **It is dependable now.** Seven of seven on the first run with no fix needed, where retry-1 needed nine fixes and several redesigns. This is the improvement I would weigh most.
3. **It has not got slower** for doing more: 198 s against 204 s on average.
4. **It still varies from run to run.** The questions drawn from the same words differ each time, and so do the data suggestions and their order. One run each is a small sample; the scores are my reading, not a measurement.

## Faults seen this round (not fixed)

1. **A question can be listed as "could not answer" when it was answered** (scenario 1: "which governorates have the most late shipments" — the count by governorate is on the same page, filed under another question).
2. **A share can be taken over the wrong base** (scenario 4: open and resolved complaints as a share of all shipments — 0.0% and 0.4% — instead of a share of complaints).
3. **A title can say "rate" over a chart of counts** (scenario 5, complaints by parcel category).
4. **A page summary can open by saying what the page does not show** (scenario 3, twice).
5. **Scenario 1 lost its single "17.4% late" headline** to a split of late against on time; the rate is there by region and governorate, not as one number.
6. **The suggested pages have category filters but no date filter**; the from–to date control added on 2026-10-12 is used by the dataset-level suggester, not yet by guided setup.

## About this run

* **Scenario 5 was run twice.** The earlier rounds chose "the broad suggestion" by its position in the list. This time the suggestions came in another order, and my script picked a complaints-only dataset — which answered a different question. That was the script, not the product; it is kept, renamed to say so (analysis 61, dataset 300). The scenario was rerun (analysis 64, dataset 303) and that is what is compared above. On the rerun the choice was the Same-Day-to-Giza dataset (2,666 rows), not the all-Giza one (11,672) used in retry-1 and -2 — the list had changed again.
* **Dashboards were not created from the suggested pages this time.** In the earlier rounds they were made by hand in the browser with every page ticked. The pages are in the last step of each analysis, ready to be made.
* Not tested, as before: a non-admin user, uploads, live datasets, several datasets in one analysis, a second database of another shape.

## Where to look

| # | Analysis (guided setup → Nile Express) | Dataset |
|---|---|---|
| 1 | Express shipments … -retry-4 (57) | 296 |
| 2 | المرتجعات … -retry-4 (58) | 297 |
| 3 | Delivery fees … -retry-4 (59) | 298 |
| 4 | شكاوى الطرود التالفة … -retry-4 (60) | 299 |
| 5 | Same-day deliveries to Giza … -retry-4 (64) | 303 |
| 6 | Drone deliveries … -retry-4 (62) | 301 |
| 7 | Shipments … -retry-4 (63) | 302 |
