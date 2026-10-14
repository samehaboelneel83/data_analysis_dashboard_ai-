# Profile: egx (PostgreSQL, Egyptian Exchange prices)

## 1. Tables
| table | rows | grain |
|---|---|---|
| stock_prices | 635,898 | one row per (ticker, trade_date) - daily OHLCV |
| egx30_index | 6,827 | one row per trade_date for the EGX 30 index (but 144 dates are duplicated, see traps) |

No primary/foreign keys declared. Join: `stock_prices.trade_date = egx30_index.trade_date` (only for ticker 'EGX 30'; the same index also lives inside stock_prices). No natural join to anything else.

stock_prices columns: ticker text, trade_date date, close/open/high/low double, volume bigint, change_pct double (percent, e.g. 10.64 = +10.64%), year int (redundant = year of trade_date, 0 mismatches), traded_value_egp double (= close*volume exactly, 0 mismatches where not null).
egx30_index columns: trade_date date, open/high/low/close double, volume bigint, change_pct double.

## 2. Grain, meaning, date ranges
- stock_prices: 262 distinct tickers; 2000-01-02 .. 2023-12-12; 6,044 distinct dates. Rows by year: 3,249 (2000, 19 tickers) -> 23,463 (2010, 136) -> 51,100 (2023, 255). Big jump in 2010 = coverage expands (19-29 tickers 2000-2009; 136+ from 2010), so "number of rows/tickers over time" is a coverage artifact, not market growth.
- **Mixed entity types in one column**: 5 of the 262 "tickers" are INDICES, not stocks: 'EGX 30' (5,846 rows), 'EGX 100' (3,482), 'EGX 30 Capped' (3,096), 'EGX 70 EWI' (1,688), 'EGX 100 EWI' (1,306) = 15,418 rows. Real stocks: 257 tickers, 620,480 rows.
- Trading days: weekday distribution is Sun 122,587 / Mon 129,018 / Tue 128,157 / Wed 132,428 / Thu 123,547 (Egyptian week) + 160 Friday rows + 1 Saturday row (odd dates).
- egx30_index: 1998-01-01 .. 2026-04-02 (6,666 distinct dates, 6,827 rows). Extends 2.3 years PAST stock_prices (570 rows dated after 2023-12-12), and starts 2 years before it.
- Ticker history length: median stock short; 10 tickers have <250 rows, 1 has <30 rows; the longest (COMI 5,817 rows) 2000-01-12 .. 2023-12-11. 7 tickers have last date before 2023-01-01 (delisted/stale).

## 3. Measures and traps (all counts computed)
Right way to compute:
- Returns: use close-to-close change (last close / first close - 1) per ticker over the period; or compound change_pct. NEVER sum or average close prices across tickers (prices are not additive; e.g. SUM(close) 2023 = 12,457,660.7, AVG(close) = 243.79 - both meaningless; the median close over all rows is 5.85 and max 30,847.75, index levels included).
- Volume: SUM(volume) per ticker per period is valid (shares), but don't sum across tickers and then call it "market volume" without excluding index rows. traded_value_egp is additive across stocks (EGP traded) once indices are excluded.
- Market turnover = SUM(traded_value_egp) WHERE ticker NOT LIKE 'EGX %'.
Data-quality issues:
- Index tickers mixed with stocks: 15,418 rows. Naive 2023 traded value for ALL rows = 2,959.3 bn EGP; stocks only = 2,088.3 bn (index "volumes" are just index-constituent volume, double counting).
- Null volume/traded_value: 8,528 rows (126 tickers affected; e.g. CTSB all 1,326 rows, EGX 30 2,220 rows, EGX 100 1,420). 3,531 are real stocks. traded_value null iff volume null.
- volume = 0: 1,852 rows (all stocks, no index rows) - "suspended/no-trade" days. One volume = -10 (1 row, impossible). 
- close = 0: 462 rows (all real stocks) - impossible price (and the following day's return is infinite/garbage). Min close is 0.
- Outlier volume: max volume 505,890,000,000 on 'EGX 100 EWI' 2020-09-17 -> traded_value 1.43e15 EGP; 4,613 rows have traded_value > 1e12 EGP (mostly index rows, since index "close" x volume).
- change_pct outliers: 1,438 rows with |change_pct|>20 (898 >50, 162 >100); max 83,591 (TAQA 2023-07-09), 33,785.71 (EBSC 2012-03-07), 17,575.5 (EDBM 2010-05-13), min -100. Egyptian daily limit is ~10-20%, so these are splits, rights issues, price rebases or bad ticks; 1,339 such rows are in stocks from 2010 on. change_pct disagrees with close/prev_close-1 by >0.5pt in 1,353 rows; 813 consecutive-row jumps >40%.
- Price anomalies example: AGIN 2000-03-12 close 1.5 -> 127.61 then 1.5 next day (bad tick).
- OHLC inconsistencies: high<low: 7 rows in stocks; close outside [low,high]: 58,183 rows (9.1%); open outside [low,high]: 1,536 rows. So high/low can't be trusted to bracket close.
- Gaps: 919 consecutive rows with >30 calendar-day gap per ticker, 246 with >90 days (stocks that stop trading then resume).
- Duplicates: stock_prices has 0 duplicate (ticker,trade_date). egx30_index has 144 duplicated dates (161 extra rows), e.g. 2020-09-17 appears twice with same OHLC but change_pct -0.336 vs 0; only 3 of those are full-row duplicates. The egx30_index first row (1998-01-01) has null change_pct (1 null). 2,683 index rows have volume 0.
- Splits: no split-adjustment column; prices are NOT adjusted for splits (see change_pct outliers). Long-run return of a single stock from raw close can be wrong by orders of magnitude (TAQA 2023 "first->last close" = +2,664% on 124 rows; SMPP +1,100% on 61 rows).
- Year column duplicates trade_date info (not a numeric measure; don't sum). Ticker is a text code (4 letters) - categorical cardinality 262; year 24 values.
- Same indices differ slightly between tables: EGX 30 on 2023-12-12 = 24,094.87 (egx30_index) vs 24,082.45 (stock_prices).

## 4. Personas and true answers
### Persona A - retail investor ("I know COMI is a bank")
A1. Which stock had the most money traded in 2023?
```sql
select ticker, round(sum(traded_value_egp)/1e9,2) bn from stock_prices where year=2023 and ticker not like 'EGX %' group by 1 order by 2 desc nulls last limit 3;
```
Clean: COMI 74.55 bn EGP, BTFH 43.55, HRHO 27.49. Naive (indices not excluded; NULLs sort first in DESC unless NULLS LAST): top "tickers" are 'EGX 30 Capped' 1,044.7 bn and 'EGX 30' 871.0 bn.
A2. How much did COMI go up in 2023?
```sql
-- first/last close in 2023 (2023-01-02 .. 2023-12-11, 228 days)
```
42.75 -> 76.89 = +79.9%. (Data stops 2023-12-11 for COMI.)
A3. What was the average share price in 2023? Naive AVG(close) over all rows = 243.79 (meaningless: mixes 251 stocks + 4 indices at thousands of points). Right answer: there is no single "average price"; per stock, e.g. COMI 2023 average close can be computed. Clean count of distinct stocks trading in 2023 = 251 (255 incl. indices).
### Persona B - market analyst ("I follow the EGX 30 index")
B1. EGX 30 index return in 2023 (egx30_index): last close of 2022 (2022-12-29) 14,598.53, last close of 2023 (2023-12-27) 24,351.12 -> +66.8%.
B2. Largest one-day fall and worst drawdown ever: change_pct min -18.505 on 2011-03-23 (close 5,142.71); max +20.165 on 2003-02-02. Max drawdown from running peak: -71.6% at 2009-02-08 (close 3,389.31 vs peak 11,935.67).
B3. How many trading days in 2023? egx30_index has 204 rows for 2023 (2023-01-02 .. 2023-12-27); stock_prices has 229 distinct dates in 2023 (includes dates up to 2023-12-12 and Friday rows). Also index table has 570 rows after 2023-12-12 that stock_prices does not (to 2026-04-02), so "latest date" differs by table.
### Persona C - exchange operations / data steward
C1. How many listed companies do we have data for? 257 stock tickers (262 incl. 5 indices); 251 traded in 2023; 7 tickers have no rows after 2022.
C2. How much trading activity per year? Stock turnover (EGP bn): 2019 569.1, 2020 2,204.1, 2021 974.3, 2022 797.0, 2023 2,088.3 (naive incl. indices: 997.9, 2,654.0, 1,347.8, 1,094.1, 2,959.3).
C3. How many bad records? 462 zero closes, 1,852 zero-volume days, 8,528 null volumes, 1,438 |change|>20% rows, 144 duplicated index dates.

## 5. What a good BI tool should tell this user automatically
- KPIs: last close and period return per ticker, turnover (EGP) per year, active tickers per year, index level and drawdown.
- Charts: candlestick/line for one ticker or index; line of EGX 30 close over time (log scale optional); bar of turnover by year; top-N tickers by traded value; histogram of daily change_pct.
- Warnings: (1) `ticker` mixes indices (EGX *) and stocks - recommend a filter; (2) close prices are not additive - never SUM/AVG close across tickers; (3) 462 rows with close = 0 and 8,528 nulls in volume/traded_value; (4) extreme change_pct (|>20%|, up to 83,591%) suggest unadjusted splits; (5) 1 negative volume, 7 rows high<low; (6) duplicated dates in egx30_index; (7) coverage jump in 2010 (19 -> 136 tickers) makes counts non-comparable across years; (8) year is an integer-looking dimension, trade_date is the true time axis; (9) the two tables end at different dates.
