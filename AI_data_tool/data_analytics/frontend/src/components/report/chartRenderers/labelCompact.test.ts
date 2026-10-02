import { describe, expect, it } from 'vitest'
import { labelListProps } from './axisOptions'

const label = (cfg: Record<string, unknown>, v: number, n = 3) =>
  labelListProps({ data_labels: true, ...cfg } as never, undefined, 'value', n)!.valueAccessor({ value: v }, 0)

describe('value labels go compact when they would collide (5.11)', () => {
  it('a billion-sized label reads 1.73B by default', () => {
    expect(label({}, 1_733_412_880)).toBe('1.73B')
  })
  it('many points of five-digit values go compact too', () => {
    expect(label({}, 45_000, 12)).toBe('45K')
  })
  it('a few small labels keep their digits, and an explicit choice wins', () => {
    expect(label({}, 45_000, 3)).not.toBe('45K')
    expect(label({ labels_compact: false }, 1_733_412_880)).not.toBe('1.73B')
  })
})

describe('value axis ticks (Chrome re-test)', () => {
  it('compacts millions by default, keeps smaller ticks, and respects an explicit no', async () => {
    const { valueTick } = await import('./axisOptions')
    expect(valueTick({} as never)(6_000_000_000)).toBe('6B')
    expect(valueTick({} as never)(45_000)).not.toBe('45K')
    expect(valueTick({ labels_compact: false } as never)(6_000_000_000)).not.toBe('6B')
  })
})
