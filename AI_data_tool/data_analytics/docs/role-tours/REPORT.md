# Role tours — data engineer, data scientist, data analyst, admin & governance

Date: 2026-10-10 · Done in Chrome on the local app as `admin@datalytics.local` (sees
every feature). Row/column security was checked by calling the API **as** the seeded
"Demo — EMEA analyst". Every bug below was fixed, tested and re-checked; the
"Recommended next" items are not built yet.

## 1. Data engineer — connect, build pipelines, keep loads healthy, trace problems

| What I did | Result |
|---|---|
| Tested connections (working and broken) | Works. **Fixed:** a failed test said only "✕ Failed"; the reason was in a toast that vanished in seconds. It now stays on the row (e.g. *could not translate host name "qa-db.invalid"*). |
| Dataflows page | **Bug fixed (serious):** every scheduled dataflow failed daily with `greenlet_spawn has not been called`. The scheduler loaded the flow's creator without their role, and the row-security check read it lazily. "Monthly headcount by department" had failed for 6 days; both affected flows now run (9 and 200 rows). The same fix covers derived-dataset rebuilds. A regression test reproduces it with a fresh session, as a real scheduler tick. |
| Refresh & jobs | **Fixed:** a dataflow with no outputs wrote "skipped" every hour (**411** identical rows), burying real failures. It's now recorded once per streak. (The old rows are still there; delete them if you want a clean history.) |
| Lineage page, column lineage, incremental, checks | Work (built yesterday, re-checked). Dataset "13" fails because its SQLite file is missing on this machine (environment, not code). |

## 2. Data scientist — explore, find drivers, build and trust models, use Python

| What I did | Result |
|---|---|
| Key influencers on price | Works, with good guidance (correlation ≠ causation, small groups, skipped id column). **Fixed:** bins read `(2014.999, 2019.0]`; they now read **2015 – 2019**, **146,999 – 90,000,000**. (That bin also exposes a 90,000,000 km outlier in the data.) |
| Trained a price model | **Bug fixed (serious): target leakage.** The model "predicted price_egp from … **price_egp (copy)**" and claimed R² **0.87**; the honest figure was **0.24**. Copies and straight-line rescalings of the outcome are now refused as inputs, and calculated columns built from the outcome (directly or through another calculated column) are left out. |
| | **Fixed:** `make` (104 brands), `model` and `governorate` were skipped as "too many values". The 19 commonest values are now kept and the rest grouped as "(other)", in training and scoring alike. Honest R² rose to **0.34**. |
| | **Fixed:** linear and logistic regression always "could not be fitted" on data with gaps (27% of mileage is empty). Gaps are now filled with the median inside those two models; linear regression is now the best model (**R² 0.37**). Fit errors now say why. |
| Use in Python | Good: one snippet, same security, audited. |

My two test models were deleted. The `price_egp (copy)` calculated column on "Cars 2015+
(setup test)" was already there and has been left alone.

## 3. Data analyst — answer questions, build and share dashboards, export

| What I did | Result |
|---|---|
| Ask AI: "Which region had the highest total revenue in 2025?" | The number was right (Europe 1,211,925.93, checked independently). **Fixed:** the answer was written in **Arabic** to an English question. The answer language is now decided from the question's own letters and stated to the model. |
| Export | PDF (377 KB, 2 s) and Excel generate correctly; the dialog is clear (formats, pages, preview, "as you see it, with your permissions"). |
| Dashboards, Insights | Work (dashboard building was tested in depth in the Fields-panel work). |

## 4. System administrator & data governance

| What I did | Result |
|---|---|
| Users, roles, settings | Pages work. The **Admin** section is folded at the bottom of a long sidebar and the user menu has no Settings link: easy to miss. |
| Row & column security, enforced? | **Yes.** As the EMEA analyst, revenue by region returned only Europe; `cost` is hidden everywhere and reported as "not a column", so its existence isn't revealed. |
| Audit trail | **Gap fixed (serious):** creating, changing or deleting **users and roles** was not audited at all, so granting org-admin rights left no trace. These are now recorded (role made org admin, user's role changed, password reset — never the password — deactivated, deleted, bulk import), with English and Arabic labels. |
| Dataset list | **Added:** a sensitivity-label filter (incl. *Unlabelled*) and a label chip. It immediately shows a governance finding: **36 of 49 datasets are unlabelled, none Confidential**, although "Current workforce" holds salaries. |
| Glossary | Works; no business terms defined yet on Cars DB. |

## Recommended next (not built)

1. Label the sensitive datasets (salaries first) and define glossary terms. This is data
   work, not code.
2. Users page: show last login and active/disabled status, to find stale accounts.
3. Put a "Settings" link in the user menu for admins.
4. Connection errors in plain words first ("The server name could not be found"), raw
   text behind "Show details", like the formula errors.
5. Ask AI results table: format big numbers (1,211,925.93), as the sentence does.
6. Key influencers: use the median as the baseline for skewed outcomes such as price.
7. Existing saved models trained with a leaked column keep their inflated score until
   retrained; retrain them.

## Checks

Backend: 1,269 tests over 85 files in the touched areas pass (new: scheduler fresh
session, skip-once, readable bins, model honesty ×7, answer language ×4, user/role
audit, list labels). Frontend: 342 files / 4,287 tests, type check, build. Architecture
document counts updated.
