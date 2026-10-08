import type { PrepStep } from '../../../services/api'
import { en } from '../../../i18n/pages/panelsB'
import type { MessageKey, TranslateFn } from '../../../i18n'

// `disabled` is a first-class, PERSISTED step field (engine-recognised in
// prep.py): a paused step round-trips through save/GET and is skipped at
// apply time, rather than being silently dropped from the saved pipeline.
// `_key` is the only client-only field, used purely as a React list key.
export type EditStep = PrepStep & { disabled?: boolean; _key: number }

/** The filter step's function palette. Function names are code; the group
 *  name and the hints are what a reader sees, so they come from the catalog. */
export function filterFuncCats(t: TranslateFn) {
  return [
    {
      label: t('pg.panelsB.fn.conditional'), color: '#c084fc',
      items: [
        { label: 'isnull(col)',         snippet: 'isnull()',        back: 1, hint: t('pg.panelsB.fn.isnull') }, // i18n-ok
        { label: 'CONTAINS(col,"t")',   snippet: 'CONTAINS(, "")',  back: 4, hint: t('pg.panelsB.fn.contains') }, // i18n-ok
        { label: 'STARTSWITH(col,"t")', snippet: 'STARTSWITH(, "")', back: 4, hint: t('pg.panelsB.fn.startswith') }, // i18n-ok
        { label: 'ENDSWITH(col,"t")',   snippet: 'ENDSWITH(, "")',  back: 4, hint: t('pg.panelsB.fn.endswith') }, // i18n-ok
      ],
    },
  ]
}

/** A step kind's display name; an unknown kind shows as its id. */
export function kindLabel(t: TranslateFn, kind: string): string {
  const key = `pg.panelsB.kind.${kind}`
  return key in en ? t(key as MessageKey) : kind
}

/** The display label of an option whose value is a code (`opt.<group>.<v>`);
 *  a value with no label shows as itself. English labels are the codes. */
export function optLabel(t: TranslateFn, group: string, value: unknown): string {
  const key = `pg.panelsB.opt.${group}.${String(value)}`
  return key in en ? t(key as MessageKey) : String(value)
}

export const KIND_ICONS: Record<string, string> = {
  filter_rows: '⏳', sort: '↕', dedupe: '⧉', drop_duplicates: '⧉', aggregate: 'Σ',
  rename: '✎', retype: '#', split: '✂', trim: '␣', case: 'Aa', replace: '⇄',
  remove_columns: '⊟', drop_nulls: '∅', fill_nulls: '▦', join: '⋈', partition: '◧',
  append: '⊕', outliers: '⚑', normalize: '⇲', encode: '⌗', date_parts: '📅', feature_select: '⛉',
  pca: '⊿', balance: '⚖',
  edit_cells: '⌨',
}

export const ADD_MENU_KINDS = [
  'filter_rows', 'sort', 'dedupe', 'aggregate', 'rename', 'retype', 'split',
  'trim', 'case', 'replace', 'remove_columns', 'drop_nulls', 'fill_nulls', 'join', 'append', 'partition',
  'outliers', 'normalize', 'encode', 'date_parts', 'feature_select', 'pca', 'balance',
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
    case 'append':         return { kind, dataset_id: null }
    case 'outliers':       return { kind, columns: [], method: 'iqr', k: 1.5, action: 'flag', name: '_Outlier_' }
    case 'normalize':      return { kind, columns: [], method: 'minmax', suffix: '' }
    case 'encode':         return { kind, column: '', method: 'onehot', categories: [] }
    case 'date_parts':     return { kind, column: '', parts: ['year', 'month'] }
    case 'feature_select': return { kind, min_variance: 0, keep: [] }
    case 'pca':            return { kind, columns: [], n: 2, prefix: 'PC' }
    case 'balance':        return { kind, column: '', method: 'undersample', seed: 42 }
    default:                return { kind }
  }
}

