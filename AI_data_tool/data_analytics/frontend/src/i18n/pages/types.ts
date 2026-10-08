/**
 * QA5: shared display names (column types and similar codes), in English and
 * Arabic. Spread into en.ts / ar.ts. Keys start with "pg.types." and the two
 * objects hold the same keys.
 *
 * `pg.types.<code>` is the full name ("Number"), `pg.types.short.<code>` the
 * badge form ("NUM"). Read them through src/lib/dtypeName.ts, never directly.
 */
export const en = {
  'pg.types.numeric': 'Number',
  'pg.types.integer': 'Whole number',
  'pg.types.float': 'Decimal number',
  'pg.types.categorical': 'Category',
  'pg.types.text': 'Text',
  'pg.types.datetime': 'Date & time',
  'pg.types.date': 'Date',
  'pg.types.time': 'Time',
  'pg.types.boolean': 'True/false',
  'pg.types.geometry': 'Geometry',
  'pg.types.calculated': 'Calculated',

  'pg.types.short.numeric': 'NUM',
  'pg.types.short.integer': 'INT',
  'pg.types.short.float': 'DEC',
  'pg.types.short.categorical': 'TXT',
  'pg.types.short.text': 'TXT',
  'pg.types.short.datetime': 'DATE',
  'pg.types.short.date': 'DATE',
  'pg.types.short.time': 'TIME',
  'pg.types.short.boolean': 'BOOL',
  'pg.types.short.geometry': 'GEO',
  'pg.types.short.calculated': 'CALC',
} as const

export const ar: Record<keyof typeof en, string> = {
  'pg.types.numeric': 'رقم',
  'pg.types.integer': 'عدد صحيح',
  'pg.types.float': 'عدد عشري',
  'pg.types.categorical': 'فئة',
  'pg.types.text': 'نص',
  'pg.types.datetime': 'تاريخ ووقت',
  'pg.types.date': 'تاريخ',
  'pg.types.time': 'وقت',
  'pg.types.boolean': 'صح/خطأ',
  'pg.types.geometry': 'شكل جغرافي',
  'pg.types.calculated': 'محسوب',

  'pg.types.short.numeric': 'رقم',
  'pg.types.short.integer': 'صحيح',
  'pg.types.short.float': 'عشري',
  'pg.types.short.categorical': 'نص',
  'pg.types.short.text': 'نص',
  'pg.types.short.datetime': 'تاريخ',
  'pg.types.short.date': 'تاريخ',
  'pg.types.short.time': 'وقت',
  'pg.types.short.boolean': 'منطقي',
  'pg.types.short.geometry': 'جغرافي',
  'pg.types.short.calculated': 'محسوب',
}
