/**
 * "Clean lists for newcomers" (4.7): every dataset picker offers All /
 * Certified / Mine, and test-looking leftovers ("13", "kjhkjhkjh",
 * "claude job check") are out of sight until asked for.
 */
import type { Dataset } from '../services/api'
import { looksLikeTestData } from './testData'

export type DatasetView = 'all' | 'certified' | 'mine'

type Meta = Record<string, unknown> | undefined
export const certificationOf = (d: Pick<Dataset, 'column_meta'>) =>
  ((d.column_meta as unknown as Meta)?.['__certified__'] ?? null) as
    { by?: number; by_email?: string; at?: string; note?: string | null } | null

export const isCertified = (d: Pick<Dataset, 'column_meta'>) => certificationOf(d) != null

export function cleanDatasets<T extends Pick<Dataset, 'name' | 'column_meta'> & { created_by?: number | null }>(
  list: T[], view: DatasetView, userId: number | null | undefined, showTest: boolean,
): { visible: T[]; hiddenTest: number; certified: number; mine: number } {
  const certified = list.filter(isCertified).length
  const mine = userId == null ? 0 : list.filter(d => d.created_by === userId).length
  let visible = list
  if (view === 'certified') visible = visible.filter(isCertified)
  else if (view === 'mine') visible = visible.filter(d => userId != null && d.created_by === userId)
  // A certified dataset is never hidden as "test data", whatever it is called.
  const test = visible.filter(d => !isCertified(d) && looksLikeTestData(d.name))
  if (!showTest) visible = visible.filter(d => isCertified(d) || !looksLikeTestData(d.name))
  // Certified first: the ones to use are the ones to see.
  visible = [...visible].sort((a, b) => Number(isCertified(b)) - Number(isCertified(a)))
  return { visible, hiddenTest: showTest ? 0 : test.length, certified, mine }
}
