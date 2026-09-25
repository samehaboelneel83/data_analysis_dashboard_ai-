import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import LoadError from './LoadError'
import ErrorBoundary from './ErrorBoundary'
import { detailToText } from '../../lib/friendlyError'

describe('LoadError never hands React an object', () => {
  it('renders a FastAPI 422 detail array as one sentence (it used to crash the app)', () => {
    const error = { response: { status: 422, data: { detail: [{ type: 'int_parsing', loc: ['path', 'dataset_id'], msg: 'Input should be a valid integer', input: 'NaN' }] } } }
    render(<LoadError what="this dataset" error={error} onRetry={() => {}} />)
    expect(screen.getByRole('alert')).toHaveTextContent('dataset_id: Input should be a valid integer')
  })
  it('offers Go back instead of Try again for a 404', () => {
    render(<LoadError what="this report" error={{ response: { status: 404, data: { detail: 'Report not found' } } }} onRetry={() => {}} />)
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Go back' })).toBeInTheDocument()
  })
})

describe('detailToText', () => {
  it('handles strings, arrays and objects', () => {
    expect(detailToText('x')).toBe('x')
    expect(detailToText({ message: 'm' })).toBe('m')
    expect(detailToText([{ msg: 'a', loc: ['body', 'name'] }])).toBe('Invalid request — name: a')
  })
})

describe('ErrorBoundary', () => {
  it('contains a render error instead of blanking the app', () => {
    const Boom = () => { throw new Error('kaboom') }
    const spy = console.error; console.error = () => {}
    render(<div><p>shell</p><ErrorBoundary><Boom /></ErrorBoundary></div>)
    console.error = spy
    expect(screen.getByText('shell')).toBeInTheDocument()
    expect(screen.getByText('Something went wrong on this page')).toBeInTheDocument()
  })
})
