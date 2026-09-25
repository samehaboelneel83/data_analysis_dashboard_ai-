import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export type Direction = 'ltr' | 'rtl'

/** UI languages offered by the switcher. Codes match the locale grammar the
 *  report-translation endpoints already validate (`^[a-z]{2}(-…)?$`). */
export type Language = 'en' | 'ar'

const STORAGE_KEY = 'datalytics.direction'
const LANG_KEY = 'datalytics.language'

/** The direction each language reads in. Language is the user-facing choice;
 *  direction follows from it, which is why the switcher sets one control and
 *  not two. A user may still override direction alone from the rail. */
export const LANGUAGE_DIRECTION: Record<Language, Direction> = { en: 'ltr', ar: 'rtl' }

export const LANGUAGE_LABEL: Record<Language, string> = { en: 'English', ar: 'العربية' }

interface DirectionContextValue {
  direction: Direction
  rtl: boolean
  setDirection: (d: Direction) => void
  language: Language
  /** Sets the language AND the direction it reads in, in one act. */
  setLanguage: (l: Language) => void
}

/**
 * App-wide reading direction.
 *
 * Stored per USER in localStorage rather than per org on the server. That is a
 * deliberate limit, not an oversight: `OrgTheme` has no general settings blob to
 * put it in, and adding a column would land in the trap this codebase documents
 * repeatedly — `create_all` never ALTERs a live table, so a new column exists on
 * fresh installs and is silently missing on every deployed one. Direction is
 * also genuinely a reader's preference: two people in one org may want opposite
 * directions, which a single org-level value could not express.
 *
 * Exported alongside the hook so a component rendered in isolation (a test, a
 * print view) can read it without a provider and fall back to LTR rather than
 * throwing.
 */
export const DirectionContext = createContext<DirectionContextValue | null>(null)

function read(): Direction {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'rtl' ? 'rtl' : 'ltr'
  } catch {
    // Private windows and blocked site-data throw on access rather than
    // returning null, so this has to be a try/catch, not a null check.
    return 'ltr'
  }
}

function readLanguage(): Language {
  try {
    return localStorage.getItem(LANG_KEY) === 'ar' ? 'ar' : 'en'
  } catch {
    return 'en'
  }
}

export function DirectionProvider({ children }: { children: ReactNode }) {
  const [direction, setDirectionState] = useState<Direction>(read)
  const [language, setLanguageState] = useState<Language>(readLanguage)

  // The document root is the single source of truth the browser acts on: it
  // mirrors flexbox, grid, scrollbars, text alignment and every logical CSS
  // property at once. Setting it here rather than on a wrapper div means the
  // whole shell — including portals and dialogs rendered outside the tree —
  // inherits it.
  useEffect(() => {
    document.documentElement.dir = direction
  }, [direction])

  // `lang` follows the LANGUAGE, not the direction. Combined with `src/i18n`,
  // picking Arabic also swaps chrome strings; `lang="ar"` tells the screen
  // reader to use an Arabic voice for that chrome and for report translations.
  useEffect(() => {
    document.documentElement.lang = language
  }, [language])

  const setDirection = (d: Direction) => {
    setDirectionState(d)
    try {
      localStorage.setItem(STORAGE_KEY, d)
    } catch {
      // Preference is lost on reload; the session still works. Failing loudly
      // here would break the app over a cosmetic setting.
    }
  }

  /** Picking a language sets the direction it reads in, in the same act --
   *  choosing العربية and then having to find a second switch to make the page
   *  read right-to-left is a puzzle, not a preference. */
  const setLanguage = (l: Language) => {
    setLanguageState(l)
    try {
      localStorage.setItem(LANG_KEY, l)
    } catch { /* see setDirection */ }
    setDirection(LANGUAGE_DIRECTION[l])
  }

  return (
    <DirectionContext.Provider
      value={{ direction, rtl: direction === 'rtl', setDirection, language, setLanguage }}>
      {children}
    </DirectionContext.Provider>
  )
}

/** App direction and language, defaulting to English/LTR with no provider. */
export function useDirection(): DirectionContextValue {
  return useContext(DirectionContext) ?? {
    direction: 'ltr', rtl: false, setDirection: () => {},
    language: 'en', setLanguage: () => {},
  }
}

/**
 * Whether one widget should render right-to-left.
 *
 * `cfg.rtl` is a per-widget OVERRIDE, and the subtlety is that it cannot be
 * read as a plain boolean. `WidgetConfigPanel` writes `rtl` unconditionally into
 * every saved config, so essentially every widget that exists carries
 * `rtl: false` — meaning "the author never turned this on", not "the author
 * demanded left-to-right". Treating that stored `false` as an assertion would
 * pin every existing widget to LTR and make app-wide RTL do nothing at all,
 * which is precisely the bug that makes a direction switch feel broken.
 *
 * So: `true` forces RTL for this widget; anything else follows the app.
 */
export function widgetIsRtl(cfgRtl: unknown, appRtl: boolean): boolean {
  return cfgRtl === true || appRtl
}

/**
 * Navigational arrows for the current direction.
 *
 * These glyphs are the one thing `dir` cannot fix. The browser mirrors layout,
 * but a `←` is a character: it keeps pointing left in an RTL page, where "back"
 * is to the right. Trend arrows (`↑` `↓`) and disclosure triangles are NOT
 * direction-coded and must not be flipped -- up is up in every language.
 */
export function navArrows(rtl: boolean) {
  return {
    back: rtl ? '→' : '←',
    forward: rtl ? '←' : '→',
    backChevron: rtl ? '›' : '‹',
    forwardChevron: rtl ? '‹' : '›',
  }
}
