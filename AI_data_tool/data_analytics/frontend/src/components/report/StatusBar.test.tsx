import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import StatusBar from './StatusBar'

describe('StatusBar', () => {
  it('shows page position', () => {
    render(<StatusBar pageIndex={1} pageCount={4} saveState="saved" />)
    expect(screen.getByText('Page 2 of 4')).toBeInTheDocument()
  })

  it('shows Saved when saveState is saved', () => {
    render(<StatusBar pageIndex={0} pageCount={1} saveState="saved" />)
    expect(screen.getByText('Saved')).toBeInTheDocument()
  })

  it('shows Saving… when saveState is saving', () => {
    render(<StatusBar pageIndex={0} pageCount={1} saveState="saving" />)
    expect(screen.getByText('Saving…')).toBeInTheDocument()
  })

  it('shows the zoom percentage and steps it up/down within bounds', () => {
    const onZoomChange = vi.fn()
    render(<StatusBar pageIndex={0} pageCount={1} saveState="saved" zoom={100} onZoomChange={onZoomChange} />)
    expect(screen.getByText('100%')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '+' }))
    expect(onZoomChange).toHaveBeenCalledWith(110)

    fireEvent.click(screen.getByRole('button', { name: '−' }))
    expect(onZoomChange).toHaveBeenCalledWith(90)
  })

  it('clamps zoom to the 50-150 range', () => {
    const onZoomChange = vi.fn()
    const { rerender } = render(<StatusBar pageIndex={0} pageCount={1} saveState="saved" zoom={150} onZoomChange={onZoomChange} />)
    fireEvent.click(screen.getByRole('button', { name: '+' }))
    expect(onZoomChange).toHaveBeenCalledWith(150)

    rerender(<StatusBar pageIndex={0} pageCount={1} saveState="saved" zoom={50} onZoomChange={onZoomChange} />)
    fireEvent.click(screen.getByRole('button', { name: '−' }))
    expect(onZoomChange).toHaveBeenCalledWith(50)
  })

  it('omits the zoom control when zoom/onZoomChange are not provided', () => {
    render(<StatusBar pageIndex={0} pageCount={1} saveState="saved" />)
    expect(screen.queryByRole('button', { name: '+' })).not.toBeInTheDocument()
  })
})
