import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ExpressionBuilder from './ExpressionBuilder'
import type { DatasetColumn } from '../../services/api'

const columns: DatasetColumn[] = [
  { id: 1, name: 'owner', dtype: 'categorical', missing_pct: 0, stats: {} },
]

describe('ExpressionBuilder', () => {
  it('always offers a System group with the user/org tokens', () => {
    render(<ExpressionBuilder columns={columns} functionsCatalog={[]} value="" onChange={vi.fn()} />)
    expect(screen.getByText('System')).toBeInTheDocument()
    for (const label of ['USEREMAIL()', 'USERID()', 'ORGID()', 'ORGNAME()']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }
  })

  it('inserts USEREMAIL() into the expression', () => {
    const onChange = vi.fn()
    render(<ExpressionBuilder columns={columns} functionsCatalog={[]} value="owner == " onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: 'USEREMAIL()' }))

    expect(onChange.mock.calls[0][0]).toContain('USEREMAIL()')
  })

  it('inserts a column reference', () => {
    const onChange = vi.fn()
    render(<ExpressionBuilder columns={columns} functionsCatalog={[]} value="" onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /owner/ }))

    expect(onChange).toHaveBeenCalledWith('owner')
  })

  it('calls onTest and renders the result via renderTestResult', async () => {
    const onTest = vi.fn().mockResolvedValue({ ok: true })
    render(
      <ExpressionBuilder
        columns={columns} functionsCatalog={[]} value="owner == USEREMAIL()" onChange={vi.fn()}
        onTest={onTest} renderTestResult={r => <div>result: {(r as { ok: boolean }).ok ? 'valid' : 'invalid'}</div>}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Test' }))

    expect(onTest).toHaveBeenCalledWith('owner == USEREMAIL()')
    expect(await screen.findByText('result: valid')).toBeInTheDocument()
  })
})

describe('ExpressionBuilder — Simple mode (C2)', () => {
  function Harness({ initialValue = '', defaultMode = 'simple' as const }) {
    const [value, setValue] = useState(initialValue)
    return <ExpressionBuilder columns={columns} functionsCatalog={[]} value={value} onChange={setValue} defaultMode={defaultMode} />
  }

  it('defaults to advanced when not told otherwise', () => {
    render(<ExpressionBuilder columns={columns} functionsCatalog={[]} value="owner == 1" onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Advanced' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('a literal condition row compiles to the expected text', () => {
    render(<Harness />)
    fireEvent.change(screen.getByLabelText('Value'), { target: { value: 'North' } })
    expect(screen.getByText('owner == "North"')).toBeInTheDocument()
  })

  it('a system-parameter row compiles USEREMAIL() unquoted', () => {
    render(<Harness />)
    fireEvent.change(screen.getByLabelText('Value type'), { target: { value: 'system' } })
    fireEvent.change(screen.getByLabelText('Value'), { target: { value: 'USEREMAIL()' } })
    expect(screen.getByText('owner == USEREMAIL()')).toBeInTheDocument()
  })

  it('joins two condition rows with the chosen operator', () => {
    render(<Harness />)
    fireEvent.change(screen.getByLabelText('Value'), { target: { value: 'North' } })
    fireEvent.click(screen.getByRole('button', { name: '+ Condition' }))
    const values = screen.getAllByLabelText('Value')
    fireEvent.change(values[1], { target: { value: 'South' } })
    fireEvent.change(screen.getByLabelText('Join with'), { target: { value: 'or' } })
    expect(screen.getByText('owner == "North" or owner == "South"')).toBeInTheDocument()
  })

  it('Simple → Advanced hands over the compiled text verbatim', () => {
    render(<Harness />)
    fireEvent.change(screen.getByLabelText('Value'), { target: { value: 'North' } })
    fireEvent.click(screen.getByRole('button', { name: 'Advanced' }))
    expect(screen.getByRole('textbox')).toHaveValue('owner == "North"')
  })

  it('round-trips a builder-generated expression back to Simple', () => {
    render(<Harness />)
    fireEvent.change(screen.getByLabelText('Value'), { target: { value: 'North' } })
    fireEvent.click(screen.getByRole('button', { name: 'Advanced' }))
    fireEvent.click(screen.getByRole('button', { name: 'Simple' }))
    expect(screen.getByLabelText('Value')).toHaveValue('North')
  })

  it('a hand-written expression shows the fallback with a Start over button', () => {
    render(<Harness initialValue="owner == 'hand written'" defaultMode="simple" />)
    expect(screen.getByText(/hand-written expression/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Value')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Start over' }))
    expect(screen.getByLabelText('Column')).toBeInTheDocument()
  })
})
