import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WidgetBody } from './WidgetBody'
import type { Widget } from '../../types/report'

/**
 * QA E-12 / SEC-02: a tile whose measure reads a column the reader's role may
 * not see showed "Unknown column or function in measure expression: name 'cost'
 * is not defined" -- a broken-looking dashboard that also names the hidden
 * column. The server now refuses it with `forbidden_column`; the tile says so
 * in plain words.
 */
const widget = {
  id: 1, widget_type: 'bar', title: 'Margin % by region',
  config: { dimension: 'region', measure: 'Margin %' },
} as unknown as Widget

const renderBody = (props: Partial<Parameters<typeof WidgetBody>[0]>) => render(
  <WidgetBody widget={widget} data={null} localSelected={null} onClickPoint={vi.fn()} broadcasts={false} {...props} />)

describe('WidgetBody — restricted data', () => {
  it('a forbidden_column refusal reads as restricted, with no retry and no column name', () => {
    const onRetry = vi.fn()
    renderBody({ fetchError: { detail: 'This widget references a column your role cannot access', code: 'forbidden_column' }, onRetry })
    expect(screen.getByText("This tile uses data your role can't see.")).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('a measure_error is a generic sentence for a reader, and the raw reason for an editor', () => {
    const data = { type: 'error', code: 'measure_error', message: "Unknown column or function in measure expression: name 'cost' is not defined", rows: [] }
    const { unmount } = renderBody({ data })
    expect(screen.getByText('This measure could not be calculated.')).toBeInTheDocument()
    expect(screen.queryByText(/cost/)).not.toBeInTheDocument()
    unmount()
    renderBody({ data, onAssignData: vi.fn() })
    expect(screen.getByText(/name 'cost' is not defined/)).toBeInTheDocument()
  })
})
