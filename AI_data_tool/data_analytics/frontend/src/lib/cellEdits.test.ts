/**
 * In-place cell editing, recorded as a prep step.
 *
 * SAS edits the source table. Here a typed correction becomes a step in the
 * pipeline, so the uploaded file is never rewritten, the change is visible
 * beside every other transform, and removing it restores the original. These
 * are the merge rules that keep one step per (key column, column) pair instead
 * of a new step per keystroke.
 */
import { describe, it, expect } from 'vitest'
import { MAX_CELL_EDITS, editedValues, mergeCellEdit } from './cellEdits'
import type { PrepStep } from '../services/api'

const edit = { keyColumn: 'order_id', column: 'region' }

describe('mergeCellEdit', () => {
  it('starts a step when there is none', () => {
    const out = mergeCellEdit([], { ...edit, key: 'A-1', value: 'North' })
    expect(out).toEqual([{ kind: 'edit_cells', key_column: 'order_id',
      column: 'region', edits: [{ key: 'A-1', value: 'North' }] }])
  })

  it('appends into the step that already covers this column', () => {
    // One step per column, not one per keystroke: fifty corrections must not
    // become fifty steps in the pipeline list.
    const first = mergeCellEdit([], { ...edit, key: 'A-1', value: 'North' })
    const out = mergeCellEdit(first, { ...edit, key: 'A-2', value: 'South' })
    expect(out).toHaveLength(1)
    expect((out[0] as unknown as { edits: unknown[] }).edits).toEqual([
      { key: 'A-1', value: 'North' }, { key: 'A-2', value: 'South' }])
  })

  it('replaces an earlier edit of the same cell', () => {
    const first = mergeCellEdit([], { ...edit, key: 'A-1', value: 'Norht' })
    const out = mergeCellEdit(first, { ...edit, key: 'A-1', value: 'North' })
    expect((out[0] as unknown as { edits: unknown[] }).edits).toEqual([
      { key: 'A-1', value: 'North' }])
  })

  it('keeps a different column in its own step', () => {
    const first = mergeCellEdit([], { ...edit, key: 'A-1', value: 'North' })
    const out = mergeCellEdit(first, { ...edit, column: 'amount', key: 'A-1', value: 5 })
    expect(out).toHaveLength(2)
  })

  it('keeps the same column under a different key in its own step', () => {
    const first = mergeCellEdit([], { ...edit, key: 'A-1', value: 'North' })
    const out = mergeCellEdit(first, { ...edit, keyColumn: 'code', key: 'X', value: 'North' })
    expect(out).toHaveLength(2)
  })

  it('leaves the other steps alone and in order', () => {
    const steps: PrepStep[] = [{ kind: 'trim' }, { kind: 'case', column: 'region', to: 'upper' }]
    const out = mergeCellEdit(steps, { ...edit, key: 'A-1', value: 'North' })
    expect(out.slice(0, 2)).toEqual(steps)
    expect(out).toHaveLength(3)
  })

  it('does not mutate the steps it was given', () => {
    // The panel holds the saved pipeline in state; mutating it would move the
    // UI ahead of what the server has agreed to.
    const steps = mergeCellEdit([], { ...edit, key: 'A-1', value: 'North' })
    const snapshot = JSON.parse(JSON.stringify(steps))
    mergeCellEdit(steps, { ...edit, key: 'A-2', value: 'South' })
    expect(steps).toEqual(snapshot)
  })

  it('refuses past the limit the backend enforces', () => {
    const edits = Array.from({ length: MAX_CELL_EDITS }, (_, i) => ({ key: `A-${i}`, value: i }))
    const full: PrepStep[] = [{ kind: 'edit_cells', key_column: 'order_id',
      column: 'region', edits }]
    expect(() => mergeCellEdit(full, { ...edit, key: 'NEW', value: 'x' })).toThrow(/500|limit|too many/i)
  })

  it('still allows correcting a cell that is already edited when full', () => {
    // Replacing an existing edit does not grow the step, so refusing it would
    // trap the user with a typo they cannot fix.
    const edits = Array.from({ length: MAX_CELL_EDITS }, (_, i) => ({ key: `A-${i}`, value: i }))
    const full: PrepStep[] = [{ kind: 'edit_cells', key_column: 'order_id',
      column: 'region', edits }]
    const out = mergeCellEdit(full, { ...edit, key: 'A-0', value: 'fixed' })
    expect((out[0] as unknown as { edits: { key: string; value: unknown }[] }).edits[0].value).toBe('fixed')
  })

  it('records an empty entry as a cleared cell, not the text "null"', () => {
    const out = mergeCellEdit([], { ...edit, key: 'A-1', value: null })
    expect((out[0] as unknown as { edits: { value: unknown }[] }).edits[0].value).toBeNull()
  })
})

describe('editedValues', () => {
  it('reports which keys a column has edits for, so the grid can mark them', () => {
    const steps = mergeCellEdit(
      mergeCellEdit([], { ...edit, key: 'A-1', value: 'North' }),
      { ...edit, key: 'A-2', value: 'South' })
    const marks = editedValues(steps, 'order_id', 'region')
    expect(marks.get('A-1')).toBe('North')
    expect(marks.get('A-2')).toBe('South')
    expect(marks.size).toBe(2)
  })

  it('is empty for a column with no edits', () => {
    expect(editedValues([{ kind: 'trim' }], 'order_id', 'region').size).toBe(0)
  })

  it('ignores edits recorded against a different key column', () => {
    const steps = mergeCellEdit([], { ...edit, keyColumn: 'code', key: 'X', value: 'North' })
    expect(editedValues(steps, 'order_id', 'region').size).toBe(0)
  })
})
