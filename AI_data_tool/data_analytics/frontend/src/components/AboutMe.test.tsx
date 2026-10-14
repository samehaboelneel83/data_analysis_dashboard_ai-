import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import AboutMe from './AboutMe'
import { AuthContext } from '../contexts/AuthContext'

const updateMe = vi.fn()
vi.mock('../services/api', () => ({ authApi: { updateMe: (b: unknown) => updateMe(b) } }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const show = (about: string | null) => render(
  <AuthContext.Provider value={{ user: { id: 1, email: 'a@b', about } as never, loading: false, login: vi.fn(), logout: vi.fn() } as never}>
    <AboutMe />
  </AuthContext.Provider>)

describe('what a person says about themselves', () => {
  beforeEach(() => updateMe.mockReset())

  it('says whether one is saved, and saves what is written to the profile', async () => {
    updateMe.mockResolvedValue({ about: 'I plan the routes' })
    show(null)
    expect(screen.getByTestId('about-me').textContent).toContain('nothing saved yet')
    const box = screen.getByLabelText(/Your work and what you look at data for/) as HTMLTextAreaElement
    const save = screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement
    expect(save.disabled).toBe(true)                               // nothing changed yet
    fireEvent.change(box, { target: { value: '  I plan the routes ' } })
    fireEvent.click(save)
    await waitFor(() => expect(updateMe).toHaveBeenCalledWith({ about: 'I plan the routes' }))
    await waitFor(() => expect(screen.getByTestId('about-me').textContent).toContain('saved on your profile'))
  })

  it('shows the saved one and clears it when emptied', async () => {
    updateMe.mockResolvedValue({ about: null })
    show('I plan the routes')
    const box = screen.getByLabelText(/Your work and what you look at data for/) as HTMLTextAreaElement
    expect(box.value).toBe('I plan the routes')
    fireEvent.change(box, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(updateMe).toHaveBeenCalledWith({ about: '' }))
    await waitFor(() => expect(screen.getByTestId('about-me').textContent).toContain('nothing saved yet'))
  })
})
