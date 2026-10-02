import { describe, it, expect } from 'vitest'
import { xAxisProps, yAxisProps } from './axisOptions'

describe('axis_ticks: false — axes named, no tick labels', () => {
  it('drops the tick labels but keeps the axis names', () => {
    const cfg = { axis_ticks: false, x_axis_label: 'Service', y_axis_label: 'Total volume' } as never
    const x = xAxisProps(cfg, false, ['GPRS Basic Service', 'Mobile Telephony'], 300)
    const y = yAxisProps(cfg, false, undefined, [1, 2])
    expect(x.tick).toBe(false)
    expect(y.tick).toBe(false)
    expect(x.label).toBeTruthy()
    expect(y.label).toBeTruthy()
    // The tick band is gone, so the plot gets the room.
    expect(x.height).toBeLessThan(40)
  })

  it('changes nothing for a chart that does not ask', () => {
    const x = xAxisProps({} as never, false, ['a', 'b'], 300)
    expect(x.tick).not.toBe(false)
  })
})

import { labelListProps } from './axisOptions'

describe('axis_tick_max_chars — long category names shortened', () => {
  it('ends a long name with … and leaves short ones alone', () => {
    const x = xAxisProps({ axis_tick_max_chars: 12 } as never, false, ['GPRS Basic Service', 'USSD'], 300)
    const f = (x as { tickFormatter: (v: unknown) => string }).tickFormatter
    expect(f('GPRS Basic Service')).toBe('GPRS Basic …')
    expect(f('USSD')).toBe('USSD')
    expect(x.tick).not.toBe(false)
  })
})

describe('labels_compact — value labels written short', () => {
  it('writes 4,470,087,681 as 4.47B, small numbers as they are', () => {
    const p = labelListProps({ data_labels: true, labels_compact: true } as never)!
    expect(p.valueAccessor({ value: 4470087681 } as never, 0)).toBe('4.47B')
    expect(p.valueAccessor({ value: 614340 } as never, 0)).toBe('614.34K')
    expect(p.valueAccessor({ value: 135 } as never, 0)).toBe('135')
  })
})

import { valueTick } from './axisOptions'

describe('labels_compact — the value axis too', () => {
  it('writes 6,000,000,000 as 6B and keeps a narrow gutter', () => {
    const f = valueTick({ labels_compact: true } as never)
    expect([f(6000000000), f(1500000000), f(250), f(0)]).toEqual(['6B', '1.5B', '250', '0'])
    expect(yAxisProps({ labels_compact: true } as never, false, undefined, [6000000000]).width).toBeLessThanOrEqual(44)
  })
  it('compacts an ordinary chart\'s axis only from millions up, and only unless told not to', () => {
    // Was "leaves it as it was": "6,000,000,000" on a small tile's axis was
    // found unreadable in the HR re-test, so millions now compact by default.
    expect(valueTick({} as never)(6000000000)).toBe('6B')
    expect(valueTick({} as never)(45000)).not.toBe('45K')
    expect(valueTick({ labels_compact: false } as never)(6000000000)).not.toBe('6B')
  })
})
