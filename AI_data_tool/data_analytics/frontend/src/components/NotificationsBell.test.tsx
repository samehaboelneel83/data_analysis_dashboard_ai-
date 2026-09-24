import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import NotificationsBell from './NotificationsBell'
import { notificationsApi } from '../services/api'

vi.mock('../services/api', () => ({
  notificationsApi: { list: vi.fn(), markRead: vi.fn() },
}))

const payload = {
  unread: 2,
  notifications: [
    { id: 1, kind: 'alert', text: 'Alert "Rev" is firing', link: null, created_at: '2026-08-23T10:00:00Z', read: false },
    { id: 2, kind: 'schedule', text: 'Delivery of "Weekly" had problems', link: '/reports/7', created_at: '2026-08-23T09:00:00Z', read: false },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(notificationsApi.list).mockResolvedValue(payload)
  vi.mocked(notificationsApi.markRead).mockResolvedValue({ marked: 2 })
})

describe('NotificationsBell', () => {
  it('shows the unread count and the items on open', async () => {
    render(<MemoryRouter><NotificationsBell /></MemoryRouter>)
    await waitFor(() => expect(screen.getByTestId('bell-unread')).toHaveTextContent('2'))
    fireEvent.click(screen.getByRole('button', { name: /Notifications/ }))
    expect(screen.getByText(/Alert "Rev" is firing/)).toBeInTheDocument()
    expect(screen.getByText(/Delivery of "Weekly"/)).toBeInTheDocument()
  })

  it('opening the bell marks everything read and clears the badge', async () => {
    render(<MemoryRouter><NotificationsBell /></MemoryRouter>)
    await screen.findByTestId('bell-unread')
    fireEvent.click(screen.getByRole('button', { name: /Notifications/ }))
    await waitFor(() => expect(notificationsApi.markRead).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByTestId('bell-unread')).not.toBeInTheDocument())
  })
})
