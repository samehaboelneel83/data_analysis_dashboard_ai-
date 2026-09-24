/** Arabic formats (Phase 7.5): digits, Hijri month names, MENA currencies.
 *
 *  One coherent story with RTL, Arabic NL->SQL and Arabic text analytics: a
 *  reader can see numbers in the digits they read (١٢٣ or 123 -- a preference,
 *  because the Gulf mostly reads Latin digits and Egypt Arabic-Indic), dates
 *  bucketed by Hijri month with the month named, and money with its own
 *  symbol on the side Arabic puts it. */

export type Digits = 'latn' | 'arab'
const DIGITS_KEY = 'datalytics.digits'
const LANG_KEY = 'datalytics.language'
const ARABIC_INDIC = '٠١٢٣٤٥٦٧٨٩'

let cached: Digits | null = null

export function getDigits(): Digits {
  if (cached) return cached
  try { cached = localStorage.getItem(DIGITS_KEY) === 'arab' ? 'arab' : 'latn' } catch { cached = 'latn' }
  return cached
}

export function setDigits(d: Digits): void {
  cached = d
  try { localStorage.setItem(DIGITS_KEY, d) } catch { /* private mode: this session only */ }
  window.dispatchEvent(new CustomEvent('datalytics:digits', { detail: d }))
}

/** For tests and after a preference change in another tab. */
export function resetDigitsCache(): void { cached = null }

function uiLanguage(): 'ar' | 'en' {
  try { return localStorage.getItem(LANG_KEY) === 'ar' ? 'ar' : 'en' } catch { return 'en' }
}

/** Western digits -> Arabic-Indic, with the Arabic decimal and thousands
 *  separators, when the reader asked for them. Everything else passes through. */
export function localDigits(s: string): string {
  if (getDigits() !== 'arab') return s
  return s.replace(/(\d),(?=\d{3}\b)/g, '$1٬')
    .replace(/(\d)\.(\d)/g, '$1٫$2')
    .replace(/[0-9]/g, d => ARABIC_INDIC[Number(d)])
}

export const HIJRI_MONTHS_AR = ['محرم', 'صفر', 'ربيع الأول', 'ربيع الآخر', 'جمادى الأولى', 'جمادى الآخرة',
  'رجب', 'شعبان', 'رمضان', 'شوال', 'ذو القعدة', 'ذو الحجة']
export const HIJRI_MONTHS_EN = ['Muharram', 'Safar', 'Rabiʿ I', 'Rabiʿ II', 'Jumada I', 'Jumada II',
  'Rajab', 'Shaʿban', 'Ramadan', 'Shawwal', 'Dhu al-Qaʿda', 'Dhu al-Hijja']

/** "1444-09" -> "Ramadan 1444" / "رمضان 1444 هـ"; anything else unchanged. */
export function hijriLabel(label: unknown, lang: 'ar' | 'en' = uiLanguage()): string {
  const s = String(label ?? '')
  const m = /^(\d{3,4})-(\d{2})$/.exec(s)
  if (!m) return /^\d{3,4}$/.test(s) ? localDigits(lang === 'ar' ? `${s} هـ` : `${s} AH`) : s
  const month = Number(m[2])
  if (month < 1 || month > 12) return s
  return lang === 'ar'
    ? localDigits(`${HIJRI_MONTHS_AR[month - 1]} ${m[1]} هـ`)
    : `${HIJRI_MONTHS_EN[month - 1]} ${m[1]}`
}

/** Currencies of the region, with the symbol Arabic readers expect. */
export const MENA_CURRENCIES: { code: string; ar: string; name: string }[] = [
  { code: 'SAR', ar: 'ر.س', name: 'Saudi riyal' },
  { code: 'AED', ar: 'د.إ', name: 'UAE dirham' },
  { code: 'EGP', ar: 'ج.م', name: 'Egyptian pound' },
  { code: 'KWD', ar: 'د.ك', name: 'Kuwaiti dinar' },
  { code: 'QAR', ar: 'ر.ق', name: 'Qatari riyal' },
  { code: 'BHD', ar: 'د.ب', name: 'Bahraini dinar' },
  { code: 'OMR', ar: 'ر.ع.', name: 'Omani rial' },
  { code: 'JOD', ar: 'د.أ', name: 'Jordanian dinar' },
  { code: 'MAD', ar: 'د.م.', name: 'Moroccan dirham' },
]

/** Arabic-script symbols go after the amount, as Arabic writes them. */
export function symbolAfter(symbol: string, position?: 'before' | 'after'): boolean {
  if (position) return position === 'after'
  return /[؀-ۿ]/.test(symbol)
}
