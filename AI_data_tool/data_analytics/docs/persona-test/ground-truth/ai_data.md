# Profile: ai_data (PostgreSQL, connection "sh2on_zobat") - officer personnel & performance-evaluation data (Arabic text, military HR)
Note: data is personnel data; names (a_name, d_name, ai_outstanding.name = award name, not person) were not extracted here; only aggregates are reported.

## 1. Tables
| table | rows | declared key | grain |
|---|---|---|---|
| ai_officer | 190 | PK mil_no | one row per officer (current profile) |
| ai_officer_weigths | 190 | PK mil_no | one row per officer: height cm, weigth kg, inc |
| ai_srv | 1,166 | none | officer service/posting history (many per officer; all 190 officers have rows) |
| ai_outstanding | 278 | none | awards/commendations (136 officers, 6 award types) |
| ai_dicipline | 43 | none | disciplinary records (35 officers) |
| ai_eval_report | 1,311 | none | evaluation report header: one per officer per evaluation period, with appraiser/reviewer, grades, free-text notes |
| ai_eval_rep_items | 1,310 | none | the 20 criterion scores of the report (WIDE layout: s2_1..s2_10, s3_1..s3_10) |
| eval_rep_sub_item | 40 | PK no | criterion dictionary: (report_type, section_no, item_no) -> Arabic name |
| eval_rep_type | 2 | PK no | 1 = annual, 2 = annual command-level |

Joins: ai_officer.mil_no = ai_officer_weigths.mil_no (1:1); = ai_srv.mil_no / ai_outstanding.mil_no / ai_dicipline.mil_no / ai_eval_report.mil_no / ai_eval_rep_items.mil_no (1:many; 0 orphan rows in any of them; mil_no_flag is always 'S' - zero-variance). ai_eval_rep_items joins ai_eval_report on (mil_no, start_date, end_date) (1,308 match; 3 reports - all 2022-01-01..2022-06-30 with null report_type - have no items). Criterion column sS_I maps to eval_rep_sub_item where section_no=S, item_no=I, report_type=2 (all items rows are report_type 2). Sub-item `no` 1-20 are for report_type 2; 29-48 for type 1 (unused by data).
mil_no is a text 6-digit ID (all numeric-looking, length 6): an identifier, never sum/average it.

## 2. Grain, meaning and dates
- ai_officer: 190 officers, 16 rank_name values (Arabic; e.g. major 31, captain 29, lieutenant-colonel...; 29 naval ranks; 11 retired ('بالمعاش')). prom_date 2020-07-01 .. 2027-01-01 (17 promotion dates are in the future relative to 2026-10-12), srv_date 2022-02-21 .. 2026-07-01 (current assignment), berth_date (birth date) 1973-04-25 .. 2004-07-21 (ages 22-53 in Oct 2026). 89 distinct unit_name, 13 unit_root, 7 corp_name (arms/branches: artillery 51, infantry 38, naval 29, 25 'أ.ذ', armor 20, signals 15, air defence 12), 23 governorates, 51 cities.
- ai_srv: 1995-03-16 .. 2026-07-01, 1,166 rows (avg 6.1 per officer), 0 duplicates.
- ai_eval_report: periods 2022-01-01 .. 2025-12-31, half-year periods (dur_type 2: 1,307 rows + 3 with null report_type; dur_type 1 = full year, 1 row 2022). Report counts by year of start: 2022 306, 2023 319, 2024 328, 2025 358. 190 officers, avg 6.9 reports each. percent_a, percent_d: appraiser/reviewer percentage 65..97 / 65..99 (mean 85.02 / 85.05, correlation 0.997 -> near-duplicate columns). field1/filed2/filed3: 1..7 / 1..7 / 1..8 (codes). degree/degrea: all 'V' (zero variance). a_mil_no/d_mil_no: appraiser/reviewer IDs (221 / 227 distinct), none of them in ai_officer (1,311 of 1,311 not found) - external; a_name/d_name hold names.
- ai_eval_rep_items: periods 2021-01-01 .. 2025-12-31 (2 rows from 2021 H1/H2 with no header, 1 full-year 2022 row); half-year rows dominate; 20 scores per row, integer 3..7, no nulls. Score columns: s2_1..s2_10 range 3-6 (s2_5..s2_10 3-5); s3_1 ranges 4-7 (mean 5.22, a one-point higher scale than all others ~4.2), s3_2/s3_4/s3_6 3-6, others 3-5.
- ai_officer_weigths: height 165..192 (mean 178.8), weigth 60..115 (mean 83.7), inc 0..25 (meaning unclear); no nulls; 112 officers BMI>=25, 25 BMI>=30.

## 3. Measures and traps
- Wide layout: 20 criterion columns in ai_eval_rep_items (should be unpivoted to criterion, score and joined to eval_rep_sub_item). Report score = AVG of the 20 columns (overall mean 4.251, row min 3.25, max 4.85).
- One-to-many joins inflate officer counts: ai_officer JOIN ai_srv = 1,166 rows, JOIN ai_outstanding = 278 rows (190 officers only 136 have awards), ai_eval_report = 1,311. COUNT(*) after joining is not "officers"; use COUNT(DISTINCT mil_no).
- Nulls/blank: high_qual blank/null 151 of 190 (80%) - only 39 hold a higher degree (21 war college fellowship + 18 master's); base_qual_degree null 41; medical_name null 40; city null 43. No empty strings; real NULLs.
- Mixed granularity in attributes: rank_name includes 'retired' suffix and 'naval' variants as separate strings (16 distinct values for ~5 real ranks; retirement/navy are separate concepts embedded in the label).
- Future dates: 17 officers' prom_date after 2026-10-12 (scheduled promotions).
- Duplicates: none in ai_srv/ai_outstanding; 1 officer has the same dicipline type twice.
- Zero-variance columns: mil_no_flag, degree, degrea, a_mil_no_flag etc.
- Cardinalities: governorate 23, city 51, unit_name 89, rank_name 16, award types 6, dicip_type 2 (عقوبة 'penalty' 27, محاكمة 'trial' 16).
- Evaluation scale is bounded 3-7; grades are ordinal - means are fine but treat as ordinal. s3_1 has a shifted scale (see above) so item means are not strictly comparable.
- Outliers: none found in height/weight; very small group sizes (e.g. 4 officers aged 22) - do not draw conclusions on tiny cells.

## 4. Personas and true answers
### Persona A - HR clerk ("I only know the officers table")
A1. How many officers do we have and in which corps? 190 officers; artillery 51, infantry 38, naval 29, 'أ.ذ' 25, armor 20, signals 15, air defence 12. (`select corp_name,count(*) from ai_officer group by 1`). Naive after joining ai_srv: 1,166.
A2. Which governorate do most officers come from? Cairo 34, Giza 21, Sharqia 16, Alexandria 15, Qalyubia 13, Menoufia 11 (`group by governorate`); 23 governorates total; 43 officers have no city.
A3. How many have a higher qualification? 39 of 190 (20.5%): war college fellowship 21, military master's 18; 151 blank. Naive "% with high_qual" if NULLs treated as a category would show 79.5% 'blank' - the BI must say 'not recorded'.
### Persona B - commander reading the appraisal reports ("I just know grades are 3 to 7")
B1. What is the average overall score and which branch scores best? Overall mean of 20 criteria 4.251. By corp (`join ai_eval_rep_items i using(mil_no)`): naval 4.349 (29 officers, 204 reports), infantry 4.322, air defence 4.276, armor 4.237, 'أ.ذ' 4.218, signals 4.206, artillery 4.176 (355 reports, 51 officers). Differences are small (0.17).
B2. Which criterion is the weakest? Lowest means: s3_7 4.160 (report_type 2, section 3, item 7 = sub_item no 17, 'reliance on him for additional work'), s3_8 4.165, s2_7 4.172; highest s3_1 5.218 (but on shifted 4-7 scale). Map to names via eval_rep_sub_item (report_type 2, section 3, item 7).
B3. How many evaluation reports per year and did scores change? Header counts by start year: 2022 306, 2023 319, 2024 328, 2025 358 (total 1,311; 3 with no items); mean item score by period start year 2021 4.150 (2 rows only), 2022 4.253, 2023 4.253, 2024 4.244, 2025 4.255 -> flat. percent_a average 85.07 (2022), 85.06 (2023), 84.88 (2024), 85.09 (2025).
### Persona C - welfare officer ("I know about awards and discipline")
C1. How many officers hold awards? 136 of 190 (71.6%); 278 awards: duty medal class 1 99, class 2 69, class 3 34, thank-you letter 48, certificate of appreciation 24, distinguished service medal 4. Naive count of rows = 278 (not officers).
C2. How many officers have disciplinary records? 35 of 190 (18.4%) with 43 records (penalty 27, trial 16).
C3. Fitness: how many officers are overweight? BMI>=25: 112 (58.9%); BMI>=30: 25 (13.2%); mean height 178.8 cm, weight 83.7 kg. Medical: 'fit' 113, 'fit with restrictions' 37, blank 40.

## 5. What a good BI tool should tell this user automatically
- KPIs: headcount (distinct mil_no), officers by rank/corps/governorate, awards and discipline rates, average evaluation score and by period/corps/rank, report count per period.
- Charts: bar by corps/governorate/rank; line of mean score by half-year; heat map criterion x period; radar/bar of the 20 criteria; distribution of scores 3-7; scatter of percent_a vs percent_d (will show they are nearly identical).
- Warnings: wide score columns need unpivoting; one-to-many joins inflate counts - use distinct counts; 80% of high_qual and 22% of base_qual_degree/city/medical status are empty; mil_no is an ID (not a measure); zero-variance columns; percent_a and percent_d correlate 0.997; appraiser IDs do not exist in the officer table; 17 future promotion dates; s3_1 uses a shifted scale; Arabic labels - right-to-left display; personal-data sensitivity (names, IDs, health data) should be masked in shared dashboards.
