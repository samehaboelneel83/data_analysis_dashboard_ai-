/**
 * The interface speaks no trade's language (docs/discovery/PLAN.md, phase 0).
 *
 * Datalytics is a general-purpose platform: an example in a placeholder, a
 * tooltip or an empty state must not name one field of work or one place.
 * This reads every string of the catalogues and the builder's label map.
 *
 * The word list mirrors `backend/tests/test_domain_neutral.py` (TRADE_WORDS),
 * which keeps the engine's word lists and prompts neutral; change both together.
 * Words every organisation's books share (amount, cost, revenue, budget) and
 * words of structure and measurement (id, rate, price, count, region) are not listed.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = join(__dirname, '..')

const TRADE_WORDS = [
  // people at work
  'salary', 'salaries', 'wage', 'wages', 'payroll', 'employee', 'employees', 'headcount', 'hire', 'hires',
  'hired', 'hiring', 'tenure',
  // commerce and logistics
  'customer', 'customers', 'seller', 'sellers', 'shipment', 'shipments', 'shipped', 'parcel', 'parcels',
  'freight', 'sku', 'commodity', 'commodities', 'churn', 'invoice', 'invoices', 'checkout', 'cart',
  // things for sale
  'mileage', 'odometer', 'bedroom', 'bedrooms', 'bathroom', 'bathrooms',
  // health, education, telecom, places
  'patient', 'patients', 'hospital', 'tuition', 'imei', 'imsi', 'msisdn', 'iccid',
  'olist', 'cairo', 'giza', 'egp',
]
// Not listed: «عميل», which is also the word for a software client (an OAuth client id).
const ARABIC = ['موظف', 'الموظف', 'الموظفون', 'الموظفين', 'راتب', 'الراتب', 'رواتب', 'الرواتب',
  'شحنة', 'الشحنة', 'شحنات', 'مريض', 'المرضى', 'فاتورة', 'الفواتير', 'القاهرة', 'الجيزة']

const WORD = new RegExp(`(?<![A-Za-z])(${TRADE_WORDS.join('|')})(?![A-Za-z])`, 'i')
const AR_WORD = new RegExp(`(?<![\\u0600-\\u06FF])(${ARABIC.join('|')})(?![\\u0600-\\u06FF])`)

/** Keys allowed to keep a listed word, with the reason. Keep this short. */
const ALLOWED: Record<string, string> = {
  'pg.adminPlatform.set.data_timezone.help': 'a time zone is named the way the zone database names it',
  'pg.adminPlatform.maps.pack.egypt-governorates.description': 'an optional map pack describes the place it draws',
}

function files(dir: string): string[] {
  return readdirSync(dir).flatMap(name => {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) return files(p)
    return /\.ts$/.test(name) && !/\.test\.ts$/.test(name) ? [p] : []
  })
}

/** `'key': 'text'` entries, one per line, in either quote style. */
const ENTRY = /^\s*(['"])((?:\\.|(?!\1).)+)\1\s*:\s*(['"`])((?:\\.|(?!\3).)*)\3,?\s*(?:\/\/.*)?$/

describe('the catalogue names no field of work', () => {
  it('has no trade noun or place name in a reader-visible string', () => {
    const found: string[] = []
    for (const path of [...files(join(SRC, 'i18n')), join(SRC, 'components/report/panelLabels.ts')]) {
      readFileSync(path, 'utf8').split('\n').forEach((line, i) => {
        const m = ENTRY.exec(line)
        if (!m || ALLOWED[m[2]]) return
        // In the label map the English phrase is the key; elsewhere the key is an identifier.
        const text = path.endsWith('panelLabels.ts') ? `${m[2]} ${m[4]}` : m[4]
        const hit = WORD.exec(text) ?? AR_WORD.exec(text)
        if (hit) found.push(`${relative(SRC, path)}:${i + 1} [${hit[1]}] ${m[2]}`)
      })
    }
    expect(found).toEqual([])
  })
})
