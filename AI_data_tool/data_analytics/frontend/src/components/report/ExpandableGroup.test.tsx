import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ExpandableGroup from './ExpandableGroup'

beforeEach(() => localStorage.clear())

describe('ExpandableGroup', () => {
  it('renders its children when open', () => {
    render(<ExpandableGroup id="roles" title="Roles" defaultOpen><p>inner</p></ExpandableGroup>)
    expect(screen.getByText('inner')).toBeInTheDocument()
  })

  it('hides its children when collapsed, and the header stays visible', () => {
    render(<ExpandableGroup id="roles" title="Roles" defaultOpen={false}><p>inner</p></ExpandableGroup>)
    expect(screen.queryByText('inner')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Roles/i })).toBeInTheDocument()
  })

  it('toggles on click', () => {
    render(<ExpandableGroup id="roles" title="Roles" defaultOpen={false}><p>inner</p></ExpandableGroup>)
    fireEvent.click(screen.getByRole('button', { name: /Roles/i }))
    expect(screen.getByText('inner')).toBeInTheDocument()
  })

  it('exposes its state to assistive tech via aria-expanded', () => {
    render(<ExpandableGroup id="roles" title="Roles" defaultOpen={false}><p>inner</p></ExpandableGroup>)
    const header = screen.getByRole('button', { name: /Roles/i })
    expect(header).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(header)
    expect(header).toHaveAttribute('aria-expanded', 'true')
  })

  it('persists its state so the author is not re-opening the same group every time', () => {
    const { unmount } = render(<ExpandableGroup id="sorting" title="Sorting" defaultOpen={false}><p>inner</p></ExpandableGroup>)
    fireEvent.click(screen.getByRole('button', { name: /Sorting/i }))
    unmount()

    render(<ExpandableGroup id="sorting" title="Sorting" defaultOpen={false}><p>inner</p></ExpandableGroup>)
    expect(screen.getByText('inner')).toBeInTheDocument()
  })

  it('keeps each group independent', () => {
    render(
      <>
        <ExpandableGroup id="a" title="Group A" defaultOpen={false}><p>a-inner</p></ExpandableGroup>
        <ExpandableGroup id="b" title="Group B" defaultOpen={false}><p>b-inner</p></ExpandableGroup>
      </>
    )
    fireEvent.click(screen.getByRole('button', { name: /Group A/i }))
    expect(screen.getByText('a-inner')).toBeInTheDocument()
    expect(screen.queryByText('b-inner')).not.toBeInTheDocument()
  })

  it('survives unreadable storage rather than failing to render', () => {
    localStorage.setItem('datalytics.panelGroups', 'not json')
    render(<ExpandableGroup id="roles" title="Roles" defaultOpen><p>inner</p></ExpandableGroup>)
    expect(screen.getByText('inner')).toBeInTheDocument()
  })

  it('forceOpen shows children of a collapsed group without persisting the open state', () => {
    render(<ExpandableGroup id="roles" title="Roles" defaultOpen={false} forceOpen><p>inner</p></ExpandableGroup>)
    expect(screen.getByText('inner')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Roles/i })).toHaveAttribute('aria-expanded', 'true')
    expect(localStorage.getItem('datalytics.panelGroups')).toBeNull()
  })

  it('forceOpen going away reverts to the real (still-collapsed) stored state', () => {
    const { rerender } = render(<ExpandableGroup id="roles" title="Roles" defaultOpen={false} forceOpen><p>inner</p></ExpandableGroup>)
    expect(screen.getByText('inner')).toBeInTheDocument()
    rerender(<ExpandableGroup id="roles" title="Roles" defaultOpen={false}><p>inner</p></ExpandableGroup>)
    expect(screen.queryByText('inner')).not.toBeInTheDocument()
  })

  it('a header click during forceOpen is a no-op: no storage write, no state flip', () => {
    render(<ExpandableGroup id="roles" title="Roles" defaultOpen={false} forceOpen><p>inner</p></ExpandableGroup>)
    fireEvent.click(screen.getByRole('button', { name: /Roles/i }))
    expect(screen.getByText('inner')).toBeInTheDocument()
    expect(localStorage.getItem('datalytics.panelGroups')).toBeNull()
  })

  it('hidden unmounts the whole group, header included', () => {
    render(<ExpandableGroup id="roles" title="Roles" defaultOpen hidden><p>inner</p></ExpandableGroup>)
    expect(screen.queryByText('inner')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Roles/i })).not.toBeInTheDocument()
  })
})
