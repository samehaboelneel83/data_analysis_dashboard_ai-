import { describe, it, expect, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import NotFound from './NotFound'
import { DirectionProvider } from '../contexts/DirectionContext'

/** QA5 R3: the path on the 404 page reads left to right in Arabic. */
describe('NotFound', () => {
  afterEach(() => { localStorage.clear() })
  const at = (lang: string) => {
    localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
    return render(<DirectionProvider><MemoryRouter initialEntries={['/activity']}><NotFound /></MemoryRouter></DirectionProvider>)
  }
  it('English: the path as typed', () => {
    at('en')
    expect(screen.getByText('Nothing lives at /activity. The link may be old or mistyped.')).toBeInTheDocument()
  })
  it('Arabic: the path isolated left-to-right, so its slash stays in front', () => {
    at('ar')
    expect(screen.getByText(/⁦\/activity⁩/)).toBeInTheDocument()
  })
})
