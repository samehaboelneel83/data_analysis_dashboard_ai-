import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Database } from 'lucide-react'
import EmptyState from './EmptyState'

describe('EmptyState', () => {
  it('shows the icon, title, and description', () => {
    render(<EmptyState icon={Database} title="No datasets yet" description="Upload a file to get started." />)
    expect(screen.getByText('No datasets yet')).toBeInTheDocument()
    expect(screen.getByText('Upload a file to get started.')).toBeInTheDocument()
  })

  it('renders as a card, matching every existing page empty-state', () => {
    const { container } = render(<EmptyState icon={Database} title="No datasets yet" />)
    expect(container.firstElementChild).toHaveClass('card')
  })

  it('renders no description paragraph when none is given', () => {
    render(<EmptyState icon={Database} title="No connections yet" />)
    expect(screen.getByText('No connections yet')).toBeInTheDocument()
    // Only the title paragraph exists -- no empty second <p>.
    expect(document.querySelectorAll('p')).toHaveLength(1)
  })

  it('renders an action slot when given one, and fires its own handler', () => {
    const onClick = vi.fn()
    render(
      <EmptyState icon={Database} title="No datasets yet"
        action={<button onClick={onClick}>Upload your first dataset</button>} />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Upload your first dataset' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('renders no action row when none is given', () => {
    render(<EmptyState icon={Database} title="No connections yet" />)
    expect(screen.queryByRole('button')).toBeNull()
  })
})
