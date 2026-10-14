# Guided setup — the same seven requests, a third time (retry-2)

Date: 2026-10-11 · Branch: `emad` · Earlier rounds: [EVALUATION_REPORT_V2.md](EVALUATION_REPORT_V2.md) (first), [RETRY_COMPARISON.md](RETRY_COMPARISON.md) (retry-1, 2026-10-10)

Same connection ("Nile Express"), same seven people, same words, same choice of suggestion as retry-1. This round's analyses, datasets and dashboards end in **-retry-2**. Each scenario was run **once**, from an empty start, with no hand-holding; the designer's setting was the default (`setup_ai_selection = free`).

Truth in the data (unchanged): Express late 17.4%; Same Day late about 32%; returns 11.2% of shipments; cash on delivery returned 15.2% against about 4.2% for a prepaid wallet; Upper Egypt latest.

## What changed in the platform between retry-1 and retry-2

Nothing was changed in the guided setup's designer for this round on purpose. What changed around it since 2026-10-10: the trade vocabulary was removed from the prompts and word lists (phase 0); "Allow AI" became one switch; stored column classes; the discovery engine; the designer gained an optional "choose among ready charts" mode (off by default). So retry-2 answers one question first: **did making the platform neutral and adding all of that cost the guided setup anything?**

## Side by side

| # | Request | retry-1 | retry-2 | Verdict |
|---|---|---|---|---|
| 1 | Express only: how many late, which governorates | 2,971 late = 17.4%; rate and count by governorate; typical days; by parcel category. 10 charts, 5 of 5 questions | 2,970 late = **17.4%**; the opening sentence now says both "Cairo has the most (727)" **and** "Assiut has the highest rate (28.1%)"; adds late count and late rate by month; a list of the late shipments. 8 charts, 5 of 5 | **Slightly better** — the rate is in the answer's first lines; a trend was added. The parcel-category split is gone (the questions it drew this time asked about time instead) |
| 2 | (Egyptian Arabic) returns only: reasons, which governorates and payment methods | Return rate 11.2%; reasons; Suez 13.1% by rate, Cairo by count; cash on delivery 15.2%. 7 charts, 5 of 5 | The same facts, all of them: 11.2%; reasons; counts **and** rates by governorate (Suez 13.1%) and by payment (15.2% against 4.2%); reasons by governorate; the returned shipments listed. 8 charts, 5 of 5 | **Same, a little fuller** |
| 3 | Revenue 2025: fees per month, top customers, best-earning service | 4.37M; per month; top customers (745,900 leads); International 1.92M; by segment. 9 charts, 5 of 5 | The same numbers; adds average fee by segment; drops the month-by-month view per service. 7 charts, 5 of 5 | **Same** |
| 4 | (Formal Arabic) damaged-parcel complaints: which branches, compensation, hours to resolve | 63 at the top branch; 109,858 paid; rate by branch (1.2% against 0.3%); **hours not answered** (the page said so in its text). 9 charts, 4 of 5 | **First run:** 252 complaints; 109,858; by branch; rate by service; by month — and **hours again not answered**, this time listed plainly as "this data could not answer". 7 charts, 4 of 5. **After the fix below:** hours by branch (77.3 at the slowest, 22.6 at the fastest), rate by branch (1.2% against 0.3%), all five answered | **Same on the first run; better after the fix** |
| 5 | Same Day to Giza (broad dataset chosen): on time? ratings? | 844 late of 2,642 as a split; rating 3.83; **no single "% on time"**. 2 pages, 4 charts, 2 of 5 | **On time 67.7%** as the headline; rating 3.83; typical duration 0.8 days; attempts; on-time rate, rating and duration by month; the scope is now both "Same Day" and "Giza" as one removable filter. 3 pages, 10 charts, 4 of 6 | **Clearly better** — the headline share retry-1 lacked is there |
| 6 | Drone deliveries (not in the data) | Says the data has none; shows all deliveries, with late and returned shares by region. 9 charts, 4 of 4 | The same honesty ("this data has nothing called Drone"); all deliveries by region, governorate, service and status; late rate by governorate. 8 charts, 5 of 5 | **Same** |
| 7 | No "About you" | Delivery time by service; late 17.7%, highest in Upper Egypt 24.2%; ratings by region and branch. 12 charts, 6 of 6 | Late 17.7%, highest in Upper Egypt 24.2%; success rate 87.6%; cost by parcel category; attempts by segment; three monthly trends. 10 charts, 4 of 5 | **A little worse** — one question dropped without saying so, and one misleading sentence (below) |

Every number checked against the truth above is right in both rounds.

### How the runs went

| | retry-1 | retry-2 |
|---|---|---|
| Scenarios that produced a dashboard on the **first** run | not all — "several retries had to be designed twice" (its report, §1) | **7 of 7** |
| Faults in the product exposed by the round | 9, fixed during it | **1** (below), fixed |
| Time per scenario, start to suggested pages | 134–379 s, 204 s on average (one run each, from its log) | 135–248 s, **185 s** on average |
| Charts that draw in the finished dashboards | not recorded | **59 of 59** |

## My evaluation

**As a user I would rate retry-2 at about 92% on the first run and 93% after the one fix — against about 92% for retry-1.** Scenario by scenario: 96 / 96 / 95 / 85→96 / 93 / 90 / 86.

So the honest reading is this:

1. **The answers are about as good as they were, not much better.** Two requests improved (5 clearly, 1 a little), three are the same, one was the same until a fix made it better, and one is a little worse. This round was not expected to raise the content: nothing in the designer was changed for it.
2. **The process is clearly more solid.** Seven of seven worked the first time with nobody intervening, where retry-1 needed redesigns and nine fixes on the way. That is the real improvement, and it held while the prompts were made neutral — removing one industry's vocabulary from the product **cost the guided setup nothing measurable** on the very database that vocabulary came from.
3. **It still varies from run to run.** The questions the AI draws from the same words differ each time (scenario 1 asked about parcel categories in one round and about months in the other), so a chart present in one round can be absent in the next. One run each is a small sample; the scores above are my reading, not a measurement.

## The fault this round exposed, and fixed

| Seen | Cause | Fix |
|---|---|---|
| "How many hours does it take to resolve a complaint?" unanswered — for the second round running | The dataset **did** carry the hours. The automatic clean-up removed the column as "almost all empty": it is empty on every shipment without a complaint, which is 99.6% of them. The existing protection only covers a column the person names by its exact name — never the case for a question asked in Arabic | A nearly empty column is kept when it is filled exactly where another column of the same table says "yes" (or holds a non-zero count): it is a detail of those rows, not a broken column. Read from the rows; no column name is consulted (`health.detail_of`). Rerun: all five questions answered |

Retry-1's report listed this as open item 2 and guessed at another cause; this is the one.

## Still not right (honest)

1. **A question can be dropped without a word.** Scenario 5 lost two of six (comparing Same Day with the other services — impossible once the page is narrowed to Same Day) and scenario 7 one of five; neither was listed under "this data could not answer". It was the same in retry-1 (scenario 5: 2 of 5, nothing listed). Scenario 4 shows the listing works when the cause is a missing column.
2. **A trend's last month can mislead.** Scenario 7 says the delivery success rate "declined from 89.3% to 70.0%". The last month holds 507 shipments still in transit; they are not failures. The platform already sets an unfinished period aside elsewhere (the forecast, the year-over-year view); the guided setup's monthly lines do not.
3. **"Follows the size of each group" is now said only when the platform adds the rate chart itself.** In this round the AI drew the rate charts, so the count charts beside them carry no such note — the reader still sees both, but is not told which to trust.
4. **One rate was written as "0.511" in a sentence** where its chart says 0.5% (scenario 4, first run).
5. **The "choose among ready charts" mode was not used here.** Measured separately on scenario 2: 2–3 of 5 questions answered against 5 of 5 (docs/discovery/PLAN.md §AV). It stays off by default for that reason.
6. **Not tested, as before:** a non-admin user, uploads, live datasets, several datasets in one analysis, a second database of another shape.

## Where to look

| # | Analysis (guided setup → Nile Express) | Dataset | Dashboard |
|---|---|---|---|
| 1 | Express shipments -retry-2 | 263 | Express shipments -retry-2 |
| 2 | المرتجعات -retry-2 | 264 | المرتجعات -retry-2 |
| 3 | delivery fees -retry-2 | 265 | delivery fees -retry-2 |
| 4 | شكاوى الطرود التالفة -retry-2 (the second of the two: the rerun after the fix; the first is kept as it ran) | 270 (first run: 266) | شكاوى الطرود التالفة -retry-2 |
| 5 | same day deliveries -retry-2 | 267 | same day deliveries -retry-2 |
| 6 | drone deliveries -retry-2 | 268 | drone deliveries -retry-2 |
| 7 | delivery performance -retry-2 | 269 | delivery performance -retry-2 |

The dashboards were made from each run's suggested pages with every page ticked.

---

# Afterwards: what retry-2 led to (retry-2b and retry-3, 2026-10-11)

## The five faults diagnosed after retry-2, fixed (retry-2b)

Each rule is read from the rows; no column's or value's name is consulted.

| Diagnosed | Now |
|---|---|
| A delivered share "fell to 70%" because the newest shipments were still on their way | A value that only the newest rows hold is treated as "not finished yet"; a share of any outcome is over finished rows, and the page says once what was left out |
| A comparison that came out level was thrown away and its question left hanging | It is said as the one number with its range: "4.06 — about the same for every parcel category (4.04 to 4.08)" |
| The setup added questions its own scope ruled out (compare Same Day with other services, on a page narrowed to Same Day) | Such added questions are dropped before designing; the person's own questions are never touched |
| "Follows the size of each group" was said only when the platform drew the rate chart | It depends on the counts alone |
| A share was written as "0.511" in a sentence | The answer writer is handed shares with their % sign |

Correction to the report above: no question the person asked was ever dropped silently. The dropped ones were questions the setup had added itself; by design those are not reported.

## Richer dashboards (retry-3)

New setting **"Guided setup: how rich the dashboards are"** — basic · **balanced** (default) · rich. Basic is the designer as it was. What balanced adds, all but the first by plain code after the charts are chosen (`services/guided_setup/dress.py`):

* a wider menu for the AI: eight further chart kinds, each under a condition about the shape of the question;
* **bar after bar is varied by shape:** a page keeps its first two comparisons as bars; later ones are drawn as a ring (a few parts of a whole), a treemap (many parts) or a dot plot (averages or rates of a handful of groups); one total over time per dashboard as an area; a ranking where the top 30% of groups carry 60% of the total as a Pareto;
* **display rule:** groups above the average are marked — good or bad only when the column's stored direction says which, otherwise a neutral colour;
* **a number's history:** sparkline and change against the previous period;
* **filter controls**, **click a group to filter the page**, **buttons between pages** carrying the selections;
* **drill-through:** one more page for a single value of the category the dashboard splits by most (numbers, trend, records), opened from any chart split by it, with a button back.

Every changed chart is drawn again before it is kept; an option the engine refuses is dropped and the chart stays.

**Measured — the seven scenarios run from scratch as -retry-3, one run each:**

| | retry-2 | retry-3 |
|---|---|---|
| Distinct chart kinds | 6 | **11** |
| Share of charts that are bars | 42% | **27%** |
| Pareto charts | 0 | 6 |
| Charts with a display rule | 0 | 17 |
| Numbers showing their history | 0 | 36 |
| Filter controls | 0 | 20 |
| Click-to-filter links | 0 | 83 |
| Buttons between pages | 0 | 49, all wired to their page |
| Drill-through pages | 0 | 7, opened from 19 charts |
| The person's own questions answered | all | **all** (19 of 19) |
| All questions, including the setup's own | — | 33 of 35 |
| Charts that draw in the built dashboards | 59 of 59 | 99 of 99 |
| Time per scenario | 185 s | 207 s |

A first attempt that only widened the AI's menu changed nothing (bars rose to 48%): given more kinds, the model still chose bars. Variety comes from the shape rules, not from the model.

**Not done, honestly**

* The built dashboards were checked through the API (every chart draws, every button and drill link points at a real page) and one was opened in the browser, where its tabs and buttons appear. **How they look was not judged by eye**, and clicking through filters, buttons and the drill page by hand was not done.
* Whether a ring, a treemap or a dot plot reads better than the bar it replaced for a person who "does not know charts" is a judgement; the setting is there to go back to basic.
* One run per scenario. The questions the AI draws still vary from run to run.
* "Change this page" in the guided setup still designs without the dressing step.
* The limit of analyses per connection is now a setting (60 by default; it was a fixed 30).

Retry-3 analyses, datasets 277–283, dashboards named "… -retry-3".
