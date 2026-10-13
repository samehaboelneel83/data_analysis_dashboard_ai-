# Profile: cars (Egyptian scraped listings: used/new cars + property for sale) — numbers computed read-only

## 1. Tables, keys, joins
No declared PK/FK anywhere. The four tables are INDEPENDENT scrapes from different sites; they do not join to each other (no shared key; only loose location text). Prices are already numeric (double precision) - not text - but are in EGP only (all "price_egp"); no currency column.
| Table | Rows | Natural key | Notes |
|---|---|---|---|
| cars_hatla2ee | 14,269 | listing_id (bigint, unique, 14,269 distinct; item_url also unique) | 28 columns; has Arabic duplicate columns (color_ar, transmission_ar, fuel_type_ar, body_type_ar, condition_ar, imported_ar, taxi_ar) |
| realestate_aqarmap | 8,994 | url (unique) | 16 cols, Arabic labels, lat/long |
| realestate_olx | 15,311 | none (no id/url) | 15 cols |
| realestate_propertyfinder | 19,924 | url (unique) | 18 cols incl. long free-text description |
Real-estate tables share concepts (price_egp, area_sqm, price_per_sqm_egp) and could be UNIONed with a source label, but with different dates, taxonomies and location granularity (see traps).

## 2. Grain, meaning, date ranges
- cars_hatla2ee: one row per car-for-sale listing. listed_date 2025-04-29..2026-06-18 (listed_at timestamptz; listed_at::date differs from listed_date in 1,039 rows = timezone shift). Volume is heavily back-loaded: 2026-03 609, 2026-04 2,720, 2026-05 3,926, 2026-06 6,950 (to 18 Jun); before 2026-03 only 64 rows total -> not a time series. model_year 1953..2027; mileage in km; condition New 2,570 / Used 11,699.
- realestate_aqarmap: one row per for-sale listing (8,153 'for-sale' URLs; the other 841 are 'projects-...' developer project pages). No date column at all. Region (21 values; Greater Cairo 6,487, Red Sea 1,752, Alexandria 339, North Coast 221, blank 65). source_file aqarmap_data1/2/3 = scrape batches (1,173 / 1,649 / 6,172).
- realestate_olx: one row per ad. ad_date 2020-03-21..2023-04-21 (null for 2,728), scraped_on 2023-03-13..2023-04-23. Data is 2023 - prices ~3x lower than the 2025/26 sources.
- realestate_propertyfinder: one row per for-sale listing (all 19,924 URLs are /buy/). available_from 2023-06-14..**2027-10-31** (null 663; future dates = off-plan delivery, not an error). Governorates: Cairo 7,610, North Coast 5,246, Giza 4,276, Red Sea 1,598, Suez 601...

## 3. Key measures and traps
Measures: listing count; **median** price (never mean - skewed); median price_per_sqm_egp (= price/area, verified matches price_egp/area_sqm in all rows with both); median price by make/model/year/age; share by categorical.

### cars_hatla2ee
- price_egp (clean) vs price_egp_raw: raw has absurd values (111,111,000,000; 380,000,000; 1,111,111,111; 2,222,222,222; 99,999,999; 1,000 x5; 6,666; 0 x1; 5,000). 15 rows have price_egp NULL where raw was junk (8 raw < 10,000, 6 raw >= 100,000,000, 1 raw = 0). Mean raw 17,371,342 vs clean mean 1,524,149; medians identical 790,000. **Naive mean on raw price is 11x too high.** Always use price_egp.
- Remaining outliers inside price_egp: min 28,000 (Fiat 127 1983), max 53,000,000 (Rolls Royce Cullinan new - plausible); but Hyundai Matrix 2005 at 50,500,500 with 0 km is clearly a typo that survived cleaning. Percentiles p1 70,000 / p50 790,000 / p99 10.12M. Mean by condition: New 3,195,630 vs median 2,165,000; Used mean 1,156,841 vs median 660,000.
- mileage_km: NULL for all 2,570 New cars (structural). 809 Used cars have mileage 0 (897 used under 100 km) = placeholder/unknown, not real; 29 rows >= 1,000,000 km incl. 123,456,789 and other fake values (2 rows in {123456789,111111,1111111}); p50 124,000, p95 320,000.
- model_year: 203 rows have model_year 2027 (age -1) and 1,957 are 2026; car_age_years = 2026 - model_year (min -1, max 73); 75 cars older than 1980. Negative age 203 rows. Condition 'Used' with model_year 2026/2027: 239 + 5.
- title empty (NULL) in 9,307 of 14,269 rows (65%); imported NULL 10,353 (72.6%; Yes 985, No 2,931); taxi NULL 9,816 (Yes 75, No 4,378); transmission NULL 2; fuel_type NULL 2; body_type NULL 125.
- Cardinality: 118 makes (Mercedes 1,519, Hyundai 1,078, Kia 928, Renault 714, Nissan 676, Chevrolet 673, BMW 667...), 950 models, 1,045 make-model pairs, 170 colors (free text like "Other (نحاسي)"; top Black 3,212, White 1,900, Silver 1,883, Gray 1,714; "Dark grey" vs "Gray" overlap), 209 cities, 37 governorates (Cairo 8,078, Giza 2,610, Alexandria 915).
- Inconsistent labels: governorate has "Beni Suef" (47) AND "Ben Suef" (21), "El Faiyum", "Asyut", plus non-governorates "Greater Cairo ( Cairo + Giza)" (16), "Sharm el-Sheikh" (15), "Mariotya" (6). city has "Tagamo3 - New Cairo"-style names.
- fuel_type "Gas" = petrol (fuel_type_ar بنزين), distinct from "Natural Gas" (CNG) - misleading English label. Gas 11,428 (80.1%), Diesel 1,390, Natural Gas 717, Electric 436, Hybrid 271, Plug-in Hybrid 25.
- Duplicates: listing_id unique; 4 groups of identical (make,model,year,mileage,price,city) tuples - negligible. Only 4 rows have price<100,000 with model_year>=2022 (suspicious tiny prices).
- Age vs price (used, median): not monotonic at the young end (age 1: 1.62M, age 2: 2.25M, age 3: 2.0M, age 4: 1.0M) because of model mix (luxury makes) - warn on "depreciation per year" claims.

### realestate_aqarmap
- price_egp: 0 null, min 370,000, max 95,000,000, p1 1.25M / median 6.1M / p99 30.9M. area_sqm: 63 NULL, min 5 (1 row <10, 2 <20), max 1,650, median 144. price_per_sqm_egp NULL 63 (= area null), median 46,667, p99 165,725, max 655,172 (2 rows > 500k/sqm = tiny areas).
- rooms: 624 NULL; outliers 13, 22, 33, 67 (one each = typos); baths NULL 1,137, 22 x2. floor is TEXT mixed numeric and Arabic ("الارضي" = ground, 798) ; 1,294 blank; floor_number 3 rows > 40 (max 234); 1,294 NULL.
- finishing_ar blank 1,292; categories سوبر لوكس 2,873, نصف تشطيب 2,010, اكسترا سوبر لوكس 1,859, بدون تشطيب 792, لوكس 168.
- lat/long NULL 466; none outside Egypt bounds. region_ar/area_name_ar Arabic only (1,157 distinct area names).
- 911 groups of identical (price, area, rooms, baths, area_name) -> likely repeated/duplicate ads under different URLs (group count, not row count).
- 841 URLs are 'projects-...' pages (developer projects, not individual units) mixed in.
- No listing date -> cannot trend.

### realestate_olx
- 2,728 rows have property_type 'Unknown' and are EMPTY (price, area, bedrooms, ad_date, level all null) - junk rows (18% of table). price_egp NULL 2,733, area NULL 2,739, price_per_sqm NULL 2,744. Property types: Apartment 10,985, Unknown 2,728, Duplex 910, Penthouse 478, Studio 210.
- price min 30,000 (18 rows < 100,000), max 50,000,000; median 2,317,352; price_per_sqm median 13,942 (p1 1,651). Prices are 2023 EGP.
- bedrooms/bathrooms NULL 2,729; level mixed text ('Ground','Highest','10+', numbers); furnished blank 6,416; payment_option blank 3,807; delivery_date mixed text/years/'Ready to move'/'soon' (6,093 blank) - a text column mixing years and words; delivery_term blank 5,042; compound NULL 8,952; city blank 2,737 (273 distinct otherwise; New Cairo - El Tagamoa 4,601).
- 177 groups of fully identical ads (type, price, area, beds, baths, city, compound, dates, level).

### realestate_propertyfinder
- price_egp NULL 539 (mostly Land 'price on request' etc.), min 186,900, max 840,000,000 (20 rows >= 300M; 913 >= 50M; 188 villas >= 100M); median 10,345,550.
- area_sqm: NULL 77, min 1, max 15,811,692 (5 rows >= 10,000 sqm; one 'apartment' with area 15,811,692 and price/sqm 1 = unit error; other: chalet 96,106 sqm). price_per_sqm min 1, max 19,500,000; price_per_sqm_egp > 1,000,000 in 3 rows; area<20 or pps>2,000,000 in 2 rows.
- 814 groups of identical (type, price, area, beds, baths, location) = probable repeated listings.
- property_type blank in 77 rows; 18 types (Apartment 8,355, Chalet 4,038, Villa 3,570, Townhouse 1,335, Twin House 834, Duplex 622, Penthouse 569, iVilla 268, Hotel Apartment 104, Land 63, Palace 23...). Mixing Land / Palace / Whole Building with apartments distorts averages: mean apartment price 8,123,080 vs median 6,750,000.
- payment_method: Cash 15,521, Installments 3,862, blank 541; down_payment_egp NULL 14,479 (only 5,445 filled; 2,769 of them are Installments); down_payment never > price. Description text can contradict the column (example: text says down payment 21,130,000 on a 25M villa; column 2,100,000).
- bedrooms NULL 472; is_studio true 328 (bedrooms then null/0); bathrooms NULL 145; compound NULL 6,663; district NULL 600; governorate blank 91, typos "South Sainai", "Al Daqahlya".
- available_from up to 2027-10-31; 98 rows before 2025-01-01.

### Cross-source traps
- Price/sqm medians (apartments, EGP): Aqarmap 46,667 (n=8,931); PropertyFinder 46,875 (n=8,280); OLX 13,714 (n=10,971) -> OLX is 2023 and not comparable to 2025/26 sources (e.g. 3-bed New Cairo apartment median: OLX 2,383,800 n=2,507 vs PropertyFinder 8,500,000 n=1,880).
- Location taxonomies differ (Aqarmap region, OLX city with 'New Cairo - El Tagamoa', PF governorate/city/district/compound), Arabic vs English. No common key.
- Never SUM prices (meaningless) and never average price_per_sqm of different property types together.

## 4. Personas and true answers

### Persona A - someone wanting to buy a used car (cars_hatla2ee)
A1. How much is a used 2015-2018 Toyota Corolla?
`SELECT count(*), percentile_cont(.5) WITHIN GROUP (ORDER BY price_egp), round(avg(price_egp)), min(price_egp), max(price_egp) FROM cars_hatla2ee WHERE make='Toyota' AND model='Corolla' AND condition='Used' AND model_year BETWEEN 2015 AND 2018`
Result: 29 listings, median 850,000, mean 872,483, range 750,000..1,250,000. (Toyota Corolla total 252 listings; model also appears as 'Corolla Cross' 1, 'GR Corolla' 3 - a text LIKE '%corolla%' returns 253/256 and mixes them.)
A2. Cheapest used automatic SUV under 1,000,000 EGP with under 100,000 km?
`... WHERE condition='Used' AND transmission='Automatic' AND body_type='SUV' AND price_egp<=1000000 AND mileage_km<100000`
Naive (mileage 0 included): 349 listings, cheapest 220,000. Clean (mileage_km>0 to drop placeholder zeros): 303 listings, cheapest 250,000, median 850,000. 
A3. What is the typical price of a used car by age? (depreciation)
`SELECT car_age_years, count(*), percentile_cont(.5) WITHIN GROUP (ORDER BY price_egp) FROM cars_hatla2ee WHERE condition='Used' AND car_age_years BETWEEN 0 AND 15 GROUP BY 1 ORDER BY 1`
Medians: age0 1,350,000 (239); 1: 1,620,000; 2: 2,250,000; 3: 2,000,000; 4: 1,000,000; 5: 1,000,050; 6: 960,000; 7: 880,000; 8: 799,999; 9: 730,000; 10: 640,000; 11: 570,000; 12: 550,000; 13: 535,000; 14: 550,000; 15: 450,000 (n 340). Non-monotonic early (mix of luxury models) - needs make-level control.

### Persona B - a private seller / dealer pricing a car
B1. What is a 2018 Hyundai Elantra (used) worth?
`SELECT count(*), percentile_cont(.5) WITHIN GROUP (ORDER BY price_egp), round(avg(price_egp)) FROM cars_hatla2ee WHERE make='Hyundai' AND model='Elantra' AND model_year=2018 AND condition='Used'` -> only 3 listings, median 800,000, mean 893,333 (too few to be reliable - tool should say so). Elantra overall: 133 listings (most common Hyundai model).
B2. Does colour matter? (used, aged 3-8, colours with >=100 listings, median price)
Black 1,400,000 (n=774), White 1,260,000 (572), Gray 1,200,000 (457), Dark blue 960,000 (300), Silver 880,000 (437), Red 817,500 (297), Blue 795,000 (150), Dark grey 950,000 (145), Dark red 715,000 (140). Confounded by make/model mix (not causal).
B3. Where are the most listings and what are the median prices? 
`SELECT governorate, count(*), percentile_cont(.5) WITHIN GROUP (ORDER BY price_egp) FROM cars_hatla2ee WHERE condition='Used' GROUP BY 1 ORDER BY 2 DESC` -> Cairo 6,043 (median 745,000), Giza 2,268 (650,000), Alexandria 831 (590,000). Beware "Beni Suef"/"Ben Suef" split.

### Persona C - a market analyst / investor on the cars market
C1. What is the average car price and which makes dominate?
Clean mean 1,524,149 / median 790,000. Naive mean on price_egp_raw = 17,371,342 (wrong by 11x). By make (n, mean, median): Mercedes 1,519, 3,864,290, 3,350,000; Hyundai 1,078, 875,953, 650,000; Kia 928, 1,060,878, 795,000; Renault 714, 551,545, 490,000; Nissan 676, 984,468, 675,000.
C2. Fuel mix and import share?
Gas (petrol) 80.09%, Diesel 9.74%, Natural Gas 5.02%, Electric 3.06% (436), Hybrid 1.90% (271), Plug-in Hybrid 0.18%. imported: Yes 985 (6.9%), No 2,931 (20.5%), unknown 10,353 (72.6%). Taxi: Yes 75 (only 6 are New cars).
C3. New vs used price level?
New 2,570 listings: mean 3,195,630, median 2,165,000; Used 11,699: mean 1,156,841, median 660,000 (New cars have no mileage).

### Persona D - a home buyer / property investor (real estate)
D1. What does a 3-bedroom apartment in New Cairo cost?
PF: `SELECT count(*), percentile_cont(.5) WITHIN GROUP (ORDER BY price_egp) FROM realestate_propertyfinder WHERE property_type='Apartment' AND bedrooms=3 AND city='New Cairo City'` -> 1,880 listings, median 8,500,000 EGP. OLX (2023, city='New Cairo - El Tagamoa', 3 beds, Apartment): n=2,507, median 2,383,800 (mean 2,992,231; median area 170 sqm). Same question, 3.6x different because of 2-3 years of price inflation and different site.
D2. Typical price per sqm by property type / area (apartments)?
Median EGP/sqm: Aqarmap 46,667 (all types); PropertyFinder apartments 46,875 (mean 53,930); OLX apartments 13,714 (mean 16,924). PF by governorate (apartments, n>200): North Coast 67,890 (262), Red Sea 62,000 (579), Cairo 49,988 (4,744), Giza 37,680 (2,337), Alexandria 35,143 (354). Aqarmap by region: North Coast 71,750, Alexandria 50,000, Red Sea 49,074, Greater Cairo 44,118. Aqarmap Greater Cairo by finishing: extra super lux 53,333; none-stated 52,500; lux 48,074; no finishing 41,153; half finishing 37,403; super lux 36,957.
D3. How many properties are sold on instalments, and what down payment is typical? (PF)
Installments 3,862, Cash 15,521, blank 541 -> 19.9% instalments among known. Down payment only given for 5,445 rows (2,769 for Installments): average down-payment ratio of price 14.5%, median 10% (n=2,769).
Also: PF villas 3,570 (3,389 with price), 188 villas listed >=100,000,000 EGP; PF Palace median 199,000,000.

## 5. What a good BI tool should tell this user automatically
- Recognise 4 unrelated tables (2 domains: cars vs property; 3 property sources); do not auto-join; offer a UNION only with a source column and a warning about different dates/currencies/taxonomy.
- KPIs: listing counts; median (not mean) price; median price/sqm; price by make/year/age/mileage band; share New vs Used, fuel, transmission, imported; property median price/sqm by region and type; instalment share.
- Charts: price distribution histogram (log scale), median price by age, top makes (bar), listings by governorate (bar/map), mileage vs price scatter (cut zeros), property price/sqm by region and type (box plot), listings over time (flagging that 2026-03..06 holds 97% of car rows; OLX is 2023; Aqarmap undated).
- Warnings it must raise: price_egp_raw junk (17,371,342 mean; 6 values >=100M, 8 under 10k) - use cleaned column, and 15 null prices; 809 used cars with 0 km and 29 mileage >= 1,000,000; 203 cars with model_year 2027 (negative age) and 75 older than 1980; 65% of car titles empty, 72.6% imported unknown; duplicate/near-duplicate labels (Ben Suef/Beni Suef, 170 colour strings, Arabic twin columns); mixed-type text columns (aqarmap floor, olx level, olx delivery_date); 2,728 empty OLX rows (type 'Unknown'); PF area outliers (15.8M sqm, price/sqm 1) and 20 prices >= 300M; PF/OLX area/price nulls (539 / 2,733 / 2,739); mean >> median skew; sources not comparable in time; 841 Aqarmap 'projects' pages mixed with units; low-sample warnings (e.g. 2018 Elantra n=3).
