import type { PrepStep } from '../../../services/api'

// `disabled` is a first-class, PERSISTED step field (engine-recognised in
// prep.py): a paused step round-trips through save/GET and is skipped at
// apply time, rather than being silently dropped from the saved pipeline.
// `_key` is the only client-only field, used purely as a React list key.
export type EditStep = PrepStep & { disabled?: boolean; _key: number }

export const FILTER_FUNC_CATS = [
  {
    label: 'Conditional', color: '#c084fc',
    items: [
      { label: 'isnull(col)',         snippet: 'isnull()',        back: 1, hint: 'True if value is missing / null' },
      { label: 'CONTAINS(col,"t")',   snippet: 'CONTAINS(, "")',  back: 4, hint: 'True if the text appears' },
      { label: 'STARTSWITH(col,"t")', snippet: 'STARTSWITH(, "")', back: 4, hint: 'True if it begins with the text' },
      { label: 'ENDSWITH(col,"t")',   snippet: 'ENDSWITH(, "")',  back: 4, hint: 'True if it ends with the text' },
    ],
  },
]

export const KIND_LABELS: Record<string, string> = {
  filter_rows: 'Filter rows',
  sort: 'Sort',
  dedupe: 'Remove duplicates',
  drop_duplicates: 'Remove duplicates (legacy)',
  aggregate: 'Aggregate',
  rename: 'Rename column',
  retype: 'Change type',
  split: 'Split column',
  trim: 'Trim whitespace',
  case: 'Change case',
  replace: 'Find & replace',
  remove_columns: 'Remove columns',
  drop_nulls: 'Drop empty rows',
  fill_nulls: 'Fill empty values',
  join: 'Join dataset',
  partition: 'Partition (train / validation)',
  // Written by the data grid's cell editor, never added from the menu here.
  edit_cells: 'Edit cells',
}

export const KIND_ICONS: Record<string, string> = {
  filter_rows: '⏳', sort: '↕', dedupe: '⧉', drop_duplicates: '⧉', aggregate: 'Σ',
  rename: '✎', retype: '#', split: '✂', trim: '␣', case: 'Aa', replace: '⇄',
  remove_columns: '⊟', drop_nulls: '∅', fill_nulls: '▦', join: '⋈', partition: '◧',
  edit_cells: '⌨',
}

export const ADD_MENU_KINDS = [
  'filter_rows', 'sort', 'dedupe', 'aggregate', 'rename', 'retype', 'split',
  'trim', 'case', 'replace', 'remove_columns', 'drop_nulls', 'fill_nulls', 'join', 'partition',
]

let keySeq = 1
export function withKey(s: PrepStep): EditStep { return { ...s, _key: keySeq++ } }

export function newStep(kind: string): PrepStep {
  switch (kind) {
    case 'filter_rows':    return { kind, expression: '' }
    case 'sort':           return { kind, columns: [] }
    case 'dedupe':         return { kind, subset: [] }
    case 'aggregate':      return { kind, group_by: [], aggregations: [] }
    case 'rename':         return { kind, column: '', to: '' }
    case 'retype':         return { kind, column: '', to: 'text' }
    case 'split':          return { kind, column: '', delimiter: '', into: [] }
    case 'trim':           return { kind, columns: [] }
    case 'case':           return { kind, column: '', to: 'upper' }
    case 'replace':        return { kind, column: '', find: '', replace: '', match: 'exact' }
    case 'remove_columns': return { kind, columns: [] }
    case 'drop_nulls':     return { kind, columns: [] }
    case 'fill_nulls':     return { kind, column: '', method: 'value', value: '' }
    case 'join':           return { kind, dataset_id: null, how: 'left', left_on: '', right_on: '' }
    case 'partition':      return { kind, name: '_Partition_', train_pct: 70, seed: 42 }
    default:                return { kind }
  }
}

