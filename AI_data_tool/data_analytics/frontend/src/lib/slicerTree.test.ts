import { describe, it, expect } from 'vitest'
import { describePaths, fromPaths, keyOf, leaves, searchTree, stateOf, toggle, toPaths, type TreeNode } from './slicerTree'

const n = (value: string, children: TreeNode[] = [], count = 1): TreeNode => ({ value, count, children })
const TREE: TreeNode[] = [
  n('Egypt', [n('Alexandria'), n('Cairo')]),
  n('US', [n('Alexandria'), n('Boston')]),
]

describe('hierarchy slicer tree', () => {
  it('ticking a country ticks its cities, and the parent reads half-ticked when some are', () => {
    let t = toggle(TREE[0], ['Egypt'], new Set())
    expect(stateOf(TREE[0], ['Egypt'], t)).toBe('on')
    t = toggle(TREE[0].children[1], ['Egypt', 'Cairo'], t)
    expect(stateOf(TREE[0], ['Egypt'], t)).toBe('mixed')
    expect(stateOf(TREE[1], ['US'], t)).toBe('off')
  })

  it('sends the shortest paths: a whole country is one path, everything ticked is no filter', () => {
    let t = toggle(TREE[0], ['Egypt'], new Set())
    t = toggle(TREE[1].children[1], ['US', 'Boston'], t)
    expect(toPaths(TREE, t)).toEqual([['Egypt'], ['US', 'Boston']])
    expect(toPaths(TREE, new Set(leaves(TREE).map(keyOf)))).toBeNull()
    expect(toPaths(TREE, new Set())).toEqual([])
  })

  it('the same Alexandria under two countries stays two different paths', () => {
    const t = toggle(TREE[0].children[0], ['Egypt', 'Alexandria'], new Set())
    expect(toPaths(TREE, t)).toEqual([['Egypt', 'Alexandria']])
    expect(stateOf(TREE[1].children[0], ['US', 'Alexandria'], t)).toBe('off')
  })

  it('reads a saved filter back into ticks (a bookmark, another tab)', () => {
    const t = fromPaths(TREE, [['Egypt'], ['US', 'Boston']])
    expect([...t].sort()).toEqual([keyOf(['Egypt', 'Alexandria']), keyOf(['Egypt', 'Cairo']), keyOf(['US', 'Boston'])].sort())
  })

  it('search shows the matches and opens the way to them', () => {
    const s = searchTree(TREE, 'bost')!
    expect(s.visible.has(keyOf(['US', 'Boston']))).toBe(true)
    expect(s.visible.has(keyOf(['US']))).toBe(true)
    expect(s.open.has(keyOf(['US']))).toBe(true)
    expect(s.visible.has(keyOf(['Egypt']))).toBe(false)
    expect(searchTree(TREE, '  ')).toBeNull()
    expect(searchTree([n('مصر', [n('القاهرة')])], 'القاهرة')!.visible.has(keyOf(['مصر']))).toBe(true)
  })

  it('describes a selection in words', () => {
    expect(describePaths([['Egypt'], ['US', 'Boston']])).toBe('Egypt, US › Boston')
    expect(describePaths([['a'], ['b'], ['c'], ['d'], ['e']])).toBe('a, b, c +2')
  })
})
