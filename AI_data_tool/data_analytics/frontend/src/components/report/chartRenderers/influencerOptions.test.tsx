import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import ModelRenderer, { chosenInfluencers, influencerFigure } from './ModelRenderer'
import { modelOptsConfig, seedModelOpts } from '../ModelSettings'

const influencers = [
  { factor: 'kind', group: 'A', value: 0.40, lift: 1.9, rows: 300, share_of_rows: 0.1 },
  { factor: 'place', group: 'North', value: 0.30, lift: 1.4, rows: 500, share_of_rows: 0.2 },
  { factor: 'kind', group: 'B', value: 0.10, lift: 0.5, rows: 400, share_of_rows: 0.15 },
  { factor: 'place', group: 'South', value: 0.26, lift: 1.2, rows: 250, share_of_rows: 0.1 },
]
const data = { type: 'model', status: 'ok', model: 'influencers', target: 'won', predictors: ['kind', 'place'], measure: 'rate',
  baseline: 0.21, influencers, result: { caveats: [] }, population: { rows_used: 1000, rows_total: 1000 },
  fit: { name: 'Overall rate', value: 0.21 }, value_format: 'percent' }
const draw = (cfg: Record<string, unknown>) => render(<ModelRenderer data={data as never} cfg={cfg as never} rows={[]}
  rtl={false} broadcasts={false} localSelected={null} onClickPoint={() => {}} />)

describe('key influencers: how they are shown', () => {
  it('keeps the bars and everything else when nothing is chosen', () => {
    draw({ response: 'won' })
    expect(screen.getAllByTestId('influencer')).toHaveLength(4)
    expect(screen.getByTestId('influencers').getAttribute('data-style')).toBeNull()
    expect((screen.getByTestId('model-header') as HTMLElement).style.display).toBe('flex')
  })

  it('draws bubbles that say how far from usual, only the direction asked for, only as many as asked', () => {
    draw({ response: 'won', influencer_style: 'bubbles', influencer_direction: 'higher', influencer_limit: 2 })
    expect(screen.getByTestId('influencers').getAttribute('data-style')).toBe('bubbles')
    expect(screen.getAllByTestId('influencer-bubble').map(b => b.textContent)).toEqual(['+90.0%', '+40.0%'])
  })

  it('lets the reader look the other way, and says when there is nothing there', () => {
    draw({ response: 'won', influencer_style: 'bubbles', influencer_direction: 'higher' })
    fireEvent.change(screen.getByTestId('influencer-direction'), { target: { value: 'lower' } })
    expect(screen.getAllByTestId('influencer-bubble').map(b => b.textContent)).toEqual(['−50.0%'])
    expect(chosenInfluencers(influencers.filter(r => r.lift >= 1), 'lower')).toEqual([])
  })

  it('shows only the influencers when the model lines are switched off', () => {
    draw({ response: 'won', influencer_details: false })
    expect((screen.getByTestId('model-header') as HTMLElement).style.display).toBe('none')
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(screen.getAllByTestId('influencer')).toHaveLength(4)
  })

  it('the settings write only what differs from the default, and read it back', () => {
    const cfg = modelOptsConfig('model_influencers', { influencer_style: 'bubbles', influencer_direction: 'higher', influencer_limit: 5, influencer_details: false })
    expect(cfg).toEqual({ influencer_style: 'bubbles', influencer_direction: 'higher', influencer_limit: 5, influencer_details: false })
    expect(seedModelOpts(cfg)).toEqual(cfg)
    expect(modelOptsConfig('model_influencers', { influencer_style: 'bars', influencer_direction: 'both' })).toEqual({})
  })

  it('writes the figure in the format and to the decimals chosen', () => {
    const r = influencers[0]
    expect(influencerFigure(r, true, 'change')).toBe('+90.0%')
    expect(influencerFigure(r, true, 'change', 0)).toBe('+90%')
    expect(influencerFigure(r, true, 'times')).toBe('1.90×')
    expect(influencerFigure(r, true, 'value', 2)).toBe('40.00%')
    expect(influencerFigure({ ...r, value: 1234.5 }, false, 'value')).toBe('1,235')
    draw({ response: 'won', influencer_style: 'bubbles', influencer_format: 'times', influencer_decimals: 1, influencer_limit: 1 })
    expect(screen.getByTestId('influencer-bubble').textContent).toBe('1.9×')
    expect(seedModelOpts(modelOptsConfig('model_influencers', { influencer_format: 'value', influencer_decimals: 0 })))
      .toEqual({ influencer_format: 'value', influencer_decimals: 0 })
  })
})
