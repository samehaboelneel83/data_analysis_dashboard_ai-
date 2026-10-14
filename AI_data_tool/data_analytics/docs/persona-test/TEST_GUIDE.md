# What to test — persona-test changes (2026-10-12 / 13)

Everything below is live in the app at **http://localhost:3001** (sign in as usual). Nothing is committed.
Each item says where to look, what you should see, and what would be wrong.

## 1. Run one new analysis yourself (the main thing)

1. **Connections → pick any connection → Set up** (try one you know well, and one in Arabic: *sh2on_zobat* or *Held-out H3 — الشحنات*).
2. **New analysis → About you:** write your job and 2–3 questions in your own words.
3. **Choose data → Suggest datasets**, tick what you want, **Next**.
4. **Check & discover**, then **Dashboard**: pick pages, make the dashboard.

What you should see:
- The dashboard opens with **"Your questions"** («أسئلتك» in Arabic): every question you asked, with its measured answer, or why it could not be answered.
- Filter titles, detail pages and notes name columns in your language (no raw names like "corp name" inside Arabic text).
- While a step works: "Running for 0:42. Usually about … here." under the working line.
- On each page, under its summary, one line per question you asked: `• <your question>: <the measured answer>`.
- A question the data cannot answer says so **with the reason**.
- A ranking of an average or a share leaves out groups with too few rows, and the chart says how many it left out.
- If a column holds a few values unlike the rest (index tickers among companies, totals among details), the dashboard has removable "≠" filters for them, and the page note says "Left out: … Remove the dashboard's filter to bring them back."

- A ranking where every group is small says "too few to say which is highest or lowest" instead of naming one.
- A leader that rests on one single row says so ("one single row gives 99% of the leader's total").
- "How many people" counts people, not rows, where one person has several rows.

Wrong would be: a number that contradicts the data, an answer under the wrong question, a "best" group with a handful of rows, or a page in the wrong language.

## 2. Things to look at on any dashboard

| Feature | How to see it | Correct |
|---|---|---|
| Change over a period | A headline tile made for "how much did X go up" | "+79.9%" with "42.75 → 76.89 (first date – last date)" beneath |
| One bar per item | A score form / survey dataset (e.g. *sh2on_zobat*, *Held-out H1*) | One bar per item column, the weakest named on the page |
| One colour for one measure | Any single-measure bar chart | All bars the same colour |
| Compact axes | A chart with very large values | "45T", never "45,000,000,000,000" |
| Personal data | Builder → Fields list | A shield on columns holding emails, names, national IDs |
| Before sharing | **Share** on a dashboard that ranks people or IDs | "N charts here show single records…" naming them |
| Leftovers | Setup → Choose data → "Already made" | "Used by N dashboards"; others' unused datasets folded |

## 3. Arabic

Use the Arabic interface on *sh2on_zobat* or *Held-out H3 — الشحنات*: shares of a status (e.g. «مرتجع») must be percentages, notes and answer lines in Arabic.

## 4. The benchmark (optional, for a developer)

```bash
docker exec -e VALKEY_URL= -e PYTHONPATH=/app datalytics_backend sh -c 'cd /app && python scripts/persona_benchmark.py /tmp/benchmark.json --average /tmp/rep7_score1.json /tmp/rep7_score2.json /tmp/rep7_score3.json'
```

Scores, history and every change are in [REPORT_AND_PLAN.md §6](REPORT_AND_PLAN.md); held-out data in [heldout/](heldout/README.md).

## 5. Test objects made by these runs (yours to keep or delete)

- Dashboard 387 ("الشحنات", from the Arabic held-out analysis), made to check the "Your questions" card; it was built before a fix for Arabic-named derived columns, so one of its charts says a column is missing. A new dashboard from a new analysis does not have this.
- Analyses 81–100 on the ten connections and on the three "Held-out" connections (ids 49–51), with their imported datasets (ids 325 onward). No dashboards were made from them.
- The three "Held-out" connections themselves (SQLite files `/app/uploads/heldout_h1.db` … `h3.db`).
