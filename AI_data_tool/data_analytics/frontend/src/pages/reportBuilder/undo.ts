/**
 * Builder undo/redo -- a command log, not state snapshots.
 *
 * Every builder mutation is a server write, so an undo entry carries the
 * inverse WRITE plus a human sentence naming it ("Delete "Revenue by region"").
 * The sentence is the product: SAS VA's descriptive undo is what lets its users
 * explore without fear, and a bare "Undo" button does not do that.
 *
 * Two details that are easy to get wrong:
 *
 *  - Undoing a delete RECREATES the widget, and the server gives it a new id.
 *    Older entries still hold the old id, so every command resolves ids through
 *    `IdAliases` at the moment it runs, never at the moment it was recorded.
 *  - A settings field fires one write per keystroke. Entries sharing a
 *    `coalesceKey` within COALESCE_MS merge: the FIRST undo is kept (back to
 *    before the typing) and the LATEST redo wins. Ctrl+Z then undoes "the
 *    title change", not the last letter of it.
 */
import { useCallback, useRef, useState } from 'react'

export interface UndoCommand {
  /** Shown as "Undo: <label>". One grammar: verb, item, object, value. */
  label: string
  undo: () => Promise<void>
  redo: () => Promise<void>
  /** Consecutive commands with the same key, close in time, merge into one. */
  coalesceKey?: string
}

interface Entry extends UndoCommand { at: number }

export const UNDO_LIMIT = 100
export const COALESCE_MS = 1500

/** Plain, framework-free stack so the rules are unit-testable. */
export class UndoStack {
  past: Entry[] = []
  future: Entry[] = []

  /** Set by any undo/redo: nothing may merge across one, whatever the clock says. */
  private sealed = false

  push(cmd: UndoCommand, now: number = Date.now()): void {
    const last = this.past[this.past.length - 1]
    if (!this.sealed && cmd.coalesceKey && last && last.coalesceKey === cmd.coalesceKey
        && now - last.at <= COALESCE_MS) {
      // Keep the first undo (the state before the burst), take the new redo.
      this.past[this.past.length - 1] = { ...last, label: cmd.label, redo: cmd.redo, at: now }
    } else {
      this.past.push({ ...cmd, at: now })
      if (this.past.length > UNDO_LIMIT) this.past.shift()
    }
    // A new edit forks history: whatever was undone can no longer be redone.
    this.future = []
    this.sealed = false
  }

  /** Remove and return the entry to undo; the caller runs it. */
  takeUndo(): Entry | undefined { this.sealed = true; return this.past.pop() }
  takeRedo(): Entry | undefined { this.sealed = true; return this.future.pop() }
  /** After a successful undo the entry becomes redoable, and vice versa. */
  undone(e: Entry): void { this.future.push(e) }
  redone(e: Entry): void { this.past.push(e) }

  get undoLabel(): string | null { return this.past[this.past.length - 1]?.label ?? null }
  get redoLabel(): string | null { return this.future[this.future.length - 1]?.label ?? null }
}

/**
 * Old widget id -> the id it lives under now. Undoing a delete and redoing an
 * add both mint new ids; `resolve` follows the chain to the current one.
 */
export class IdAliases {
  private map = new Map<number, number>()
  set(from: number, to: number): void { if (from !== to) this.map.set(from, to) }
  resolve(id: number): number {
    let cur = id
    const seen = new Set<number>()
    while (this.map.has(cur) && !seen.has(cur)) { seen.add(cur); cur = this.map.get(cur)! }
    return cur
  }
}

// ── Sentences ────────────────────────────────────────────────────────────────

const MAX_VALUE = 28

function show(v: unknown): string {
  if (v === undefined || v === null || v === '') return 'none'
  const s = typeof v === 'string' ? v : JSON.stringify(v)
  return s.length > MAX_VALUE ? `${s.slice(0, MAX_VALUE - 1)}…` : s
}

/** `measure_col` -> "measure col"; the config key is the only name we have. */
export function settingName(key: string): string {
  return key.replace(/_/g, ' ').replace(/\s+/g, ' ').trim()
}

/** Keys whose value differs between two configs (shallow, JSON-compared). */
export function changedKeys(before: Record<string, unknown>, after: Record<string, unknown>): string[] {
  const keys = new Set([...Object.keys(before), ...Object.keys(after)])
  return [...keys].filter(k => JSON.stringify(before[k]) !== JSON.stringify(after[k])).sort()
}

/** The one sentence for a widget settings change. */
export function describeConfigChange(
  widgetName: string,
  before: Record<string, unknown>, after: Record<string, unknown>,
  beforeTitle: string, afterTitle: string,
): string {
  const keys = changedKeys(before, after)
  const renamed = beforeTitle !== afterTitle
  if (renamed && keys.length === 0) return `Rename "${beforeTitle}" to "${afterTitle}"`
  if (keys.length === 1 && !renamed) {
    const k = keys[0]
    return `Change ${settingName(k)} of "${widgetName}" from ${show(before[k])} to ${show(after[k])}`
  }
  const n = keys.length + (renamed ? 1 : 0)
  return `Change ${n} settings of "${widgetName}"`
}

// ── React binding ────────────────────────────────────────────────────────────

export interface UndoApi {
  push: (cmd: UndoCommand) => void
  undo: () => Promise<string | null>
  redo: () => Promise<string | null>
  undoLabel: string | null
  redoLabel: string | null
  busy: boolean
}

/**
 * `onAfter` runs after every undo/redo (the builder reloads the report there).
 * A command that throws is DROPPED rather than kept: its target is usually gone
 * (another session deleted the page), and retrying it would fail forever.
 */
export function useUndoStack(
  onAfter: () => Promise<void>,
  onError: (label: string, err: unknown) => void,
): UndoApi {
  const stack = useRef(new UndoStack())
  const busyRef = useRef(false)
  const [, bump] = useState(0)
  const [busy, setBusy] = useState(false)
  const rerender = () => bump(n => n + 1)

  const push = useCallback((cmd: UndoCommand) => {
    if (busyRef.current) return // never record the effects of an undo itself
    stack.current.push(cmd)
    rerender()
  }, [])

  const run = useCallback(async (dir: 'undo' | 'redo'): Promise<string | null> => {
    if (busyRef.current) return null
    const s = stack.current
    const e = dir === 'undo' ? s.takeUndo() : s.takeRedo()
    if (!e) return null
    busyRef.current = true
    setBusy(true)
    try {
      await (dir === 'undo' ? e.undo() : e.redo())
      if (dir === 'undo') s.undone(e); else s.redone(e)
      await onAfter()
      return e.label
    } catch (err) {
      onError(e.label, err)
      return null
    } finally {
      busyRef.current = false
      setBusy(false)
      rerender()
    }
  }, [onAfter, onError])

  return {
    push,
    undo: () => run('undo'),
    redo: () => run('redo'),
    undoLabel: stack.current.undoLabel,
    redoLabel: stack.current.redoLabel,
    busy,
  }
}
