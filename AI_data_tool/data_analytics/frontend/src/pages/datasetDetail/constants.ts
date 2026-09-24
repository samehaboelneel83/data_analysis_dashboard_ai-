import type { DataPreviewFilter } from '../../services/api'

export type Tab = 'overview' | 'data' | 'meaning' | 'statistics' | 'alerts' | 'models'
         | 'aggregates'

export const OPS: { value: DataPreviewFilter['op']; label: string }[] = [
  { value: 'eq',         label: '=='         },
  { value: 'ne',         label: '!='         },
  { value: 'gt',         label: '>'          },
  { value: 'lt',         label: '<'          },
  { value: 'gte',        label: '>='         },
  { value: 'lte',        label: '<='         },
  { value: 'contains',   label: 'contains'   },
  { value: 'startswith', label: 'starts with'},
]

// Function palette for the dataset-level row filter builder — a subset of
// CalcColumnsPanel's catalog relevant to boolean filter expressions.
export const FILTER_FUNC_CATS = [
  {
    label: 'Conditional', color: '#c084fc',
    items: [
      { label: 'isnull(col)',           snippet: 'isnull()',        back: 1, hint: 'True if value is missing / null' },
      { label: 'CONTAINS(col,"t")',     snippet: 'CONTAINS(, "")',  back: 4, hint: 'True if the text appears' },
      { label: 'STARTSWITH(col,"t")',   snippet: 'STARTSWITH(, "")', back: 4, hint: 'True if it begins with the text' },
      { label: 'ENDSWITH(col,"t")',     snippet: 'ENDSWITH(, "")',  back: 4, hint: 'True if it ends with the text' },
    ],
  },
  {
    label: 'Text', color: '#34d399',
    items: [
      { label: 'SENTIMENT(col)', snippet: 'SENTIMENT()', back: 1, hint: 'Tone of the text, -1 to 1 (English + Arabic)' },
      { label: 'UPPER(col)', snippet: 'UPPER()', back: 1, hint: 'Convert to uppercase' },
      { label: 'LOWER(col)', snippet: 'LOWER()', back: 1, hint: 'Convert to lowercase' },
      { label: 'TRIM(col)',  snippet: 'TRIM()',  back: 1, hint: 'Remove surrounding spaces' },
    ],
  },
  {
    label: 'Date', color: '#f59e0b',
    items: [
      { label: 'year(col)',  snippet: 'YEAR()',  back: 1, hint: 'Extract year from date' },
      { label: 'month(col)', snippet: 'MONTH()', back: 1, hint: 'Month number (1–12)' },
      { label: 'day(col)',   snippet: 'DAY()',   back: 1, hint: 'Day of month (1–31)' },
      { label: 'TODAY()',    snippet: 'TODAY()', back: 0, hint: 'Today at midnight' },
    ],
  },
]

export const PAGE_SIZE = 100

