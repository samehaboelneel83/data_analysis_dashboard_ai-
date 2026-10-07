import { describe, expect, it } from 'vitest'
import { autoChart, groupedBars } from './ResultView'
import { answerToWidget } from './answerWidget'
import type { AgentResult } from '../../services/api'

const res = (columns: string[], rows: (string | number | null)[][]): AgentResult =>
  ({ step: 1, columns, rows, total: rows.length, truncated: false } as unknown as AgentResult)

const byTitleGender = res(['title', 'gender', 'avg_salary'], [
  ['Engineer', 'M', 59000], ['Engineer', 'F', 58800],
  ['Senior Staff', 'M', 80700], ['Senior Staff', 'F', 80600],
  ['Staff', 'M', 67300],
])

describe('two-dimension answers (3.8)', () => {
  it('pivots title x gender into a crosstab, one series per gender', () => {
    const g = groupedBars(byTitleGender)!
    expect(g.x).toBe('title')
    expect(g.series).toBe('gender')
    expect(g.y).toBe('avg_salary')
    expect(g.columns).toEqual(['title', 'M', 'F', 'Total'])
    expect(g.rows[2]).toEqual(['Staff', 67300, 0, 67300])
    expect(autoChart(byTitleGender)).toBe('bar')
  })

  it('leaves a one-label result alone', () => {
    expect(groupedBars(res(['dept', 'n'], [['A', 1], ['B', 2]]))).toBeNull()
  })

  it('does not group when every row is its own label (nothing to split)', () => {
    expect(groupedBars(res(['first', 'last', 'salary'], [['A', 'X', 1], ['B', 'Y', 2], ['C', 'Z', 3]]))).toBeNull()
  })

  it('adds to a dashboard as a bar split by the second label', () => {
    const w = answerToWidget(byTitleGender, ['SELECT title, gender, AVG(salary) AS avg_salary FROM t GROUP BY 1,2'],
      ['title', 'gender', 'salary'])
    expect(w).toEqual({ widget_type: 'bar', config: { dimension: 'title', dimension2: 'gender', measure: 'salary', aggregation: 'avg' } })
  })
})

describe('code and name together (Chrome re-test)', () => {
  it('labels the bars with the department name, not the code', async () => {
    const { chartColumns, chartRows } = await import('./ResultView')
    const r = res(['dept_no', 'dept_name', 'leaver_count'], [['d001', 'Marketing', 5369], ['d002', 'Finance', 4909]])
    expect(chartColumns(r).x).toBe('dept_name')
    expect(chartRows(r)[0]).toEqual({ name: 'Marketing', value: 5369 })
    expect(groupedBars(r)).toBeNull()
  })
})

describe('autoChart with numeric-looking labels (redesign 1d)', () => {
  it('charts faculty names against their average as bars', () => {
    expect(autoChart(res(['faculty', 'average_final_score'],
      [['Engineering', 61.53500000000001], ['Science', 70.2], ['Arts', 58.1], ['Law', 66.4]]))).toBe('bar')
  })

  it('charts faculty codes 1-4 as bars instead of falling back to the grid', () => {
    expect(autoChart(res(['faculty', 'average_final_score'],
      [[1, 61.5], [2, 70.2], [3, 58.1], [4, 66.4]]))).toBe('bar')
  })

  it('keeps the grid when the numeric first column repeats', () => {
    expect(autoChart(res(['faculty', 'score'], [[1, 61.5], [1, 70.2], [2, 58.1]]))).toBeNull()
  })
})
