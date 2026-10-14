# Meaning map — every number read against its base

Date: 2026-10-10 · Branch: `emad` · **Status: phases 1–4 built and tested the same day, phase 5 in part — see [../guided-setup/RETRY_COMPARISON.md](../guided-setup/RETRY_COMPARISON.md). Owner's instruction: build with the recommended decisions of §8.** · Builds on [guided-setup/PLAN_V2.md](../guided-setup/PLAN_V2.md)

## 1. The problem, in the owner's words

> If Cairo has the most complaints, that does not mean the Cairo branch has a problem.
> It may carry 1,000,000 shipments and 1,000 complaints — which is nothing.

Seen on Nile Express (2026-10-10): the quality officer asked "which branches have more complaints?" and got "Cairo Central Hub: 63, Dakahlia: 3". True, and useless: Cairo simply handles the most parcels. The honest answer is complaints **per 1,000 shipments**, and the dataset the dashboard was built on did not even contain shipments.

This is not about couriers. It is the same mistake everywhere:

| Database | The count that misleads | What it must be read against |
|---|---|---|
| Courier | complaints per branch | shipments that branch handled |
| Hospital | deaths per department | patients admitted there |
| HR | resignations per department | people employed there |
| Shop | returns per product | units sold |
| School | failures per class | students enrolled |
| Bank | defaults per branch | loans granted |
| Any | anything per month | how much activity that month had |

**The rule the platform is missing:** a count of events says nothing until it is put beside the number of things those events could have happened to — its **base**. A big group has a big count of everything.

## 2. Why the AI cannot do it today (read from the code)

1. **It sees one dataset at a time.** The designer (`answer.py`, `suggest_dataset_dashboard.py`) is shown the columns of the chosen dataset. A complaints dataset has no shipments in it, so no rate can be formed, whatever the prompt says.
2. **The relationships carry no meaning.** `SourceRelationship` records that `complaints.shipment_id` joins `shipments.shipment_id`. It does not record that a complaint is *something that happens to* a shipment — so nothing knows shipments are the base of complaints.
3. **Nothing records what a row IS.** No field says "one row of this table is one shipment" or that a table holds events, things, or a list of names. Each engine guesses again from column names (`_LEVEL`, `_AMOUNT`, `_ADDITIVE`, `is_intensive` — four regex lists in four files).
4. **Step 2 picks data before anyone asks "compared with what?"** The proposals follow the person's words. "Complaints by branch" yields complaints.
5. **No check catches it afterwards.** The meaning gate (PLAN_V2 4c) refuses flat and empty charts; it does not notice that a ranking is just the ranking of sizes. (`health.beyond_size` does this for insights only, added 2026-10-10.)

Prompting harder will not fix this: items 1–3 are missing **facts**, not missing instructions.

## 3. The idea: a Meaning map per connection

A small, checked description of what the database *means*, written **once** in the Understand step (the AI proposes, the database verifies, the person can correct), stored, and read by every engine — dataset suggestions, the Demand, the dashboard designer, insights, Ask AI. It is metadata **about meaning**, beside the existing metadata about shape (tables, columns, types, joins).

Five kinds of fact, all generic:

### 3.1 What one row is (the grain) and what kind of table it is

```json
{"table": "shipments", "row_is": "one parcel handed over for delivery", "kind": "activity",
 "key": "shipment_id", "when": "created_at"}
```
`kind` is one of: **activity** (things that happen and are counted: orders, visits, shipments), **event-on-something** (complaints, returns, payments, reviews — they happen *to* a row of another table), **thing** (customers, branches, products), **list** (names for codes), **snapshot** (balances, stock levels per day), **system**.

### 3.2 Bases — "counted against what?"

```json
{"events": "complaints", "base": "shipments", "via": ["shipment_id"],
 "share_of_base_with_events": 0.036, "events_per_base": 0.037, "verified": true,
 "shared_groups": ["branch", "customer", "month"], "per": 1000,
 "name": {"en": "complaints per 1,000 shipments", "ar": "الشكاوى لكل 1000 شحنة"}}
```
Found from the direction of the join and **measured**: how many base rows have at least one event, how many events per base row. A link is a base only when the measurement agrees (many base rows, few events each). `shared_groups` are the things both sides can be split by — the groups a rate can be compared across.

A base is not always a table. Three more forms, same record:
* **an outcome inside the table** — `is_late`, `status = 'Returned'` are outcomes *of* shipments: the base is the table's own rows (this is what PLAN_V2's percent columns already draw);
* **a size column** — population, floor area, headcount, seats: "per 100,000 people", "per m²";
* **time** — per day, per month open: a branch opened in June has half a year of anything.

### 3.3 What each number is

One classification, stored once, replacing the four regex lists:
**amount** (add it up: fees, quantities) · **level** (a price, a balance, a temperature: average it, never total it) · **duration** · **rate / percentage** · **score** (a rating) · **count held in a row** (attempts, items) · **identifier / code** (never calculate).
Plus **unit** (EGP, kg, hours) and **direction**: is higher better, worse, or neither. Direction is what lets an answer say "worst" and "best" correctly — a high rating is good, a high delay is bad.

### 3.4 Named measures the business would recognise

Built from 3.2 and 3.3, each with numerator, base, the groups it can be split by, its plain name in English and Arabic, and its value measured on the whole database:
*late rate (17.4%), return rate (11.2%), complaints per 1,000 shipments (36), average fee per shipment (176 EGP), compensation per complaint.*
This list is what a person means by "the numbers of this business". It is offered in Understand ("What this database can measure") and is the vocabulary the Demand and the designer reuse.

### 3.5 How much to trust a comparison

For every base: the smallest group size at which a rate is worth showing (3 complaints out of 20 shipments is 15% and means nothing). A rate on a tiny base is shown greyed with its base, or left out of a ranking.

## 4. How it is built (Understand step, once per connection)

1. **Facts first, no model:** join directions and cardinalities measured with `COUNT` queries run as the person (decision D1 unchanged); yes/no and few-value status columns found from the column statistics the sync already holds; candidate size columns and date columns.
2. **The model names and judges:** what a row is, which links are "happens to", what each number is, its direction, plain names for the measures. Strict structured output; table and column names checked against the catalogue.
3. **The database checks the model:** every base is measured; every named measure is computed once on the whole data. A measure that cannot be computed, or a "base" where events outnumber base rows many times over, is dropped.
4. **The person sees it plainly** in Understand, as sentences they can correct:
   > **How to read this database**
   > · Complaints are counted against shipments: about 36 complaints for every 1,000 shipments.
   > · A shipment can end late (17%), returned (11%) or lost (0.4%).
   > · Money is in EGP. Fees add up; ratings are averaged (higher is better).
   > [Not right? Change it] · [Show details]
5. **Asked once, kept** (owner rule): re-measured when the database is synced again; re-asked only on "Ask AI again"; a person's correction always wins (`description_source = confirmed`, as today).

**Storage.** One new table `meaning_facts` (migration): `data_source_id, kind (grain | base | number | measure), subject (table / column / measure name), body JSON, source (measured | ai | confirmed), verified, measured_value, measured_at`. Datasets inherit through the lineage that already exists (`knowledge.link_columns`): a dataset's `column_meta` gets the number kind, unit and direction of each column, and the dataset records which bases it carries and which it lacks.

## 5. How every step uses it

### Step 2 — choose data: bring the base along
* When the person's request is about an event-on-something (complaints, returns, cancellations…), the **first** suggestion is built at the grain of the **base**, with the event attached: *every shipment, with whether it had a complaint, its type and compensation*. The rate is then simply the share of rows with the event — exactly what the percent columns of PLAN_V2 already draw — and can be split by anything the base has (branch, service, month, customer).
* The card says so in plain words under *Why*: "Includes the shipments without complaints too, so branches can be compared fairly."
* An events-only dataset is still offered second ("just the complaints, to read them one by one") and is marked: *counts only — cannot compare groups fairly*.
* When the base is very large, the suggestion can be a small summary table instead (per branch and month: shipments, complaints) — the map says which groups are shared.

### The Demand — "compared how?"
Each question gets one more field, decided from the map, not from wording: `compare: count | rate | both` and the base it needs. "Which branches have more complaints?" → `both`, base *shipments*. If the chosen data lacks the base, the Demand card says it before any dashboard is designed:
> To compare branches fairly we need the shipments each branch handled. [Add them] · [Counts are enough]

### Step 4 — dashboard: the size check (deterministic, in the gate)
For every chart that counts or totals something per group:
1. find the group sizes (rows of the base per group);
2. if the ranking by count is essentially the ranking by size (rank correlation high, sizes differ) → the chart alone misleads: it is **paired with or replaced by** the rate per base, sorted by rate;
3. groups below the minimum base are greyed or left out of the ranking, and the chart says so;
4. if the dataset has no base → the chart keeps a visible note, "Bigger branches have more of everything; this data cannot show the rate", with the button to add the base.

The answer sentence says both, in the right order:
> Cairo Central has the most complaints (63) because it handles the most parcels; per 1,000 shipments it is average (34). **Gharbia is the highest: 61 per 1,000.**

The designer's menu gains the map's named measures as ready fields, with direction, so "worst" and "best" are never inverted (the "on-time rate" titled over the late share, found 2026-10-10, becomes impossible).

### Step 3 — check & discover
Insights are computed on rates where a base exists, and a finding that only restates size is dropped (generalising `beyond_size`). The number kinds replace the regex lists in `health.py`.

### Everywhere else (same map, later phases)
* **Ask AI:** "which branch has the most complaints?" answers with the count *and* the rate, and says which is which.
* **Insights page and the Dashboards page's designer:** same size check, same number kinds.
* **Builder:** a count-by-group chart offers "Show per <base>" in one click.

## 6. Order of work

| Phase | Content | Size |
|---|---|---|
| 1 | `meaning_facts` table; measured facts (join direction, cardinality, outcomes, sizes); model naming + verification; "How to read this database" in Understand with edit | L |
| 2 | Number kinds, unit and direction into `column_meta` through lineage; replace the four regex lists with one reader (`semantic_guard`) | M |
| 3 | Step 2: base-grain suggestions for event questions; "counts only" mark; Demand `compare` and the "we need the base" card | M |
| 4 | Step 4: size check in the gate, rate pairing, minimum base, answer wording, named measures on the menu | M |
| 5 | Step 3 insights on rates; Ask AI and the other designers read the map; builder's "Show per <base>" | M |
| 6 | Test as users on four databases of different shapes; evaluation report | S |

Phases 1–4 deliver the owner's example end to end; 5 spreads it to the rest of the app.

## 7. Done when (acceptance, as a user, English and Arabic)

* **Nile Express** — "which branches have more complaints?" → the dataset includes shipments; the page shows complaints **per 1,000 shipments** by branch, sorted by rate, with the count beside it; the answer names the branch that is worst *per shipment* and says Cairo's count is its size.
* **Olist** (orders, reviews) — "which sellers get bad reviews?" → share of low reviews per seller's orders, sellers with a handful of orders greyed.
* **Employees (HR)** — "which departments lose people?" → leavers per people employed, not the raw count.
* **A database with no base at all** (one flat table of complaints) → counts, with the plain note that sizes are unknown — never a made-up rate.
* **Direction** — on every database, "best / worst / highest risk" point the right way for a rating, a delay and a cost.
* The map is written once: opening the setup again, or a second analysis, asks the AI nothing new.
* A person's correction in "How to read this database" changes the next dashboard.

## 8. Decisions for the owner

1. **Where the person corrects the map.** Plan: a short "How to read this database" block in Understand (plain sentences, edit in place), details behind a button. Alternative: a separate "Meaning" page per connection.
2. **Default when a base exists.** Plan: show **both** count and rate, rate first when comparing groups. Alternative: rate only.
3. **Events-only datasets.** Plan: still offered second, marked "counts only". Alternative: not offered when the question compares groups.
4. **Minimum base for a rate.** Plan: 30 rows of the base by default, greyed below it, changeable per connection.
