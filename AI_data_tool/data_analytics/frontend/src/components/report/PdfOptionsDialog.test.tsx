import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import PdfOptionsDialog from './PdfOptionsDialog'

describe('PdfOptionsDialog', () => {
  it('hands back paper, orientation, contents and the chosen pages', () => {
    const onDownload = vi.fn()
    render(<PdfOptionsDialog pages={[{ id: 1, name: 'Overview' }, { id: 2, name: 'Detail' }]} onDownload={onDownload} onClose={() => {}} />)
    fireEvent.change(screen.getByLabelText('Paper'), { target: { value: 'Letter' } })
    fireEvent.click(screen.getByLabelText('Portrait'))
    fireEvent.click(screen.getByLabelText('Contents page'))
    fireEvent.click(screen.getByLabelText('Detail'))
    fireEvent.click(screen.getByRole('button', { name: 'Download' }))
    expect(onDownload).toHaveBeenCalledWith({ paper: 'Letter', orientation: 'portrait', contents: false, pages: [1] })
  })
  it('will not download zero pages', () => {
    render(<PdfOptionsDialog pages={[{ id: 1, name: 'A' }, { id: 2, name: 'B' }]} onDownload={vi.fn()} onClose={() => {}} />)
    fireEvent.click(screen.getByLabelText('A')); fireEvent.click(screen.getByLabelText('B'))
    expect((screen.getByRole('button', { name: 'Download' }) as HTMLButtonElement).disabled).toBe(true)
  })
})
