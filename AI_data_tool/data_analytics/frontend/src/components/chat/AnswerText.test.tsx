import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import AnswerText from './AnswerText'
import type { AnswerEvidence } from '../../services/api'

/**
 * Redesign step 1a-1c: the model's markdown renders, long floats are rounded
 * for reading, and the paragraph takes the direction of its majority script --
 * all without moving the traced numbers' offsets, which count the RAW text.
 */
describe('AnswerText markup (1a)', () => {
  it('renders **faculty** bold, with no asterisks', () => {
    render(<AnswerText text="Grouped by **faculty** as asked." />)
    const p = screen.getByTestId('answer-text')
    expect(p.querySelector('strong')).toHaveTextContent('faculty')
    expect(p).toHaveTextContent('Grouped by faculty as asked.')
    expect(p.textContent).not.toContain('*')
  })

  it('keeps a traced number inside bold a button, shown bold', () => {
    const text = 'Medicine is highest at **83.88833333333332** on average.'
    const start = text.indexOf('83.')
    const evidence: AnswerEvidence = { untraced: 0, claims: [{
      start, end: start + '83.88833333333332'.length, text: '83.88833333333332', status: 'traced',
      source: { result: 0, row: 0, column: 'avg', value: 83.88833333333332, kind: 'cell' } }] }
    const onShow = vi.fn()
    render(<AnswerText text={text} evidence={evidence} onShow={onShow} />)
    const btn = screen.getByRole('button', { name: /^83\.9: / })
    expect(btn).toHaveTextContent('83.9')
    expect(btn.closest('strong')).not.toBeNull()
    btn.click()
    expect(onShow).toHaveBeenCalledWith(expect.objectContaining({ text: '83.88833333333332' }))
  })

  it('renders links only for https://', () => {
    render(<AnswerText text={'See [docs](https://example.com/a), [old](http://example.com/b) and [x](javascript:alert(1)).'} />)
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(1)
    expect(links[0]).toHaveAttribute('href', 'https://example.com/a')
    expect(screen.getByTestId('answer-text')).toHaveTextContent('[old](http://example.com/b)')
  })
})

describe('AnswerText numbers (1b)', () => {
  it('rounds a long float at render time only', () => {
    render(<AnswerText text="Arts averages 61.53500000000001 and 2025 is the year." />)
    const p = screen.getByTestId('answer-text')
    expect(p).toHaveTextContent('Arts averages 61.5 and 2025 is the year.')
  })
})

describe('AnswerText direction (1c)', () => {
  it('lays out an Arabic answer RTL even when it starts with a data value', () => {
    render(<AnswerText text="Medicine الأعلى بمتوسط 83.9 نقطة" />)
    expect(screen.getByTestId('answer-text')).toHaveAttribute('dir', 'rtl')
  })

  it('lays out an English answer LTR', () => {
    render(<AnswerText text="Arts is lowest" />)
    expect(screen.getByTestId('answer-text')).toHaveAttribute('dir', 'ltr')
  })
})
