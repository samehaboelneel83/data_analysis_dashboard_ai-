// ── Expression builder data ───────────────────────────────────────────────────

export interface FuncItem { label: string; snippet: string; back: number; hint: string }
export interface FuncCat  { label: string; color: string; items: FuncItem[] }

export const FUNC_CATS: FuncCat[] = [
  {
    label: 'Numeric', color: '#60a5fa',
    items: [
      { label: 'abs(x)',       snippet: 'abs()',        back: 1, hint: 'Absolute value' },
      { label: 'round(x,n)',   snippet: 'round(, 2)',   back: 4, hint: 'Round to n decimals' },
      { label: 'sqrt(x)',      snippet: 'sqrt()',       back: 1, hint: 'Square root' },
      { label: 'floor(x)',     snippet: 'floor()',      back: 1, hint: 'Round down to integer' },
      { label: 'ceil(x)',      snippet: 'ceil()',       back: 1, hint: 'Round up to integer' },
      { label: 'log(x)',       snippet: 'log()',        back: 1, hint: 'Natural logarithm' },
      { label: 'exp(x)',       snippet: 'exp()',        back: 1, hint: 'e to the power x' },
      { label: 'pow(x,n)',     snippet: 'pow(, 2)',     back: 4, hint: 'x raised to power n' },
      { label: 'min(x,y)',     snippet: 'min(, )',      back: 3, hint: 'Minimum of two values' },
      { label: 'max(x,y)',     snippet: 'max(, )',      back: 3, hint: 'Maximum of two values' },
    ],
  },
  {
    label: 'Text', color: '#34d399',
    items: [
      { label: 'SENTIMENT(col)',        snippet: 'SENTIMENT()',        back: 1, hint: 'Tone of the text, -1 to 1 (English + Arabic); empty when no word is scored' },
      { label: 'SENTIMENT_LABEL(col)',  snippet: 'SENTIMENT_LABEL()',  back: 1, hint: 'positive / neutral / negative / unscored' },
      { label: 'UPPER(col)',            snippet: 'UPPER()',            back: 1, hint: 'Convert to uppercase' },
      { label: 'LOWER(col)',            snippet: 'LOWER()',            back: 1, hint: 'Convert to lowercase' },
      { label: 'TRIM(col)',             snippet: 'TRIM()',             back: 1, hint: 'Remove surrounding spaces' },
      { label: 'LEN(col)',              snippet: 'LEN()',              back: 1, hint: 'Number of characters' },
      { label: 'LEFT(col,n)',           snippet: 'LEFT(, 3)',          back: 4, hint: 'First n characters' },
      { label: 'RIGHT(col,n)',          snippet: 'RIGHT(, 3)',         back: 4, hint: 'Last n characters' },
      { label: 'SUBSTRING(col,at,len)', snippet: 'SUBSTRING(, 1, 3)',  back: 7, hint: 'Characters from position (1-based)' },
      { label: 'CONCAT(a,b)',           snippet: 'CONCAT(, )',         back: 3, hint: 'Join two values as text' },
      { label: 'REPLACE(col,a,b)',      snippet: 'REPLACE(, "", "")',  back: 8, hint: 'Replace every occurrence' },
      { label: 'FIND(col,"t")',         snippet: 'FIND(, "")',         back: 4, hint: 'Position of text, 0 if absent' },
      { label: 'CONTAINS(col,"t")',     snippet: 'CONTAINS(, "")',     back: 4, hint: 'True if the text appears' },
      { label: 'STARTSWITH(col,"t")',   snippet: 'STARTSWITH(, "")',   back: 4, hint: 'True if it begins with the text' },
      { label: 'ENDSWITH(col,"t")',     snippet: 'ENDSWITH(, "")',     back: 4, hint: 'True if it ends with the text' },
      { label: 'SPLIT(col,"-",n)',      snippet: 'SPLIT(, "-", 1)',    back: 8, hint: 'The nth part after splitting (1-based)' },
      { label: 'REVERSE(col)',          snippet: 'REVERSE()',          back: 1, hint: 'Reverse the characters' },
      { label: 'LPAD(col,w,"0")',       snippet: 'LPAD(, 5, "0")',     back: 8, hint: 'Pad on the left to width w' },
      { label: 'RPAD(col,w," ")',       snippet: 'RPAD(, 5, " ")',     back: 8, hint: 'Pad on the right to width w' },
      { label: 'to_text(x)',            snippet: 'str()',              back: 1, hint: 'Convert a value to text' },
    ],
  },
  {
    label: 'Date', color: '#f59e0b',
    items: [
      { label: 'year(col)',           snippet: 'YEAR()',              back: 1, hint: 'Extract year from date' },
      { label: 'quarter(col)',        snippet: 'QUARTER()',           back: 1, hint: 'Quarter number (1–4)' },
      { label: 'month(col)',          snippet: 'MONTH()',             back: 1, hint: 'Month number (1–12)' },
      { label: 'day(col)',            snippet: 'DAY()',               back: 1, hint: 'Day of month (1–31)' },
      { label: 'datetrunc(col,unit)', snippet: "DATETRUNC(, 'month')", back: 9, hint: 'Truncate to year / quarter / month / week / day' },
    ],
  },
  {
    label: 'Conditional', color: '#c084fc',
    items: [
      { label: 'IF(cond,yes,no)',           snippet: 'IF(, , )',           back: 5, hint: 'Return yes if condition true, else no' },
      { label: 'SWITCH(col,v1,r1,default)', snippet: 'SWITCH(, , , )',     back: 7, hint: 'Map values: col==v1→r1, else default' },
      { label: 'isnull(col)',               snippet: 'isnull()',           back: 1, hint: 'True if value is missing / null' },
    ],
  },
  {
    label: 'Aggregation', color: '#f472b6',
    items: [
      { label: 'SUM(col)',       snippet: 'SUM()',       back: 1, hint: 'Total sum of all values in column' },
      { label: 'AVG(col)',       snippet: 'AVG()',       back: 1, hint: 'Average (mean) of all values' },
      { label: 'MEDIAN(col)',    snippet: 'MEDIAN()',    back: 1, hint: 'Middle value (50th percentile)' },
      { label: 'COUNT(col)',     snippet: 'COUNT()',     back: 1, hint: 'Count of non-null values' },
      { label: 'COUNTD(col)',    snippet: 'COUNTD()',    back: 1, hint: 'Count of distinct (unique) values' },
      { label: 'STDEV(col)',     snippet: 'STDEV()',     back: 1, hint: 'Standard deviation' },
      { label: 'VARIANCE(col)',  snippet: 'VARIANCE()',  back: 1, hint: 'Statistical variance' },
      { label: 'PCT_TOTAL(col)', snippet: 'PCT_TOTAL()', back: 1, hint: '% share of column total (0–100)' },
      { label: 'NORMALIZE(col)', snippet: 'NORMALIZE()', back: 1, hint: 'Scale to 0–1 range (min-max)' },
      { label: 'ZSCORE(col)',    snippet: 'ZSCORE()',    back: 1, hint: 'Standard deviations from mean' },
    ],
  },
  {
    label: 'Running & Rank', color: '#fb923c',
    items: [
      { label: 'CUMSUM(col)',    snippet: 'CUMSUM()',    back: 1, hint: 'Running cumulative sum' },
      { label: 'CUMPCT(col)',    snippet: 'CUMPCT()',    back: 1, hint: 'Cumulative % of total' },
      { label: 'RANK(col)',      snippet: 'RANK()',      back: 1, hint: 'Rank each row (1 = smallest)' },
      { label: 'DIFF(col)',      snippet: 'DIFF()',      back: 1, hint: 'Difference from previous row' },
      { label: 'LAG(col, n)',    snippet: 'LAG(, 1)',    back: 4, hint: 'Value n rows back (default 1)' },
      { label: 'LEAD(col, n)',   snippet: 'LEAD(, 1)',   back: 4, hint: 'Value n rows ahead (default 1)' },
    ],
  },
  {
    label: 'Group By', color: '#2dd4bf',
    items: [
      { label: 'GROUPSUM(col,grp)',   snippet: 'GROUPSUM(, )',   back: 3, hint: 'Sum of col within each group value' },
      { label: 'GROUPAVG(col,grp)',   snippet: 'GROUPAVG(, )',   back: 3, hint: 'Average of col within each group' },
      { label: 'GROUPCOUNT(col,grp)', snippet: 'GROUPCOUNT(, )', back: 3, hint: 'Count within each group' },
      { label: 'GROUPRANK(col,grp)',  snippet: 'GROUPRANK(, )',  back: 3, hint: 'Rank within each group' },
      { label: 'GROUPMIN(col,grp)',   snippet: 'GROUPMIN(, )',   back: 3, hint: 'Minimum within each group' },
      { label: 'GROUPMAX(col,grp)',   snippet: 'GROUPMAX(, )',   back: 3, hint: 'Maximum within each group' },
      { label: 'GROUPPCT(col,grp)',   snippet: 'GROUPPCT(, )',   back: 3, hint: '% of group total' },
    ],
  },
  {
    label: 'Date parts',
    color: '#38bdf8',
    items: [
      { label: 'WEEKDAY(col)',   snippet: 'WEEKDAY()',   back: 1, hint: 'Day of week, 1 = Monday' },
      { label: 'WEEK(col)',      snippet: 'WEEK()',      back: 1, hint: 'ISO week number' },
      { label: 'DAYOFYEAR(col)', snippet: 'DAYOFYEAR()', back: 1, hint: 'Day of the year, 1-366' },
      { label: 'HOUR(col)',      snippet: 'HOUR()',      back: 1, hint: 'Hour, 0-23' },
      { label: 'MINUTE(col)',    snippet: 'MINUTE()',    back: 1, hint: 'Minute, 0-59' },
      { label: 'SECOND(col)',    snippet: 'SECOND()',    back: 1, hint: 'Second, 0-59' },
      { label: 'MONTHNAME(col)', snippet: 'MONTHNAME()', back: 1, hint: 'Month as a word' },
      { label: 'DAYNAME(col)',   snippet: 'DAYNAME()',   back: 1, hint: 'Weekday as a word' },
    ],
  },
  {
    label: 'Date maths',
    color: '#38bdf8',
    items: [
      { label: 'DATEADD(col,n,"month")',  snippet: 'DATEADD(, 1, "month")',  back: 15, hint: 'Shift by whole units; months follow the calendar' },
      { label: 'DATEDIFF(a,b,"day")',     snippet: 'DATEDIFF(, , "day")',    back: 10, hint: 'Whole units from a to b' },
      { label: 'DATEFROMYMD(y,m,d)',      snippet: 'DATEFROMYMD(, , )',      back: 5,  hint: 'Build a date from parts' },
      { label: 'TODAY()',                 snippet: 'TODAY()',                back: 0, hint: 'Today at midnight' },
      { label: 'NOW()',                   snippet: 'NOW()',                  back: 0, hint: 'Current date and time' },
      { label: 'TODATE(col)',             snippet: 'TODATE()',               back: 1, hint: 'Text or epoch days to a date' },
      { label: 'TONUMBER(col)',           snippet: 'TONUMBER()',             back: 1, hint: 'Date to epoch days' },
    ],
  },
  {
    label: 'Statistics',
    color: '#a78bfa',
    items: [
      { label: 'PERCENTILE(col,q)', snippet: 'PERCENTILE(, 50)', back: 5, hint: 'q is 0-100' },
      { label: 'MODE(col)',         snippet: 'MODE()',           back: 1, hint: 'Most common value' },
      { label: 'CORR(a,b)',         snippet: 'CORR(, )',         back: 3, hint: 'Correlation of two columns' },
      { label: 'COVAR(a,b)',        snippet: 'COVAR(, )',        back: 3, hint: 'Covariance of two columns' },
      { label: 'SKEW(col)',         snippet: 'SKEW()',           back: 1, hint: 'Distribution asymmetry' },
      { label: 'KURTOSIS(col)',     snippet: 'KURTOSIS()',       back: 1, hint: 'Tail heaviness' },
      { label: 'IQR(col)',          snippet: 'IQR()',            back: 1, hint: 'Interquartile range' },
      { label: 'SE(col)',           snippet: 'SE()',             back: 1, hint: 'Standard error of the mean' },
    ],
  },
]

export interface OpItem { label: string; snippet: string; back?: number }
export const OP_GROUPS: { label: string; items: OpItem[] }[] = [
  { label: 'Arithmetic', items: [
    { label: '+',  snippet: ' + '  },
    { label: '-',  snippet: ' - '  },
    { label: '*',  snippet: ' * '  },
    { label: '/',  snippet: ' / '  },
    { label: '**', snippet: ' ** ' },
    { label: '%',  snippet: ' % '  },
  ]},
  { label: 'Comparison', items: [
    { label: '==', snippet: ' == ' },
    { label: '!=', snippet: ' != ' },
    { label: '>',  snippet: ' > '  },
    { label: '<',  snippet: ' < '  },
    { label: '>=', snippet: ' >= ' },
    { label: '<=', snippet: ' <= ' },
  ]},
  { label: 'Logical', items: [
    { label: 'and', snippet: ' and ' },
    { label: 'or',  snippet: ' or '  },
    { label: 'not', snippet: ' not ' },
    { label: '(',   snippet: '('     },
    { label: ')',   snippet: ')'     },
  ]},
]

