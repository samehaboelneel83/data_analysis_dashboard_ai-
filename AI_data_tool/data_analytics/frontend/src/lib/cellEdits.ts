/**
 * In-place cell editing, recorded as a prep step.
 *
 * SAS Visual Analytics edits the source table: you type in a cell and the data
 * changes. This does the same thing from the user's side and something quite
 * different underneath -- a correction becomes an `edit_cells` step in the
 * dataset's prep pipeline, applied on every load.
 *
 * The trade, stated rather than hidden:
 *
 *   * The uploaded file is never rewritten, so removing the step restores the
 *     original value, and nothing about the source becomes un-reproducible.
 *   * The correction is visible in the pipeline beside every other transform,
 *     rather than being an invisible difference between the file and the data.
 *   * It is addressed by the VALUE of a key column, not by row number, so it
 *     survives a re-upload -- and a row with no usable key cannot be corrected
 *     this way, which is the honest cost.
 *
 * These are the merge rules that keep one step per (key column, column) pair,
 * so fifty corrections are one step and not fifty.
 */
import type { PrepStep } from '../services/api'

/** MIRRORS MAX_CELL_EDITS in backend services/prep.py -- the backend rejects
 *  the save, and refusing here means the user is told at the keystroke rather
 *  than losing an edit to a 400. Pinned by test_frontend_constant_mirrors.py. */
export const MAX_CELL_EDITS = 500

export interface CellEdit { key: string; value: unknown }

interface EditCellsStep extends Record<string, unknown> {
  kind: 'edit_cells'
  key_column: string
  column: string
  edits: CellEdit[]
}

function isEditCells(s: PrepStep, keyColumn: string, column: string): boolean {
  return s.kind === 'edit_cells'
    && (s as unknown as EditCellsStep).key_column === keyColumn
    && (s as unknown as EditCellsStep).column === column
}

/** The pipeline with one cell correction folded in. Never mutates its input:
 *  the panel holds the SAVED pipeline in state, and mutating it would move the
 *  UI ahead of what the server has agreed to. */
export function mergeCellEdit(
  steps: PrepStep[],
  { keyColumn, column, key, value }:
    { keyColumn: string; column: string; key: string; value: unknown },
): PrepStep[] {
  const index = steps.findIndex(s => isEditCells(s, keyColumn, column))
  if (index === -1) {
    return [...steps, { kind: 'edit_cells', key_column: keyColumn,
      column, edits: [{ key, value }] } as unknown as PrepStep]
  }
  const step = steps[index] as unknown as EditCellsStep
  const at = step.edits.findIndex(e => e.key === key)
  // Replacing an existing edit does not grow the step, so it stays allowed at
  // the limit -- otherwise a full step would trap the user with a typo.
  if (at === -1 && step.edits.length >= MAX_CELL_EDITS) {
    throw new Error(
      `At most ${MAX_CELL_EDITS} corrections per column. Past that, a join or a `
      + `fixed source file is the right answer -- every one of these is replayed `
      + `on every load of the dataset.`)
  }
  const edits = at === -1
    ? [...step.edits, { key, value }]
    : step.edits.map((e, i) => (i === at ? { key, value } : e))
  const next = [...steps]
  next[index] = { ...step, edits } as unknown as PrepStep
  return next
}

/** Which keys carry a correction for this column, so the grid can mark the
 *  cells it changed rather than presenting edited and original values alike. */
export function editedValues(steps: PrepStep[], keyColumn: string,
                             column: string): Map<string, unknown> {
  const out = new Map<string, unknown>()
  for (const s of steps) {
    if (!isEditCells(s, keyColumn, column)) continue
    for (const e of (s as unknown as EditCellsStep).edits ?? []) out.set(e.key, e.value)
  }
  return out
}
