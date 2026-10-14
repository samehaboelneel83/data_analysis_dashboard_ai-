import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, columnMetaApi } from './api'

afterEach(() => vi.restoreAllMocks())

describe('columnMetaApi.set', () => {
  it('sends the columns and leaves the reserved keys of the dataset map at home', async () => {
    const put = vi.spyOn(api, 'put').mockResolvedValue({ data: {} } as never)
    await columnMetaApi.set(7, {
      region: { geo_level: 'city', class_source: 'confirmed' },
      __prep_steps__: [{ op: 'dedupe' }],
      __demo__: true,
    } as never)
    expect(put).toHaveBeenCalledWith('/datasets/7/column-meta', {
      meta: { region: { geo_level: 'city', class_source: 'confirmed' } },
    })
  })
})
