// ── Expression builder data ───────────────────────────────────────────────────

import type { TranslateFn } from '../../../i18n'

export interface FuncItem { label: string; snippet: string; back: number; hint: string }
export interface FuncCat  { label: string; color: string; items: FuncItem[] }

/** The palette, in the reader's language. Signatures (`label`) and `snippet`
 *  are code and stay as typed; only category names and hints are translated. */
export const funcCats = (t: TranslateFn): FuncCat[] => [
  {
    label: t('pg.panelsA.calc.cat.numeric'), color: '#60a5fa',
    items: [
      { label: 'abs(x)',       snippet: 'abs()',        back: 1, hint: t('pg.panelsA.calc.hint.abs') }, // i18n-ok
      { label: 'round(x,n)',   snippet: 'round(, 2)',   back: 4, hint: t('pg.panelsA.calc.hint.round') }, // i18n-ok
      { label: 'sqrt(x)',      snippet: 'sqrt()',       back: 1, hint: t('pg.panelsA.calc.hint.sqrt') }, // i18n-ok
      { label: 'floor(x)',     snippet: 'floor()',      back: 1, hint: t('pg.panelsA.calc.hint.floor') }, // i18n-ok
      { label: 'ceil(x)',      snippet: 'ceil()',       back: 1, hint: t('pg.panelsA.calc.hint.ceil') }, // i18n-ok
      { label: 'log(x)',       snippet: 'log()',        back: 1, hint: t('pg.panelsA.calc.hint.log') }, // i18n-ok
      { label: 'exp(x)',       snippet: 'exp()',        back: 1, hint: t('pg.panelsA.calc.hint.exp') }, // i18n-ok
      { label: 'pow(x,n)',     snippet: 'pow(, 2)',     back: 4, hint: t('pg.panelsA.calc.hint.pow') }, // i18n-ok
      { label: 'min(x,y)',     snippet: 'min(, )',      back: 3, hint: t('pg.panelsA.calc.hint.min') }, // i18n-ok
      { label: 'max(x,y)',     snippet: 'max(, )',      back: 3, hint: t('pg.panelsA.calc.hint.max') }, // i18n-ok
    ],
  },
  {
    label: t('pg.panelsA.calc.cat.text'), color: '#34d399',
    items: [
      { label: 'SENTIMENT(col)',        snippet: 'SENTIMENT()',        back: 1, hint: t('pg.panelsA.calc.hint.sentiment') }, // i18n-ok
      { label: 'SENTIMENT_LABEL(col)',  snippet: 'SENTIMENT_LABEL()',  back: 1, hint: t('pg.panelsA.calc.hint.sentiment_label') }, // i18n-ok
      { label: 'UPPER(col)',            snippet: 'UPPER()',            back: 1, hint: t('pg.panelsA.calc.hint.upper') }, // i18n-ok
      { label: 'LOWER(col)',            snippet: 'LOWER()',            back: 1, hint: t('pg.panelsA.calc.hint.lower') }, // i18n-ok
      { label: 'TRIM(col)',             snippet: 'TRIM()',             back: 1, hint: t('pg.panelsA.calc.hint.trim') }, // i18n-ok
      { label: 'LEN(col)',              snippet: 'LEN()',              back: 1, hint: t('pg.panelsA.calc.hint.len') }, // i18n-ok
      { label: 'LEFT(col,n)',           snippet: 'LEFT(, 3)',          back: 4, hint: t('pg.panelsA.calc.hint.left') }, // i18n-ok
      { label: 'RIGHT(col,n)',          snippet: 'RIGHT(, 3)',         back: 4, hint: t('pg.panelsA.calc.hint.right') }, // i18n-ok
      { label: 'SUBSTRING(col,at,len)', snippet: 'SUBSTRING(, 1, 3)',  back: 7, hint: t('pg.panelsA.calc.hint.substring') }, // i18n-ok
      { label: 'CONCAT(a,b)',           snippet: 'CONCAT(, )',         back: 3, hint: t('pg.panelsA.calc.hint.concat') }, // i18n-ok
      { label: 'REPLACE(col,a,b)',      snippet: 'REPLACE(, "", "")',  back: 8, hint: t('pg.panelsA.calc.hint.replace') }, // i18n-ok
      { label: 'FIND(col,"t")',         snippet: 'FIND(, "")',         back: 4, hint: t('pg.panelsA.calc.hint.find') }, // i18n-ok
      { label: 'CONTAINS(col,"t")',     snippet: 'CONTAINS(, "")',     back: 4, hint: t('pg.panelsA.calc.hint.contains') }, // i18n-ok
      { label: 'STARTSWITH(col,"t")',   snippet: 'STARTSWITH(, "")',   back: 4, hint: t('pg.panelsA.calc.hint.startswith') }, // i18n-ok
      { label: 'ENDSWITH(col,"t")',     snippet: 'ENDSWITH(, "")',     back: 4, hint: t('pg.panelsA.calc.hint.endswith') }, // i18n-ok
      { label: 'SPLIT(col,"-",n)',      snippet: 'SPLIT(, "-", 1)',    back: 8, hint: t('pg.panelsA.calc.hint.split') }, // i18n-ok
      { label: 'REVERSE(col)',          snippet: 'REVERSE()',          back: 1, hint: t('pg.panelsA.calc.hint.reverse') }, // i18n-ok
      { label: 'LPAD(col,w,"0")',       snippet: 'LPAD(, 5, "0")',     back: 8, hint: t('pg.panelsA.calc.hint.lpad') }, // i18n-ok
      { label: 'RPAD(col,w," ")',       snippet: 'RPAD(, 5, " ")',     back: 8, hint: t('pg.panelsA.calc.hint.rpad') }, // i18n-ok
      { label: 'to_text(x)',            snippet: 'str()',              back: 1, hint: t('pg.panelsA.calc.hint.to_text') }, // i18n-ok
    ],
  },
  {
    label: t('pg.panelsA.calc.cat.date'), color: '#f59e0b',
    items: [
      { label: 'year(col)',           snippet: 'YEAR()',              back: 1, hint: t('pg.panelsA.calc.hint.year') }, // i18n-ok
      { label: 'quarter(col)',        snippet: 'QUARTER()',           back: 1, hint: t('pg.panelsA.calc.hint.quarter') }, // i18n-ok
      { label: 'month(col)',          snippet: 'MONTH()',             back: 1, hint: t('pg.panelsA.calc.hint.month') }, // i18n-ok
      { label: 'day(col)',            snippet: 'DAY()',               back: 1, hint: t('pg.panelsA.calc.hint.day') }, // i18n-ok
      { label: 'datetrunc(col,unit)', snippet: "DATETRUNC(, 'month')", back: 9, hint: t('pg.panelsA.calc.hint.datetrunc') }, // i18n-ok
    ],
  },
  {
    label: t('pg.panelsA.calc.cat.conditional'), color: '#c084fc',
    items: [
      { label: 'IF(cond,yes,no)',           snippet: 'IF(, , )',           back: 5, hint: t('pg.panelsA.calc.hint.if') }, // i18n-ok
      { label: 'SWITCH(col,v1,r1,default)', snippet: 'SWITCH(, , , )',     back: 7, hint: t('pg.panelsA.calc.hint.switch') }, // i18n-ok
      { label: 'isnull(col)',               snippet: 'isnull()',           back: 1, hint: t('pg.panelsA.calc.hint.isnull') }, // i18n-ok
    ],
  },
  {
    label: t('pg.panelsA.calc.cat.aggregation'), color: '#f472b6',
    items: [
      { label: 'SUM(col)',       snippet: 'SUM()',       back: 1, hint: t('pg.panelsA.calc.hint.sum') }, // i18n-ok
      { label: 'AVG(col)',       snippet: 'AVG()',       back: 1, hint: t('pg.panelsA.calc.hint.avg') }, // i18n-ok
      { label: 'MEDIAN(col)',    snippet: 'MEDIAN()',    back: 1, hint: t('pg.panelsA.calc.hint.median') }, // i18n-ok
      { label: 'COUNT(col)',     snippet: 'COUNT()',     back: 1, hint: t('pg.panelsA.calc.hint.count') }, // i18n-ok
      { label: 'COUNTD(col)',    snippet: 'COUNTD()',    back: 1, hint: t('pg.panelsA.calc.hint.countd') }, // i18n-ok
      { label: 'STDEV(col)',     snippet: 'STDEV()',     back: 1, hint: t('pg.panelsA.calc.hint.stdev') }, // i18n-ok
      { label: 'VARIANCE(col)',  snippet: 'VARIANCE()',  back: 1, hint: t('pg.panelsA.calc.hint.variance') }, // i18n-ok
      { label: 'PCT_TOTAL(col)', snippet: 'PCT_TOTAL()', back: 1, hint: t('pg.panelsA.calc.hint.pct_total') }, // i18n-ok
      { label: 'NORMALIZE(col)', snippet: 'NORMALIZE()', back: 1, hint: t('pg.panelsA.calc.hint.normalize') }, // i18n-ok
      { label: 'ZSCORE(col)',    snippet: 'ZSCORE()',    back: 1, hint: t('pg.panelsA.calc.hint.zscore') }, // i18n-ok
    ],
  },
  {
    label: t('pg.panelsA.calc.cat.running'), color: '#fb923c',
    items: [
      { label: 'CUMSUM(col)',    snippet: 'CUMSUM()',    back: 1, hint: t('pg.panelsA.calc.hint.cumsum') }, // i18n-ok
      { label: 'CUMPCT(col)',    snippet: 'CUMPCT()',    back: 1, hint: t('pg.panelsA.calc.hint.cumpct') }, // i18n-ok
      { label: 'RANK(col)',      snippet: 'RANK()',      back: 1, hint: t('pg.panelsA.calc.hint.rank') }, // i18n-ok
      { label: 'DIFF(col)',      snippet: 'DIFF()',      back: 1, hint: t('pg.panelsA.calc.hint.diff') }, // i18n-ok
      { label: 'LAG(col, n)',    snippet: 'LAG(, 1)',    back: 4, hint: t('pg.panelsA.calc.hint.lag') }, // i18n-ok
      { label: 'LEAD(col, n)',   snippet: 'LEAD(, 1)',   back: 4, hint: t('pg.panelsA.calc.hint.lead') }, // i18n-ok
    ],
  },
  {
    label: t('pg.panelsA.calc.cat.groupBy'), color: '#2dd4bf',
    items: [
      { label: 'GROUPSUM(col,grp)',   snippet: 'GROUPSUM(, )',   back: 3, hint: t('pg.panelsA.calc.hint.groupsum') }, // i18n-ok
      { label: 'GROUPAVG(col,grp)',   snippet: 'GROUPAVG(, )',   back: 3, hint: t('pg.panelsA.calc.hint.groupavg') }, // i18n-ok
      { label: 'GROUPCOUNT(col,grp)', snippet: 'GROUPCOUNT(, )', back: 3, hint: t('pg.panelsA.calc.hint.groupcount') }, // i18n-ok
      { label: 'GROUPRANK(col,grp)',  snippet: 'GROUPRANK(, )',  back: 3, hint: t('pg.panelsA.calc.hint.grouprank') }, // i18n-ok
      { label: 'GROUPMIN(col,grp)',   snippet: 'GROUPMIN(, )',   back: 3, hint: t('pg.panelsA.calc.hint.groupmin') }, // i18n-ok
      { label: 'GROUPMAX(col,grp)',   snippet: 'GROUPMAX(, )',   back: 3, hint: t('pg.panelsA.calc.hint.groupmax') }, // i18n-ok
      { label: 'GROUPPCT(col,grp)',   snippet: 'GROUPPCT(, )',   back: 3, hint: t('pg.panelsA.calc.hint.grouppct') }, // i18n-ok
    ],
  },
  {
    label: t('pg.panelsA.calc.cat.dateParts'),
    color: '#38bdf8',
    items: [
      { label: 'WEEKDAY(col)',   snippet: 'WEEKDAY()',   back: 1, hint: t('pg.panelsA.calc.hint.weekday') }, // i18n-ok
      { label: 'WEEK(col)',      snippet: 'WEEK()',      back: 1, hint: t('pg.panelsA.calc.hint.week') }, // i18n-ok
      { label: 'DAYOFYEAR(col)', snippet: 'DAYOFYEAR()', back: 1, hint: t('pg.panelsA.calc.hint.dayofyear') }, // i18n-ok
      { label: 'HOUR(col)',      snippet: 'HOUR()',      back: 1, hint: t('pg.panelsA.calc.hint.hour') }, // i18n-ok
      { label: 'MINUTE(col)',    snippet: 'MINUTE()',    back: 1, hint: t('pg.panelsA.calc.hint.minute') }, // i18n-ok
      { label: 'SECOND(col)',    snippet: 'SECOND()',    back: 1, hint: t('pg.panelsA.calc.hint.second') }, // i18n-ok
      { label: 'MONTHNAME(col)', snippet: 'MONTHNAME()', back: 1, hint: t('pg.panelsA.calc.hint.monthname') }, // i18n-ok
      { label: 'DAYNAME(col)',   snippet: 'DAYNAME()',   back: 1, hint: t('pg.panelsA.calc.hint.dayname') }, // i18n-ok
    ],
  },
  {
    label: t('pg.panelsA.calc.cat.dateMaths'),
    color: '#38bdf8',
    items: [
      { label: 'DATEADD(col,n,"month")',  snippet: 'DATEADD(, 1, "month")',  back: 15, hint: t('pg.panelsA.calc.hint.dateadd') }, // i18n-ok
      { label: 'DATEDIFF(a,b,"day")',     snippet: 'DATEDIFF(, , "day")',    back: 10, hint: t('pg.panelsA.calc.hint.datediff') }, // i18n-ok
      { label: 'DATEFROMYMD(y,m,d)',      snippet: 'DATEFROMYMD(, , )',      back: 5,  hint: t('pg.panelsA.calc.hint.datefromymd') }, // i18n-ok
      { label: 'TODAY()',                 snippet: 'TODAY()',                back: 0, hint: t('pg.panelsA.calc.hint.today') }, // i18n-ok
      { label: 'NOW()',                   snippet: 'NOW()',                  back: 0, hint: t('pg.panelsA.calc.hint.now') }, // i18n-ok
      { label: 'TODATE(col)',             snippet: 'TODATE()',               back: 1, hint: t('pg.panelsA.calc.hint.todate') }, // i18n-ok
      { label: 'TONUMBER(col)',           snippet: 'TONUMBER()',             back: 1, hint: t('pg.panelsA.calc.hint.tonumber') }, // i18n-ok
    ],
  },
  {
    label: t('pg.panelsA.calc.cat.statistics'),
    color: '#a78bfa',
    items: [
      { label: 'PERCENTILE(col,q)', snippet: 'PERCENTILE(, 50)', back: 5, hint: t('pg.panelsA.calc.hint.percentile') }, // i18n-ok
      { label: 'MODE(col)',         snippet: 'MODE()',           back: 1, hint: t('pg.panelsA.calc.hint.mode') }, // i18n-ok
      { label: 'CORR(a,b)',         snippet: 'CORR(, )',         back: 3, hint: t('pg.panelsA.calc.hint.corr') }, // i18n-ok
      { label: 'COVAR(a,b)',        snippet: 'COVAR(, )',        back: 3, hint: t('pg.panelsA.calc.hint.covar') }, // i18n-ok
      { label: 'SKEW(col)',         snippet: 'SKEW()',           back: 1, hint: t('pg.panelsA.calc.hint.skew') }, // i18n-ok
      { label: 'KURTOSIS(col)',     snippet: 'KURTOSIS()',       back: 1, hint: t('pg.panelsA.calc.hint.kurtosis') }, // i18n-ok
      { label: 'IQR(col)',          snippet: 'IQR()',            back: 1, hint: t('pg.panelsA.calc.hint.iqr') }, // i18n-ok
      { label: 'SE(col)',           snippet: 'SE()',             back: 1, hint: t('pg.panelsA.calc.hint.se') }, // i18n-ok
    ],
  },
]

export interface OpItem { label: string; snippet: string; back?: number }
export const OP_GROUPS: { label: string; items: OpItem[] }[] = [
  { label: 'Arithmetic', items: [ // i18n-ok: a group key, translated by ExpressionBuilder (GROUP_KEY)
    { label: '+',  snippet: ' + '  },
    { label: '-',  snippet: ' - '  },
    { label: '*',  snippet: ' * '  },
    { label: '/',  snippet: ' / '  },
    { label: '**', snippet: ' ** ' },
    { label: '%',  snippet: ' % '  },
  ]},
  { label: 'Comparison', items: [ // i18n-ok: a group key, translated by ExpressionBuilder (GROUP_KEY)
    { label: '==', snippet: ' == ' },
    { label: '!=', snippet: ' != ' },
    { label: '>',  snippet: ' > '  },
    { label: '<',  snippet: ' < '  },
    { label: '>=', snippet: ' >= ' },
    { label: '<=', snippet: ' <= ' },
  ]},
  { label: 'Logical', items: [ // i18n-ok: a group key, translated by ExpressionBuilder (GROUP_KEY)
    { label: 'and', snippet: ' and ' }, // i18n-ok: an operator, code
    { label: 'or',  snippet: ' or '  }, // i18n-ok: an operator, code
    { label: 'not', snippet: ' not ' }, // i18n-ok: an operator, code
    { label: '(',   snippet: '('     },
    { label: ')',   snippet: ')'     },
  ]},
]

