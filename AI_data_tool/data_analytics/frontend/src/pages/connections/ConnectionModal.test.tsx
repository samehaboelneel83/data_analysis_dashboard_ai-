import { describe, it, expect, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { renderWithProviders } from '../../test/renderWithProviders'
import { ConnectionModal } from './ConnectionModal'
import type { ConnectorSpec } from '../../services/api'

vi.mock('../../services/api', async (orig) => ({ ...(await orig<Record<string, unknown>>()) }))

const spec = (key: string, label: string, installed: boolean): ConnectorSpec => ({
  key, label, icon: '', category: 'Databases', default_port: null, driver_installed: installed,
  supports_directquery: true, config_fields: [],
}) as ConnectorSpec

describe('ConnectionModal type grid (B-23)', () => {
  const catalog = [spec('snowflake', 'Snowflake', false), spec('postgresql', 'PostgreSQL', true)]

  it('marks a type whose driver is not installed, after the ones that work', () => {
    renderWithProviders(<ConnectionModal catalog={catalog} onSave={vi.fn()} onClose={vi.fn()} />)
    const radios = within(screen.getByRole('radiogroup')).getAllByRole('radio')
    expect(radios.map(r => r.textContent)).toEqual([expect.stringContaining('PostgreSQL'), expect.stringContaining('Snowflake')])
    expect(radios[1]).toHaveTextContent('Driver not installed')
    expect(radios[0]).not.toHaveTextContent('Driver not installed')
  })

  it('can be chosen, but Create connection is off with the notice', () => {
    renderWithProviders(<ConnectionModal catalog={catalog} onSave={vi.fn()} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('radio', { name: /Snowflake/ }))
    fireEvent.click(screen.getByRole('button', { name: /Next/ }))
    expect(screen.getByRole('note')).toHaveTextContent('not installed')
    expect(screen.getByRole('button', { name: 'Create connection' })).toBeDisabled()
  })
})
