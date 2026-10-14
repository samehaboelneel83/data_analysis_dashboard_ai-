# Profile: nile_express (courier / parcel delivery company, Egypt) — all numbers computed read-only

## 1. Tables, keys, joins
| Table | Rows | PK | FKs |
|---|---|---|---|
| shipments | 64,420 (**64,000 distinct shipment_id**) | none declared (shipment_id NOT unique) | customer_id->customers, origin_branch_id->branches, driver_id->drivers |
| customers | 1,800 | customer_id | - |
| drivers | 147 | driver_id | branch_id->branches |
| branches | 19 | branch_id | - |
| complaints | 2,343 | complaint_id | customer_id->customers, branch_id->branches; **shipment_id has no declared FK** but all 2,343 match shipments |
| app_sessions_log | 3,000 | id | none; unrelated noise table (session_token, user_agent always "Mozilla/5.0"; 3,000 distinct tokens; 2024-01-01..2026-09-29) |

Join paths: shipments.customer_id=customers; shipments.origin_branch_id=branches; shipments.driver_id=drivers (drivers.branch_id=branches); complaints.shipment_id=shipments.shipment_id (join to the DEDUPED shipments, else fan-out); complaints.branch_id=branches. app_sessions_log joins to nothing.
Note: branch is "origin branch", not destination. 19 branches, 2 in Cairo, 2 Giza, 2 Alexandria, 1 per other of 13 governorates.
Verified: no orphan FKs (0 null customer/driver/branch in shipments). complaints.customer_id matches the shipment's customer in 2,343/2,343 rows.

## 2. Grain, meaning, date ranges
- shipments: one row per parcel (shipment_id/tracking_no "NX<id>EG"). created_at 2024-01-01..2026-09-30; promised_date 2024-01-02..2026-10-09; delivered_at 2024-01-01..2026-10-07 (only for Delivered/Returned); updated_at = delivered_at when set. Years (deduped): 2024 18,140; 2025 24,823; 2026 21,037 (2026 is partial, to 30 Sep).
- customers: one per account (joined_on 2021-01-01..2025-08-28). Segments: E-commerce seller 976, Business 540, Individual 284.
- drivers: hired_on 2019-01-05..2025-07-06; vehicle Motorcycle 89, Van 46, Truck 12.
- branches: opened_on 2018-09-01..2023-10-01; monthly_rent_egp 22,515..85,910 (a cost table).
- complaints: opened_at 2024-01-04..2026-10-05; resolved_at 2024-01-05..2026-10-09 (null for the 228 Open).
- Status mix (deduped 64,000): Delivered 56,050 (87.58%), Returned 7,154 (11.18%), In transit 517 (0.81%, all created 2026-09-25..30), Lost 279 (0.44%).

## 3. Measures and traps
Right way to compute:
- Shipment count / revenue: `WITH s AS (SELECT DISTINCT * FROM shipments)` first. Revenue = SUM(delivery_fee_egp) (EGP; currency column is 'EGP' for all rows). Recognise revenue for status='Delivered' (and arguably Returned); exclude negative fees.
- On-time / late %: use status='Delivered' only (is_late NULL for In transit/Lost).
- Return rate = Returned / all non-In-transit shipments (or all rows); lost rate similar.
- COD cash = SUM(cod_amount_egp) where payment_method='Cash on delivery' (cod_amount = declared_value for every COD row; 0 otherwise).
- Avg delivery time = AVG(delivery_days) on Delivered only (days = delivered_at - created_at, verified except 55 bad rows).

Data-quality issues (counts actually found):
1. **Duplicate rows**: 420 shipment_ids appear twice (840 rows), exact full-row duplicates (SELECT DISTINCT gives 64,000). Inflates counts by 420 (0.65%) and fees: naive total fee 11,195,626.14 vs deduped 11,109,352.72. 2 complaints belong to a duplicated shipment (complaints dist shipment_id 2,342 of 2,343 - one shipment has 2 complaints).
2. **declared_value is TEXT** (all 64,420 parse as numeric, no non-numeric strings found, 0 nulls). Range 11..23,449, median 543; 39 rows > 10,000. Must CAST to numeric; BI tools may treat it as a category.
3. **Padded/whitespace categories**: destination_governorate has 904 rows with leading/trailing spaces -> 64 distinct raw values vs 16 real governorates (naive "top governorates" chart and per-gov rates split). Fix with TRIM. (destination_region clean; 4 regions.)
4. **Negative values**: weight_kg < 0 in 1,309 rows (all = -1.00; 1,300 after dedup); delivery_fee_egp < 0 in 38 rows (min -902.44; sum -4,529.97). Max weight 60 (5 rows >= 50, plausible-ish outlier); fees > 1,000: 1,012 rows (International service, avg fee 929) - legit, not errors. Fee p50 102.83, p95 858.
5. **Impossible time order**: delivered_at < created_at in 55 rows (49 Delivered, 6 Returned); delivery_days still positive (mismatch with timestamps).
6. **is_late inconsistent with dates**: 2,205 rows is_late=false but delivered_at::date > promised_date; 16 rows is_late=true though delivered on/before promise. Use is_late consistently or define late from dates; the two give different answers.
7. **Nulls by design**: customer_rating NULL 30,777 (all non-Delivered plus ~40% of Delivered; only Delivered rows rated: 33,643 raw / 33,428 deduped); return_reason blank 57,217 (only Returned have it); is_late NULL 802; internal_note: 63,129 blank, 1,291 'checked by supervisor' (useless column). customers.account_manager blank for 284 (exactly the Individual segment). Blank strings are '' not NULL for return_reason/internal_note.
8. **Temporal impossibilities in dimensions**: 4,015 shipments (deduped) are dated before the customer's joined_on; 3,215 shipments before the driver's hired_on; 5 complaints opened before shipment created_at. Synthetic-data artefacts; do not trust customer-tenure analysis.
9. **Concentration**: customer 1362 ("Gamal Store") = 16.84% of shipments (9,328 delivered).
10. **ID lookalikes**: shipment_id (bigint 500001..564000), customer_id, driver_id, branch_id, complaint_id are numeric IDs - must not be summed/averaged. drivers.national_id is a 14-char TEXT PII (all 14 long); customers.phone (11-digit text, all match 01xxxxxxxxx), email, customer_name are PII; customer_name has only 330 distinct values for 1,800 customers (names are not unique).
11. customers.name distincts, drivers: 111 distinct names for 147 drivers.
12. complaints: Late delivery 1,517 (64.7%), Damaged parcel 252, Lost parcel 225, Overcharged 134, Rude courier 116, Wrong item delivered 99. compensation_egp > 0 only for Damaged/Lost (435 rows, total 201,406.33). resolution_hours blank for the 228 Open; median 23.6h; Lost parcel avg 124.2h. Complaints count (2,343) is NOT linked to is_late counts.

Cardinalities: service_type 4 (Standard 33,507 / Express 17,427 / Same Day 8,283 / International 5,203 raw), parcel_category 8 (~8,000 each, uniform), payment_method 4 (COD 40,832 raw; Company account, Prepaid card, Prepaid wallet ~7.8-7.9k), delivery_attempts 1..5 (1: 44,550), customer_rating 1..5, governorates 16 true, regions 4.

## 4. Personas and true answers
CTE used everywhere: `WITH s AS (SELECT DISTINCT * FROM shipments)`.

### Persona A - Operations manager ("is my service reliable?")
A1. What % of delivered shipments were late?
SQL: `WITH s AS (SELECT DISTINCT * FROM shipments) SELECT count(*), sum(is_late::int), round(100.0*avg(is_late::int),2) FROM s WHERE status='Delivered'`
Clean: 56,050 delivered, 9,917 late = **17.69%**. Naive (with dups): 56,415 / 9,976 = 17.68% (little change). (Do not average is_late over all statuses: Returned rows also carry is_late, 1,293 true.)
A2. Which service type is latest / slowest?
SQL: `... SELECT service_type, count(*), round(100.0*avg(is_late::int),2) late_pct, round(avg(delivery_days),2) FROM s WHERE status='Delivered' GROUP BY 1`
Result: Same Day 31.39% late (avg 1.54 d); International 23.34% (7.99 d); Express 17.21% (2.28 d); Standard 13.69% (3.69 d).
A3. Which governorate has the highest return rate? (trap: padded names)
SQL: `... SELECT trim(destination_governorate), count(*), round(100.0*avg((status='Returned')::int),2) FROM s GROUP BY 1 ORDER BY 3 DESC`
Clean (16 groups): Suez 13.07% (227/1,737), Aswan 12.98%, Fayoum 12.04%, Ismailia 11.86%, Port Said 11.83%; lowest Sharqia 10.32%, Dakahlia 10.35%. Naive without TRIM splits into 64 groups (the Cairo returns, for example, are spread over several spellings that differ only by spaces).
Bonus: worst on-time origin branch (Delivered): Minya Central Hub 27.07% (447), Aswan 26.36%, Assiut 24.61%; best Dakahlia 12.07%.

### Persona B - Finance / sales lead ("how much do we earn and who pays?")
B1. Delivery-fee revenue per year.
SQL: `... SELECT extract(year from created_at), count(*), round(sum(delivery_fee_egp)) FROM s GROUP BY 1` 
Clean all statuses: 2024 3,097,100; 2025 4,369,885; 2026 3,642,368 (to 30 Sep); total 11,109,352.72. Naive (dups): 3,113,606 / 4,407,428 / 3,674,592 = 11,195,626.14 (+86k). Delivered + positive fee only: 2024 2,729,189; 2025 3,828,699; 2026 3,152,372.
B2. Total COD cash to collect/remit from Delivered parcels?
SQL: `... SELECT status, round(sum(cod_amount_egp)) FROM s GROUP BY 1`
Clean Delivered: 27,767,792 EGP (33,927 COD parcels); Returned 5,105,574 (never collected); In transit 258,054; Lost 145,370. Naive Delivered (dups): 27,994,937.
B3. Top customers by delivered fee revenue, and revenue by segment.
SQL: `... SELECT c.customer_id,c.customer_name,count(*),round(sum(delivery_fee_egp)) FROM s JOIN customers c USING(customer_id) WHERE status='Delivered' AND delivery_fee_egp>0 GROUP BY 1,2 ORDER BY 4 DESC LIMIT 5`
Result: 1362 Gamal Store 1,625,150 (9,328); 266 Nabil Fashion 460,772; 331 Gamal Online 283,183; 241 Nabil Trading 264,839; 1781 Abdallah Boutique 235,287. Segments: E-commerce 7,596,323 (43,873 parcels), Business 1,929,084 (11,050), Individual 184,853 (1,093). Revenue by service: International 4,168,051 (4,490 parcels), Standard 2,365,343, Express 1,851,856, Same Day 1,325,009 - International is 8.0% of delivered parcels (4,490 of 56,050) but 42.9% of delivered fee revenue.

### Persona C - Customer-care head ("are customers happy, what goes wrong?")
C1. Average customer rating, and does lateness hurt it?
SQL: `... SELECT round(avg(customer_rating),3), count(customer_rating) FROM s` -> **4.058** (33,428 rated). Late: 2.901 vs on-time 4.310. By service: Same Day 3.871, International 3.980, Express 4.060, Standard 4.115. (Rating exists only for Delivered; a rating of NULL must not be counted as 0.)
C2. Complaint volume, open backlog, and cost.
SQL: `SELECT status,count(*),round(avg(resolution_hours),1),round(sum(compensation_egp)) FROM complaints GROUP BY 1`
Result: Resolved 2,115 (avg 37.0 h; median 23.6 h), Open 228 (no resolution time); total compensation 201,406.33 EGP over 435 complaints (all Damaged/Lost). Top type: Late delivery 1,517 (64.7%).
C3. What share of parcels are lost and what happens to those customers?
SQL: `... SELECT count(*) FILTER (WHERE status='Lost'), round(100.0*count(*) FILTER (WHERE status='Lost')/count(*),2) FROM s` -> 279 lost of 64,000 = **0.44%** (156 distinct customers); naive raw 280. Lost parcels have no delivered_at or rating.

## 5. What a good BI tool should tell this user automatically
KPIs: shipments (deduped 64,000), delivered %, return % (11.18%), lost % (0.44%), on-time % (82.31% of delivered), avg delivery days, total fee revenue, COD collected, avg rating (4.06), open complaints (228), compensation paid.
Charts: monthly shipments + revenue line (2024-01..2026-09, flag 2026-09 partial & In-transit-only tail); status donut; late % by service type (bar); return % by governorate/region (bar or map, trimmed names); late % by origin branch; rating by late/on-time; complaints by type + resolution time; revenue concentration (customer 1362 = 16.84% of shipments) Pareto.
Warnings it must raise: (1) 420 exact duplicate shipment_ids (840 rows) - dedupe; (2) declared_value stored as text - convert to number; (3) destination_governorate has 904 padded values making 64 distinct values for 16 - trim; (4) 1,309 negative weights (-1.00) and 38 negative delivery fees - treat as errors; (5) 55 shipments delivered before created; (6) is_late disagrees with dates in 2,221 rows; (7) shipment_id/customer_id/etc are identifiers, not measures; (8) national_id/phone/email are personal data; (9) app_sessions_log is unrelated and complaints.shipment_id has no declared FK; (10) internal_note and currency (constant 'EGP') carry no information; (11) rating/return_reason/delivered_at nulls are structural, not missing data; (12) 4,015 shipments pre-date customer joined_on (don't use tenure analysis).
