import { describe, it, expect } from 'vitest'
import { compileCondition } from './displayRules'

describe('compileCondition', () => {
  it('compiles comparison operators against a plain column', () => {
    expect(compileCondition('value', { op: 'gt', value: 1000 })).toBe('value > 1000')
    expect(compileCondition('value', { op: 'gte', value: 1000 })).toBe('value >= 1000')
    expect(compileCondition('value', { op: 'lt', value: 10 })).toBe('value < 10')
    expect(compileCondition('value', { op: 'lte', value: 10 })).toBe('value <= 10')
    expect(compileCondition('value', { op: 'eq', value: 10 })).toBe('value == 10')
    expect(compileCondition('value', { op: 'ne', value: 10 })).toBe('value != 10')
  })

  it('quotes string operands with double quotes', () => {
    expect(compileCondition('name', { op: 'eq', value: 'US' })).toBe('name == "US"')
  })

  it('backtick-quotes column names that are not bare identifiers', () => {
    expect(compileCondition('net sales', { op: 'gt', value: 1 })).toBe('`net sales` > 1')
  })

  it('compiles between to an inclusive pair', () => {
    expect(compileCondition('value', { op: 'between', value: 10, value2: 20 }))
      .toBe('(value >= 10) and (value <= 20)')
  })

  it('compiles in to a list membership test', () => {
    expect(compileCondition('name', { op: 'in', value: ['US', 'CA'] }))
      .toBe('name in ["US", "CA"]')
  })

  it('compiles null checks without using `not`, which is ambiguous on a Series', () => {
    expect(compileCondition('value', { op: 'isnull' })).toBe('isnull(value) == True')
    expect(compileCondition('value', { op: 'notnull' })).toBe('isnull(value) == False')
  })

  it('escapes embedded double quotes rather than emitting broken syntax', () => {
    expect(compileCondition('name', { op: 'eq', value: 'a"b' })).toBe('name == "a\\"b"')
  })

  it('compiles booleans as Python literals, not JavaScript ones', () => {
    // `active == true` passes the backend's AST allowlist (a bare name) and only fails
    // later as NameError, which display rules swallow — so the rule would silently never apply.
    expect(compileCondition('active', { op: 'eq', value: true })).toBe('active == True')
    expect(compileCondition('active', { op: 'eq', value: false })).toBe('active == False')
  })
})
