# nyc_taxi profile (NYC yellow-taxi style trips, all numbers computed via read-only SQL)

## 1. Tables
| table | rows | PK | FKs |
|---|---|---|---|
| trips | 2,964,624 | trip_id (bigint) | vendor_id->vendors, rate_code_id->rate_codes, payment_type_id->payment_types, pickup_zone_id->zones, dropoff_zone_id->zones |
| zones | 265 | zone_id | - |
| vendors | 4 | vendor_id | - |
| payment_types | 7 | payment_type_id | - |
| rate_codes | 7 | rate_code_id | - |

trips columns: trip_id bigint, vendor_id int, pickup_at/dropoff_at timestamp, passenger_count int, trip_distance_miles double, rate_code_id int, store_and_fwd_flag text, pickup_zone_id int, dropoff_zone_id int, payment_type_id int, fare_amount, extra, mta_tax, tip_amount, tolls_amount, improvement_surcharge, total_amount, congestion_surcharge, airport_fee (all numeric).
zones(zone_id, borough, zone_name, service_zone); vendors(vendor_id, vendor_name); payment_types(payment_type_id, payment_type); rate_codes(rate_code_id, rate_code).
Joins: trips -> zones twice (pickup_zone_id, dropoff_zone_id), other lookups by their ids. All FKs satisfied.

## 2. Grain, meaning, ranges
- trips: one taxi trip (meter record). Intended period January 2024: pickup_at spans 2002-12-31 22:59 to 2024-02-01 00:01; dropoff_at to 2024-02-02 13:56. 2,964,606 pickups are in Jan 2024; 18 pickups are outside (2002-12: 2, 2009-01: 3, 2023-12: 10, 2024-02: 3) = junk timestamps. Busiest day 2024-01-27 (110,515), then 01-17 (110,365); quietest 2024-01-07 (67,543).
- zones: 265 TLC taxi zones (borough: Manhattan 69, Queens 69, Brooklyn 61, Bronx 43, Staten Island 20, EWR 1, "Unknown" 1 (id 264), blank 1 (id 265 "Outside of NYC")). Pickup uses 260 distinct zones, dropoff 261.
- vendors: 1 Creative Mobile Technologies (729,732 trips), 2 Curb Mobility (2,234,632), 6 Myle Technologies (260), 7 Helix (0 trips).
- payment_types: 0 Flex fare trip (140,162; 4.73%), 1 Credit card (2,319,046; 78.22%), 2 Cash (439,191; 14.81%), 3 No charge (19,597), 4 Dispute (46,628), 5 Unknown (0), 6 Voided (0).
- rate_codes: 1 Standard 2,663,350; 2 JFK 98,713; 3 Newark 7,954; 4 Nassau/Westchester 6,365; 5 Negotiated 19,410; 6 Group ride 7; 99 Unknown 28,663; plus 140,162 NULL.

## 3. Measures and traps
- Revenue = total_amount (fare+extra+mta+tip+tolls+surcharges). total_amount does NOT always equal the sum of its components: 761,838 rows differ (591,045 by -2.50, 129,332 by +2.50, 22,451 by -4.25, 18,149 by -1.75, ...; congestion surcharge handling), 2,202,786 match exactly. Do not recompute total from parts.
- Clean-trip predicate C = pickup in Jan 2024 AND fare_amount>0 AND total_amount>0 AND trip_distance_miles>0 AND dropoff_at>pickup_at AND duration<=6h -> 2,867,842 trips (96.7% of 2,964,624).
- Data-quality counts (all rows):
  - fare_amount<0: 37,448 (21,406 on Dispute, 8,208 cash, 5,740 No charge, 28 credit card: refunds/disputes); fare=0: 893; fare>500: 46; min -899.00, max 5,000.00.
  - total_amount<0: 35,504; =0: 416; min -900.00, max 5,000.00; 62 trips > 500 (sum 55,338.33).
  - tip_amount<0: 102; max 428.00. tolls<0: 2,035; extra<0: 17,548; mta_tax<0: 34,434.
  - trip_distance=0: 60,371 (56,569 of them with fare>0; 25,890 also same pickup/dropoff zone); 0<dist<0.1: 9,368; >50: 412; >100: 59; >200: 31; max 312,722.3 miles (impossible). 32 trips >100 mi with fare<200.
  - Duration: dropoff before pickup 56; zero duration 814; >5h 1,814; >6h 1,772; >24h 16. 29,010 paid trips shorter than 60 s. 964 trips imply >100 mph.
  - passenger_count NULL 140,162 (the same rows as Flex fare payment 0, which also have NULL rate_code, store_and_fwd_flag, congestion_surcharge, airport_fee); passenger_count=0 31,465; >=7 (7:8, 8:51, 9:1) 60. Distribution: 1=2,188,739; 2=405,103; 3=91,262; 4=51,974; 5=33,506; 6=22,353.
  - store_and_fwd_flag: N 2,813,126; Y 11,336; NULL 140,162.
  - Pickup or dropoff in zone 264/265 (Unknown / Outside NYC): 31,527 trips. Same pickup and dropoff zone: 160,766.
  - Duplicates: 0 (on vendor, times, zones, total).
- ID-like columns that look numeric: trip_id, vendor_id, rate_code_id (99 = Unknown), payment_type_id (0..6), pickup_zone_id, dropoff_zone_id; never sum/average. passenger_count is a genuine count.
- Tips: only recorded for card payments (cash tip avg 0.00). Tip % must use credit-card trips only.
- Cardinalities: vendors 3 used, payment types 5 used, rate codes 7 used, zones 260/261 used, boroughs 7 + blank.

Headline numbers (naive vs clean):
- Trips: 2,964,624 all rows; 2,964,606 in Jan 2024; 2,867,842 clean.
- Total revenue: naive SUM(total_amount) 79,456,384.28; positives only 80,349,763.32 (negatives sum -893,379.04); clean 78,421,992.54 (78,420,375.04 also dropping total>=1000).
- Avg total_amount: naive 26.80; clean 27.35. Avg fare: naive 18.18; clean 18.50.
- Avg distance: naive 3.652 mi; excluding 0 and >=100: 3.293 (equal for Jan-only clean); median 1.68 mi (naive mean is nearly double median; heavy skew). Total miles naive 10,827,308 vs 9,564,780 excluding >=100 mi.
- Avg duration: naive 15.61 min, clean (0< t <=6h) 14.85, median 11.63.
- Fare per mile (sum fare/sum miles): naive 4.977; clean 4.955.

## 4. Personas and true answers
### Persona 1: City-transport journalist/planner ("taxis in New York in January")
Q1. How many trips, and which day/hour is busiest?
```sql
select count(*), count(*) filter(where pickup_at>='2024-01-01' and pickup_at<'2024-02-01') from trips; -- 2,964,624 / 2,964,606
select pickup_at::date, count(*) from trips where pickup_at>='2024-01-01' and pickup_at<'2024-02-01' group by 1 order by 2 desc limit 3;
select extract(hour from pickup_at), count(*) from trips group by 1 order by 2 desc limit 3;
```
Busiest day Sat 2024-01-27 (110,515); hours: 18:00 (212,788), 17:00 (206,257), 16:00 (190,201); quietest hour 04:00 (16,742). Trips per calendar day by weekday (avg): Mon 81,655, Tue 92,732, Wed 99,006, Thu 107,147, Fri 102,147, Sat 105,290, Sun 84,826 (totals Mon 408,277, Tue 463,662, Wed 495,032, Thu 428,587, Fri 408,588, Sat 421,158, Sun 339,302, so compare per-day averages, not totals).
Q2. Which borough/zone do most trips start in?
```sql
select z.borough,count(*) from trips t join zones z on z.zone_id=t.pickup_zone_id group by 1 order by 2 desc;
```
Manhattan 2,646,948 (89.28%), Queens 273,128 (9.21%), Brooklyn 25,258 (0.85%), Unknown 10,360, Bronx 6,905, blank (Outside NYC) 1,658, EWR 295, Staten Island 72. Top pickup zones: JFK Airport 145,240, Midtown Center 143,471, Upper East Side South 142,708, Upper East Side North 136,465, Midtown East 106,717. Top dropoff: Upper East Side North 142,044, Upper East Side South 130,249, Midtown Center 111,942.
Q3. How long/far is a typical trip?
Median 1.68 mi and 11.6 min; mean 3.29 mi (clean) / 3.652 (naive, distorted by 312,722-mile record) and 14.85 min (clean) / 15.61 naive. 60,371 zero-distance trips and 56 negative-duration trips are junk.

### Persona 2: Taxi driver / fleet manager ("I drive a cab")
Q1. What is the typical tip?
```sql
select round(100*sum(tip_amount)/sum(fare_amount),2) from trips where payment_type_id=1 and <C>;
```
Credit-card clean: 22.62% of fare (average of per-trip ratios 26.28%; avg tip 4.156); naive card tip% 22.47%; all payments clean 18.40% (cash tips are not recorded, so a tool averaging all payments understates tipping). Naive avg tip across all rows 3.336; cash avg 0.00.
Q2. What is the payment mix? Credit card 78.22%, Cash 14.81%, Flex fare 4.73%, Dispute 1.57%, No charge 0.66%. Revenue by payment type: card 65,533,599.31; cash 10,050,669.22; flex 3,617,824.63; no-charge 171,581.04; dispute 82,710.08 (naive).
Q3. Where are the most lucrative pickups, and is airport work worth it?
Clean pickups with >=1000 trips, highest avg total: JFK Airport 80.89 (138,314 trips), LaGuardia 66.37 (87,658), East Elmhurst 64.36, Long Island City 43.92, Sunnyside 35.00. Highest pickup revenue: JFK 11,187,615.13, LaGuardia 5,817,950.03, Midtown Center 3,355,399.20, Upper East Side South 2,770,786.77, Times Sq/Theatre District 2,763,458.61. Rate code JFK = 3.28% of clean trips (94,041) but trips touching JFK zone = 161,956 (zone, not rate code, is the better filter). Fare per mile 4.955 clean. Avg fare by rate code (naive): Standard 15.37, JFK 67.09, Newark 79.28, Nassau/Westchester 100.98.

### Persona 3: Finance analyst ("revenue of the taxi fleet")
Q1. Total revenue for the month?
```sql
select sum(total_amount) from trips; -- naive 79,456,384.28
select sum(total_amount) from trips where <C>; -- clean 78,421,992.54
```
Naive 79.46M includes -893,379.04 of negative (refund/dispute) amounts and out-of-period rows; clean (positive complete trips in Jan 2024) 78.42M; positives only 80.35M. Outliers: 62 trips with total>500 sum 55,338.33 (0.07%); max 5,000.
Q2. Revenue by vendor?
Naive: Vendor 2 Curb Mobility 60,602,721.27 (2,234,632 trips), Vendor 1 Creative Mobile 18,841,261.98 (729,732), Vendor 6 Myle 12,401.03 (260). Clean: 60,444,491.07 / 17,966,887.57 / 10,613.90. Avg clean total per trip 27.83 / 25.83 / 51.03. Vendor 7 Helix has no trips (lookup only). Cleaning removes 4.6% of vendor 1 revenue vs 0.3% of vendor 2 (cause not investigated).
Q3. Weekday vs weekend, and best day?
Clean: weekday 2,134,490 trips, avg total 27.77, revenue 59,268,396; weekend 733,352 trips, avg 26.12, revenue 19,153,596. Highest-revenue days: 2024-01-25 (2,970,490), 2024-01-17 (2,928,392). Average passengers per trip 1.354 (excluding 0: 1.354; including 0: 1.339).

## 5. What a good BI tool should tell this user automatically
- KPIs: trips 2.96M (2.87M clean), revenue ~78.4M clean, avg total 27.35, avg fare 18.50, avg distance 3.29 mi (median 1.68), avg duration ~15 min, tip% 22.6% on cards, payment mix, avg passengers 1.35.
- Charts: trips by hour x weekday heatmap (evening 16-19h peak), daily trips line (range 67.5k-110.5k), top pickup/dropoff zones, borough share (Manhattan 89%), revenue by payment type/vendor, distance histogram (log scale, truncated at ~30 mi).
- Warnings it must raise: pickup_at outside Jan 2024 (18 rows; 2002, 2009 timestamps); 56 negative durations and 1,772 trips >6h; 60,371 zero-distance trips; distances up to 312,722 miles (31 >200); 37,448 negative fares and 35,504 negative totals (refunds/disputes); 31,465 passenger_count=0 and 140,162 NULLs (which coincide with Flex-fare trips with NULL rate code/flags/surcharges); total_amount does not reconcile to components in 761,838 rows; tips exist only for card trips (cash 0 tips); vendor_id/rate_code_id/payment_type_id/zone ids are codes not numbers; unknown/outside zones 264/265 (31,527 trips); Helix vendor has no data; heavy skew means medians over means.
