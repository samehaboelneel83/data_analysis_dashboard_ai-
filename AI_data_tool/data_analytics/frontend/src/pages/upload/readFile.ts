/**
 * Upload (autopilot step 5): reading a chosen file in the browser, before
 * anything is sent, so the review can show its first rows. Only the reader's
 * own file is read; nothing here is sample data.
 *
 * Text files (CSV, TSV, TXT) and JSON (an array of records) are read here.
 * Excel, Parquet, XML and Access need the server, so their preview is the
 * dataset itself, after import.
 *
 * The column kinds are this reader's guess from the first rows, shown as a
 * hint; the server decides the real types on import.
 */

export type Kind = 'csv' | 'xlsx' | 'json' | 'xml' | 'parquet' | 'access' | 'other'
export type ColType = 'num' | 'date' | 'bool' | 'text'

export interface Preview {
  columns: string[]
  types: ColType[]
  rows: string[][]
  /** All the data rows, when the whole file was read; null for a large file. */
  total: number | null
  /** Empty cells in what was read. */
  missing: number
  /** Columns whose dates could be day/month or month/day ("05/09/2025"). */
  ambiguousDates: string[]
}

export const PREVIEW_ROWS = 20
/** Read whole files up to this size (for the row count); larger ones only their head. */
const WHOLE_BYTES = 5 * 1024 * 1024
const HEAD_BYTES = 256 * 1024

export function kindOf(name: string): Kind {
  const ext = name.toLowerCase().split('.').pop() ?? ''
  if (['csv', 'tsv', 'txt'].includes(ext)) return 'csv'
  if (['xlsx', 'xls'].includes(ext)) return 'xlsx'
  if (ext === 'json') return 'json'
  if (ext === 'xml') return 'xml'
  if (ext === 'parquet') return 'parquet'
  if (['mdb', 'accdb'].includes(ext)) return 'access'
  return 'other'
}
export const readable = (k: Kind) => k === 'csv' || k === 'json'

/** RFC 4180: quoted fields, doubled quotes, line breaks inside quotes. */
export function parseDelimited(text: string, delimiter?: string): string[][] {
  const nl = text.search(/\r?\n/)
  const first = nl < 0 ? text : text.slice(0, nl)
  const d = delimiter ?? ([',', ';', '\t', '|'].map(c => [c, first.split(c).length] as const).sort((a, b) => b[1] - a[1])[0][0])
  const rows: string[][] = []
  let row: string[] = [], field = '', quoted = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (quoted) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++ } else quoted = false }
      else field += c
    } else if (c === '"' && field === '') quoted = true
    else if (c === d) { row.push(field); field = '' }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++
      row.push(field); field = ''
      if (row.length > 1 || row[0] !== '') rows.push(row)
      row = []
    } else field += c
  }
  if (field !== '' || row.length) { row.push(field); rows.push(row) }
  return rows
}

const NUM = /^[-+]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$/
const ISO = /^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?/
const SLASH = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})$/
const BOOL = /^(true|false|yes|no)$/i

export function guessType(values: string[]): ColType {
  const v = values.map(x => x.trim()).filter(Boolean)
  if (!v.length) return 'text'
  if (v.every(x => NUM.test(x))) return 'num'
  if (v.every(x => ISO.test(x) || SLASH.test(x))) return 'date'
  if (v.every(x => BOOL.test(x))) return 'bool'
  return 'text'
}

/** Day/month or month/day? Only when no value settles it (a part over 12). */
export function ambiguousDate(values: string[]): boolean {
  const parts = values.map(x => SLASH.exec(x.trim())).filter((m): m is RegExpExecArray => !!m)
  if (!parts.length) return false
  return parts.every(m => Number(m[1]) <= 12 && Number(m[2]) <= 12) && parts.some(m => m[1] !== m[2])
}

export function previewOf(table: string[][], whole: boolean): Preview {
  const [head = [], ...data] = table
  const width = Math.max(head.length, ...data.slice(0, PREVIEW_ROWS).map(r => r.length))
  const columns = Array.from({ length: width }, (_, i) => head[i]?.trim() || `column_${i + 1}`)
  const sample = data.slice(0, 200)
  const col = (i: number) => sample.map(r => r[i] ?? '')
  return {
    columns,
    types: columns.map((_, i) => guessType(col(i))),
    rows: data.slice(0, PREVIEW_ROWS).map(r => columns.map((_, i) => r[i] ?? '')),
    total: whole ? data.length : null,
    missing: (whole ? data : sample).reduce((n, r) => n + columns.filter((_, i) => !(r[i] ?? '').trim()).length, 0),
    ambiguousDates: columns.filter((_, i) => ambiguousDate(col(i))),
  }
}

export function previewJson(text: string): Preview | null {
  let data: unknown
  try { data = JSON.parse(text) } catch { return null }
  const list = Array.isArray(data) ? data : data && typeof data === 'object' ? Object.values(data).find(Array.isArray) : null
  if (!Array.isArray(list) || !list.length || typeof list[0] !== 'object' || list[0] === null) return null
  const columns = [...new Set(list.slice(0, 200).flatMap(r => (r && typeof r === 'object' ? Object.keys(r) : [])))]
  const cell = (v: unknown) => (v == null ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v))
  const table = [columns, ...list.map(r => columns.map(c => cell((r as Record<string, unknown>)[c])))]
  return previewOf(table, true)
}

/** A blob's text (FileReader where `Blob.text` is missing). */
function textOf(b: Blob): Promise<string> {
  if (typeof b.text === 'function') return b.text()
  return new Promise((ok, fail) => { const r = new FileReader(); r.onload = () => ok(String(r.result)); r.onerror = () => fail(r.error); r.readAsText(b) })
}

/** Read a file's head (or all of it, when small) and build its preview. */
export async function readPreview(file: File): Promise<Preview | null> {
  const kind = kindOf(file.name)
  if (!readable(kind)) return null
  const whole = file.size <= WHOLE_BYTES
  if (kind === 'json') return whole ? previewJson(await textOf(file)) : null
  let text = await textOf(whole ? file : file.slice(0, HEAD_BYTES))
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1)
  // A cut head ends mid-row: drop the last, partial line.
  if (!whole) text = text.slice(0, text.lastIndexOf('\n'))
  const table = parseDelimited(text)
  return table.length ? previewOf(table, whole) : null
}

/** "enrolments_2025.csv" -> "Enrolments 2025": a name to start from. Only
 *  the extension goes and underscores become spaces; hyphens are part of the
 *  name ("QAF-upload" stays "QAF-upload", QAF 21). */
export function nameFromFile(file: string): string {
  const stem = file.replace(/\.[^.]+$/, '').replace(/_+/g, ' ').replace(/\s+/g, ' ').trim()
  return stem.charAt(0).toUpperCase() + stem.slice(1)
}
