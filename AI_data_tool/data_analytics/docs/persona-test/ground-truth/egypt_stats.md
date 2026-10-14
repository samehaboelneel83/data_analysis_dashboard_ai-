# Profile: egypt_stats (PostgreSQL, connection "food"; despite the name it is an Egypt humanitarian/development open-data collection)

## 1. Tables (14, no declared PK/FK)
| table | rows | grain / layout |
|---|---|---|
| conflict_events | 1,071 | month x event_type (national, admin_level 0) |
| humanitarian_funding | 44 | appeal x year |
| national_risk | 1 | single row (INFORM risk 2025) |
| population_by_governorate | 81 | governorate x gender (year 2012 only) |
| poverty_rate | 51 | governorate x year (2008, 2014) |
| rainfall_by_governorate | 46,740 | governorate/district x 10-day period x aggregation_period (long, triplicated) |
| refugees_in_egypt | 46,540 | year x origin country x population_group x gender x age_range |
| returnees | 26 | same layout as refugees (2012-2015, 10 people total) |
| undp_human_development | 1,118 | year x indicator (long / EAV) |
| wfp_food_prices | 3,658 | month x market x commodity (retail prices) |
| wfp_markets | 68 | market dimension |
| who_health_indicators | 32,846 | indicator x year x dimension (long / EAV, mixed units) |
| worldbank_indicator_info | 1,498 | indicator dimension (code -> name, description, source, topic) |
| worldbank_indicators | 46,861 | year x indicator (long) |

Joins (evident): wfp_food_prices.market_id = wfp_markets.market_id (only 2 of 68 markets are used: 226 "National Average", 10254 "Cairo (national average)"); worldbank_indicators.indicator_code = worldbank_indicator_info.indicator_code (all 1,370 used codes present; 1,498 in info); population/poverty/rainfall share admin1_code (EG01 Cairo ... EG35 South Sinai; 27 governorates); conflict/funding/risk/refugees only join by `year`. Governorate names differ by table (provider_admin1_name 'Asyout' vs admin1_name 'Assiut'; WFP markets use 'Qalyubia'/'Sohag' vs 'Kalyoubia'/'Suhag') - join on code, not on name. wfp_markets/wfp_food_prices governorate is a different spelling set.

## 2. Date ranges / meaning
- conflict_events: 1997-01-01 .. 2026-09-30 (monthly rows; 357 months x 3 event types: political_violence, demonstration, civilian_targeting).
- humanitarian_funding: year 2001..2029 (years 2026-2029 are future-dated pledged funding); appeal_code null on 26 rows.
- national_risk: 2025, risk_class 3, global_rank 68, overall_risk 4.3.
- population_by_governorate: 2012 only; 27 governorates x {m,f,all}; age_range always 'all'.
- poverty_rate: 2008 (24 governorates) and 2014 (27); mpi 0.0007..0.0828, headcount_ratio 0.2071..18.9975 (percent).
- rainfall_by_governorate: 2022-01-01 .. 2026-09-20 (reference_period dekads of 8-11 days); version final 44,694 / preliminary 2,046.
- refugees_in_egypt: 2001..2025; returnees 2012..2015.
- undp_human_development: 1990..2023 (indices HDI, GDI, GII, IHDI (2010+), PHDI; 7 distinct index_id values, 50 indicator ids; 150 rows are is_index=true).
- wfp_food_prices: 2010-08-15 .. 2026-08-15, monthly (15th), 17 calendar years, 40 commodity names, 7 categories, 6 units.
- who_health_indicators: start_year 1955 .. end_year 2030 (19 rows start after 2025 = projections); 485 indicators, 42 dimension types.
- worldbank_indicators: 1960..2025; 1,370 indicators, 34 topics.

## 3. Measures and traps (counts computed)
General: no stated measure is additive across indicators in the three EAV tables (who, worldbank, undp): each indicator has its own unit. Always filter to ONE indicator_code before aggregating or charting.
- **population_by_governorate** - totals mixed with detail: gender 'all' row = m + f. SUM(population) = 162,791,082 (double counts) vs correct 81,395,541 (gender='all'; Egypt 2012). Per governorate Cairo all = 8,762,503. 27 governorates, 0 nulls.
- **refugees_in_egypt** - each (year, origin, population_group) has 13 rows: gender x age cells plus subtotals (all/all, m/all, f/all). Naive SUM(population) 2025 = 3,471,403; correct total = gender='all' AND age_range='all' = 1,175,943 (2.95x overcount; the sum of the 10 m/f x age cells is 1,146,042, small cells are rounded/suppressed so cells don't tie out exactly). Also 780 (year,origin,group,gender,age) keys have duplicate rows (e.g. 14 rows for origin EGY/ASY in 2001) - origin_location_code 'EGY' appears as an origin (77,642 in 2025) which is suspicious. 30,836 rows have population = 0 (66%). 3 population groups: REF refugees, ASY asylum seekers, OOC others in refugee-like situation. age_range has 'all' and 5 bands; max_age null for '60+' and 'all'.
- **rainfall** - `aggregation_period` repeats each location/dekad in 3 rows: 'dekad', '1-month', '3-month' (rolling accumulations: 2024 national sums 1,099 / 3,755 / 12,805 mm-units). Summing all three periods gives 17,659 vs 1,099 for dekad only (16x) in 2024 at admin level 1. Also admin_level 1 (4,590 x 3 rows) and admin_level 2 (10,990 x 3) mix governorate and district rows (admin2_name null for 13,770 rows = admin1 rows). Correct annual rain per governorate: admin_level=1, aggregation_period='dekad', SUM(rainfall) by year. Leaks: 2026 is partial (to Sep 20), 2,046 preliminary rows, 14,970 rows have rainfall_long_term_average = 0 (anomaly pct not meaningful) with 20 of them rainfall>0. Rainfall 0..192.5; anomaly pct 53.6..372.0 (never negative, so it is "percent of average").
- **conflict_events**: fatalities null on all 357 'demonstration' rows (357 nulls = 33%): not zero, not recorded. events 0..319, fatalities 0..745. Total events 13,273; fatalities 16,131 (excl. demonstrations). 90 (year,event_type) keys repeat because monthly. Years 2011 and 2013-2015 are peak.
- **humanitarian_funding**: requirements_usd null on 27 of 44 rows (older years and the three future years), appeal_code/name null on 26; funding_pct null where requirements null. Per-year rows contain an un-coded "other" funding row (e.g. 2024: 43,571,168 USD with no appeal, no requirement). funding_pct stored as 0-100. Years 2026-2029 hold forward-dated funding (53.5m, 11.3m, 2.3m, 0.19m USD).
- **wfp_food_prices**: only 2 markets and they DUPLICATE each other: 'National Average' (id 226) 2010-08..2022-10 and 'Cairo (national average)' (id 10254) 2021-01..2026-08; the overlap 2021-01..2022-10 has the same commodity/date twice (99 date+commodity+price duplicate groups; 30 pairs differ in price, 129 pairs total). governorate/district/lat/long null on 2,580 rows (the national-average market). Units are mixed: KG 2,945, 800 G 380, 8 pcs 147, Unit 116, 1 piece 67, L 3 - egg prices are per piece, cheese per 8 pieces, oil per 800 g; commodity names differ by era ('Eggs' vs 'Eggs (medium size)', 'Onions' vs 'Onions (red)'), so a continuous series for "eggs" needs both. price_egp 0.66..302.50 (no nulls, no zeros); price_usd 0.064..11.67. priceflag all 'actual', pricetype all 'Retail' (zero-variance columns). market_id/commodity_id are numeric-looking identifiers.
- **who_health_indicators**: EAV with 485 indicators; value is double, value_text holds "value [low-high]" strings (18,106 rows non-numeric text); value null 2,557; low/high null 17,318; dimension_type blank on 2,309 rows; range -0.93 .. 81,000,000,000 (1 negative, 2 above 1e9); 2,131 (indicator, years, dimension_type, dimension_code) keys repeat, so additional discriminating fields exist/are missing; 27 rows span multiple years (start<>end); 19 rows start after 2025 (projections). Top 7 indicators are life-table columns (nMx, nLx, lx, ex ..., 1,254 rows each).
- **worldbank_indicators**: 46,861 rows, 1,370 indicators, 34 topics; negative values 1,771 (legitimate for balances/growth); value range -2.12e12 .. 2.03e13 - mixes USD, %, counts. No (year, indicator) duplicates. 2025 only 428 rows (partial), 2023 877.
- **undp_human_development**: indicators with 1 observation only (MPI components, 2014; rank rows 2023). Gender-split series (hdi_f, hdi_m, le_f, ...) present as separate indicator_ids; is_index flags 150 index rows. Never AVG(value) across indicators.
- worldbank_indicator_info: description null count 0.

## 4. Personas and true answers
### Persona A - journalist ("how big is Egypt and how are prices moving?")
A1. What was Egypt's 2012 population? `select sum(population) from population_by_governorate where gender='all'` = 81,395,541. Naive `select sum(population)` = 162,791,082 (2.0x). Largest governorate: Cairo 8,762,503 (gender='all').
A2. Inflation in 2023? `select value from worldbank_indicators where indicator_code='FP.CPI.TOTL.ZG' and year=2023` = 33.88 (%); 2022 13.90, 2024 28.27, 2025 14.07, 2021 5.21.
A3. How much did sugar cost in 2021 vs 2025? Average of wfp_food_prices (KG) price_egp: 2021 = 13.49 EGP/kg, 2025 = 41.90 (3.1x). Naive vs de-duplicated: 2022 naive 13.92 vs one-market-only 14.26 (double-counted months bias the average). Rice 9.27 -> 29.22; Tomatoes 5.28 -> 10.64; Eggs (medium size) 1.64 -> 5.38 per piece.
### Persona B - humanitarian programme officer ("I know refugees came from Sudan")
B1. How many refugees/asylum seekers were in Egypt in 2025? Correct = 1,175,943 (gender='all' and age_range='all'); naive sum of all rows = 3,471,403. By group (all/all): ASY 924,560; REF 243,796; OOC 7,587. Top origin: SDN 834,201, then SYR 117,364, EGY 77,642 (odd), SSD 53,332, ERI 44,461.
B2. How did the number change since 2022? 2022 all/all = 410,894; 2025 = 1,175,943 (+186%); 2023 542,529; 2024 956,944.
B3. How well funded was the 2024 appeal? Two coded appeals: requirements 183,142,076 + 76,092,112 = 259,234,188 USD; funded 66,096,038 + 54,163,569 = 120,259,607 -> 46.4%. Naive SUM(funding_usd)/SUM(requirements) for year 2024 = 163,830,775/259,234,188 = 63.2% because it includes a 43,571,168 USD row with no appeal. Per appeal funding_pct: Sudan RRP 36, Syria 3RP 71.
### Persona C - agriculture / development analyst
C1. Which governorate got the most rain in 2024? Correct (admin_level=1, dekad): North Sinai 126.2 (units as stored, mm), Alexandria 115.2, Suez 103.3. Naive (admin_level=1 but all 3 aggregation periods summed): Alexandria 1,861.6, North Sinai 1,756.9 - different ranking and about 14x inflated.
C2. Which governorate was poorest in 2014? Highest MPI: Matrouh 0.0415 (headcount 10.95%), Suhag 0.0382, Fayoum 0.0370. In 2008 the highest was Fayoum (0.083, headcount 19.0%), Assiut 0.079; only 24 governorates in 2008 vs 27 in 2014 - comparisons across years need the common set.
C3. What is Egypt's HDI trend and life expectancy? HDI 0.572 (1990), 0.639 (2000), 0.677 (2010), 0.754 (2023); life expectancy (UNDP) 62.51 -> 71.63 yrs. WHO life expectancy at birth both sexes: 69.15 (2000), 71.59 (2019), 69.11 (2021). Conflict: 2013 = 2,559 events / 2,070 fatalities (political violence 822, demonstration 1,521, civilian targeting 216); 2023 = 219 events / 47 fatalities.

## 5. What a good BI tool should tell this user automatically
- Detect that tables are separate subject areas (no shared key except year/admin1_code); build per-table dashboards instead of forcing joins.
- Warn: gender/age 'all' rows are subtotals (population, refugees) - SUM overcounts 2x and 2.95x; aggregation_period triples rainfall rows; admin_level mixes province/district; 'National Average' and 'Cairo (national average)' overlap in 2021-2022; EAV tables (WHO, World Bank, UNDP) need an indicator picker, and measures have different units; fatalities null for demonstrations; 2026+ rows are partial/future; WFP units differ per commodity.
- Auto KPIs: total population by governorate (2012), refugee total over time (line), funding vs requirements % per year, conflict events by year (stacked by type), rainfall by dekad/month with anomaly, food price index lines (sugar, rice, oil) EGP and USD, HDI trend, inflation.
- Best charts: line (time series: prices, refugees, inflation), bar (governorate population/MPI), map-like governorate ranking, stacked area for conflict types, dual line requirements vs funding.
