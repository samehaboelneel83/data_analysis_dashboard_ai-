import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import LanguageSwitcher from './LanguageSwitcher'
import { DirectionProvider } from '../contexts/DirectionContext'

/**
 * Picking a language must move BOTH document attributes: `dir` (what mirrors
 * the layout) and `lang` (what makes a screen reader pick the right voice).
 * Setting one without the other is the half-done state this control exists to
 * prevent -- an Arabic page that still reads left-to-right, or an RTL page a
 * screen reader still pronounces in English.
 */

const renderSwitcher = () =>
  render(<DirectionProvider><LanguageSwitcher /></DirectionProvider>)

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('lang')
  document.documentElement.removeAttribute('dir')
})
afterEach(() => localStorage.clear())

describe('LanguageSwitcher', () => {
  it('starts in English, left-to-right', () => {
    renderSwitcher()
    expect(screen.getByRole('button', { name: /Language: English/ })).toBeInTheDocument()
    expect(document.documentElement.lang).toBe('en')
    expect(document.documentElement.dir).toBe('ltr')
  })

  it('choosing Arabic sets BOTH lang and dir', () => {
    renderSwitcher()
    fireEvent.click(screen.getByRole('button', { name: /Language: English/ }))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /العربية/ }))

    expect(document.documentElement.lang).toBe('ar')
    expect(document.documentElement.dir).toBe('rtl')
  })

  it('switching back to English restores left-to-right', () => {
    renderSwitcher()
    fireEvent.click(screen.getByRole('button', { name: /Language/ }))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /العربية/ }))
    fireEvent.click(screen.getByRole('button', { name: /اللغة/ }))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /English/ }))

    expect(document.documentElement.lang).toBe('en')
    expect(document.documentElement.dir).toBe('ltr')
  })

  it('marks the active language for assistive technology', () => {
    renderSwitcher()
    fireEvent.click(screen.getByRole('button', { name: /Language/ }))
    expect(screen.getByRole('menuitemradio', { name: /English/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('menuitemradio', { name: /العربية/ })).toHaveAttribute('aria-checked', 'false')
  })

  it('renders each option in its own script and direction', () => {
    // The Arabic option must not inherit the LTR page's direction, or the
    // label renders with its punctuation on the wrong side.
    renderSwitcher()
    fireEvent.click(screen.getByRole('button', { name: /Language/ }))
    const arabic = screen.getByRole('menuitemradio', { name: /العربية/ })
    expect(arabic).toHaveAttribute('lang', 'ar')
    expect(arabic).toHaveAttribute('dir', 'rtl')
  })

  it('survives a reload', () => {
    renderSwitcher()
    fireEvent.click(screen.getByRole('button', { name: /Language/ }))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /العربية/ }))

    // A second mount reads the stored preference, as a page refresh would.
    document.documentElement.removeAttribute('lang')
    renderSwitcher()
    expect(document.documentElement.lang).toBe('ar')
    expect(document.documentElement.dir).toBe('rtl')
  })

  it('Escape closes the menu', () => {
    renderSwitcher()
    fireEvent.click(screen.getByRole('button', { name: /Language/ }))
    expect(screen.getByRole('menu')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('explains that it changes the app language', () => {
    renderSwitcher()
    fireEvent.click(screen.getByRole('button', { name: /Language/ }))
    expect(screen.getByText(/Changes the app language and page direction/)).toBeInTheDocument()
  })
})
