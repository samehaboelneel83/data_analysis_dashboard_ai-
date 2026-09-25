import { describe, it, expect } from 'vitest'
import { looksLikeTestData } from './testData'

describe('looksLikeTestData', () => {
  it.each(['qa_sample', 'qa_sampleQA Sample Append 1', 'test', 'Test 3', 'tmp_orders', 'Untitled dashboard 4',
    'Sales (copy)', 'Copy of revenue', 'debug-run'])('flags %s', n => expect(looksLikeTestData(n)).toBe(true))
  it.each(['Sales — Global', 'Testimonials', 'Customer churn', 'Attestation log', 'Temperature readings', 'Samples by lab'])(
    'leaves %s alone', n => expect(looksLikeTestData(n)).toBe(false))
})
