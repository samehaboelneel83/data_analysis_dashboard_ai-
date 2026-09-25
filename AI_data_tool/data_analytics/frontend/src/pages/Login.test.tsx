import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, within } from '@testing-library/react'
import Login, { signInErrorKey } from './Login'
import { DirectionProvider } from '../contexts/DirectionContext'

/**
 * The sign-in page is a UI shell around AuthContext.login -- these pin the
 * shell: inline validation in plain words, no double submit, friendly
 * errors, the reveal toggle, and that Arabic gets its own strings. The
 * request itself (cookie session, T6) is AuthContext's and is not touched.
 */

const login = vi.fn()
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: null, login }),
}))
const discover = vi.fn()
vi.mock('../services/api', () => ({
  ssoApi: { discover: (...a: unknown[]) => discover(...a), loginUrl: () => '/sso' },
}))

const renderLogin = () => render(<DirectionProvider><Login /></DirectionProvider>)
const email = () => screen.getByLabelText('Email')
const password = () => screen.getByLabelText('Password')
const submit = () => screen.getByRole('button', { name: /^Sign In/ })

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})
afterEach(() => { document.documentElement.removeAttribute('data-theme') })

describe('Login', () => {
  it('labels both fields, offers SSO and says who creates accounts (no fake sign-up or reset flow)', () => {
    renderLogin()
    expect(screen.getByRole('heading', { level: 1, name: 'Welcome back' })).toBeInTheDocument()
    expect(email()).toHaveAttribute('placeholder', 'name@company.com')
    expect(password()).toHaveAttribute('type', 'password')
    expect(screen.getByRole('button', { name: 'Sign in with SSO' })).toBeInTheDocument()
    expect(screen.getByText(/Ask your workspace admin/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /sign up|forgot/i })).toBeNull()
    // Exactly one submit button: the reveal toggle and SSO must not submit the form.
    expect(document.querySelectorAll('button[type="submit"]')).toHaveLength(1)
  })

  it('an empty submit explains each missing field inline and sends nothing', () => {
    renderLogin()
    fireEvent.click(submit())
    expect(screen.getByText('Enter your email address.')).toBeInTheDocument()
    expect(screen.getByText('Enter your password.')).toBeInTheDocument()
    expect(email()).toHaveAttribute('aria-invalid', 'true')
    expect(email()).toHaveFocus()
    expect(login).not.toHaveBeenCalled()
  })

  it('checks the email shape once the field is left, and clears the message when fixed', () => {
    renderLogin()
    fireEvent.change(email(), { target: { value: 'sara' } })
    fireEvent.blur(email())
    expect(screen.getByText(/Enter a full email address/)).toBeInTheDocument()
    fireEvent.change(email(), { target: { value: 'sara@datalytics.local' } })
    expect(screen.queryByText(/Enter a full email address/)).toBeNull()
  })

  it('shows and hides the password', () => {
    renderLogin()
    const toggle = screen.getByRole('button', { name: 'Show password' })
    fireEvent.click(toggle)
    expect(password()).toHaveAttribute('type', 'text')
    expect(screen.getByRole('button', { name: 'Hide password' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('submits once however fast it is clicked, with a busy button meanwhile', async () => {
    let finish!: () => void
    login.mockImplementation(() => new Promise<void>(r => { finish = r }))
    renderLogin()
    fireEvent.change(email(), { target: { value: 'a@b.co' } })
    fireEvent.change(password(), { target: { value: 'pw' } })
    const form = email().closest('form')!
    fireEvent.submit(form)
    fireEvent.submit(form)
    expect(login).toHaveBeenCalledTimes(1)
    expect(login).toHaveBeenCalledWith('a@b.co', 'pw')
    const busy = screen.getByRole('button', { name: /Signing in/ })
    expect(busy).toBeDisabled()
    await act(async () => { finish() })
  })

  it('turns a rejected sign-in into a plain-language alert', async () => {
    login.mockRejectedValue({ response: { status: 401 } })
    renderLogin()
    fireEvent.change(email(), { target: { value: 'a@b.co' } })
    fireEvent.change(password(), { target: { value: 'nope' } })
    await act(async () => { fireEvent.click(submit()) })
    expect(screen.getByRole('alert')).toHaveTextContent("That email and password don't match")
  })

  it('names network, server and rate-limit failures differently', () => {
    expect(signInErrorKey(new Error('Network Error'))).toBe('login.err.network')
    expect(signInErrorKey({ response: { status: 503 } })).toBe('login.err.server')
    expect(signInErrorKey({ response: { status: 429 } })).toBe('login.err.tooMany')
    expect(signInErrorKey({ response: { status: 422 } })).toBe('login.err.emailInvalid')
  })

  it('SSO asks for the email first instead of starting blind', async () => {
    renderLogin()
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Sign in with SSO' })) })
    expect(screen.getByRole('alert')).toHaveTextContent('Enter your email first')
    expect(discover).not.toHaveBeenCalled()
  })

  it('the brand panel explains the product with an accessible picture', () => {
    renderLogin()
    const panel = screen.getByRole('complementary', { name: 'About Datalytics' })
    expect(within(panel).getByRole('img', { name: /How Datalytics works/ })).toBeInTheDocument()
    expect(within(panel).getByText(/Connect any data\. Ask in plain language\./)).toBeInTheDocument()
  })

  it('under reduced motion the KPI shows its final number, not a count', () => {
    const mm = window.matchMedia
    window.matchMedia = ((q: string) => ({ ...mm(q), matches: q.includes('reduce') })) as typeof window.matchMedia
    try {
      renderLogin()
      const panel = screen.getByRole('complementary', { name: 'About Datalytics' })
      expect(within(panel).getByText('2,480,000')).toBeInTheDocument()
    } finally { window.matchMedia = mm }
  })

  it('Arabic: every string comes from the Arabic catalogue', () => {
    localStorage.setItem('datalytics.language', 'ar')
    localStorage.setItem('datalytics.direction', 'rtl')
    renderLogin()
    expect(screen.getByRole('heading', { level: 1, name: 'مرحبًا بعودتك' })).toBeInTheDocument()
    expect(screen.getByLabelText('كلمة المرور')).toHaveAttribute('placeholder', 'أدخل كلمة المرور')
    expect(screen.getByRole('button', { name: 'إظهار كلمة المرور' })).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: 'عن داتاليتكس' })).toBeInTheDocument()
  })

  it('the theme switch writes the same key and attribute the shell uses', () => {
    renderLogin()
    fireEvent.click(screen.getByRole('button', { name: 'Switch to dark mode' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(localStorage.getItem('theme')).toBe('dark')
  })
})
