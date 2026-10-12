/**
 * Association rules read by the ROLE each value plays: what a rule starts
 * from (its antecedent), what it concludes (its consequent), or both. Five
 * views of the same mined rules -- a network, a matrix, a summary, a table
 * and a chord diagram -- each a `rules_view` of the rules widget
 * (ModelRenderer). Nothing here mines or filters: every figure is counted
 * from the rules the server returned.
 */
import { useT } from '../../../i18n'
import { seriesColor } from '../chartUtils'

type Item = [string, string]
export type Rule = { if_items?: Item[]; then_items?: Item[]; lift?: number; confidence?: number
  support_pct?: number; support_rows?: number }
export type Role = 'A' | 'C' | 'B'
export type RuleView = 'network' | 'matrix' | 'summary' | 'table' | 'chord'
export const RULE_VIEWS: RuleView[] = ['network', 'matrix', 'summary', 'table', 'chord']

export interface RoleItem {
  id: string; column: string; label: string
  /** Rules it starts, rules it ends, and all it appears in. */
  starts: number; ends: number; rules: number
  role: Role
  /** The other items it is linked with, and how: it leads to them (A), they lead to it (C), or both (B). */
  partners: Record<string, Role>
}

const idOf = (i: Item) => `${i[0]}=${i[1]}`

/** A miner reports most links in BOTH directions ("p goes with q" and "q goes
 *  with p" have the same lift), which would make every value "both". What
 *  differs is how SURE each direction is: knowing p may say much more about q
 *  than knowing q says about p. So a link counts as one-way when one
 *  direction's confidence is at least this many times the other's, and as
 *  both ways when they are closer than that. */
export const ONE_WAY = 1.2

/** Every value that appears in a rule, with the role it plays; most-connected first. */
export function ruleRoles(rules: Rule[]): RoleItem[] {
  const items = new Map<string, RoleItem>()
  const get = (i: Item) => {
    const id = idOf(i)
    if (!items.has(id)) items.set(id, { id, column: String(i[0]), label: String(i[1]), starts: 0, ends: 0, rules: 0, role: 'A', partners: {} })
    return items.get(id)!
  }
  const sure = new Map<string, number>()            // "a>c" -> the most confident rule from a to c
  for (const r of rules) {
    const from = (r.if_items ?? []).map(get), to = (r.then_items ?? []).map(get)
    for (const a of from) { a.starts += 1; a.rules += 1 }
    for (const c of to) { c.ends += 1; c.rules += 1 }
    for (const a of from) for (const c of to) {
      const key = `${a.id}>${c.id}`
      sure.set(key, Math.max(sure.get(key) ?? 0, Number(r.confidence) || 0))
    }
  }
  for (const [key, forward] of sure) {
    const [a, c] = key.split('>')
    const back = sure.get(`${c}>${a}`) ?? 0
    // One-way when this direction is clearly the surer (or the only) one.
    const role: Role = !back || forward >= back * ONE_WAY ? 'A' : back >= forward * ONE_WAY ? 'C' : 'B'
    items.get(a)!.partners[c] = role
    items.get(c)!.partners[a] = role === 'A' ? 'C' : role === 'C' ? 'A' : 'B'
  }
  // A value's own role: what it is towards the values it is linked with.
  for (const it of items.values()) {
    const kinds = new Set(Object.values(it.partners))
    it.role = kinds.size === 1 ? [...kinds][0] : kinds.size === 0 ? (it.starts ? 'A' : 'C') : 'B'
  }
  return [...items.values()].sort((a, b) => b.rules - a.rules || a.id.localeCompare(b.id))
}

/** The dashboard's palette, one colour per role, the same in every view. */
export const roleColor = (role: Role) => seriesColor(role === 'A' ? 2 : role === 'C' ? 3 : 1)
const ROLE_KEY = { A: 'mdl.role.a', C: 'mdl.role.c', B: 'mdl.role.b' } as const
const short = (s: string, n = 14) => (s.length > n ? `${s.slice(0, n - 1)}…` : s)
/** A value alone when it is unmistakable, with its column when two columns share it. */
function namer(items: RoleItem[]) {
  const seen = new Map<string, number>()
  for (const i of items) seen.set(i.label, (seen.get(i.label) ?? 0) + 1)
  return (i: RoleItem) => ((seen.get(i.label) ?? 0) > 1 ? `${i.column}: ${i.label}` : i.label)
}

function Legend({ counts }: { counts?: Record<Role, number> }) {
  const t = useT()
  return (
    <div data-testid="role-legend" style={{ display: 'flex', flexWrap: 'wrap', gap: 12, fontSize: 11, margin: '4px 0' }}>
      {(['A', 'C', 'B'] as Role[]).map(r => (
        <span key={r} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
          <span aria-hidden style={{ width: 10, height: 10, borderRadius: 10, background: roleColor(r), display: 'inline-block' }} />
          {t(ROLE_KEY[r])}{counts ? <b style={{ fontVariantNumeric: 'tabular-nums' }}> {counts[r]}</b> : null}
        </span>
      ))}
    </div>
  )
}

/** 1 — the values on a circle, coloured by role, an arrow for every rule. */
function Network({ rules, items }: { rules: Rule[]; items: RoleItem[] }) {
  const t = useT()
  const name = namer(items)
  const W = 360, H = 270, R = 96, cx = W / 2, cy = H / 2
  const at = new Map(items.map((n, i) => {
    const a = (2 * Math.PI * i) / Math.max(items.length, 1) - Math.PI / 2
    return [n.id, { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a), a }]
  }))
  const most = Math.max(...items.map(n => n.rules), 1)
  const kept = new Set(items.map(n => n.id))
  const counts = { A: 0, C: 0, B: 0 } as Record<Role, number>
  for (const i of items) counts[i.role] += 1
  // One line for each linked pair; an arrowhead where the link is one-way.
  const lifts = new Map<string, number>()
  for (const r of rules) for (const a of r.if_items ?? []) for (const c of r.then_items ?? []) {
    const key = [idOf(a), idOf(c)].sort().join('||')
    lifts.set(key, Math.max(lifts.get(key) ?? 0, Number(r.lift) || 1))
  }
  const edges = items.flatMap(n => Object.entries(n.partners)
    .filter(([other, role]) => kept.has(other) && (role === 'A' || (role === 'B' && n.id < other)))
    .map(([other, role]) => ({ a: n.id, c: other, role, lift: lifts.get([n.id, other].sort().join('||')) ?? 1 })))
  const top = Math.max(...edges.map(e => e.lift), 1.0001)
  return (
    <div data-testid="rule-roles-network">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t('mdl.net.aria', { n: items.length, k: edges.length })} style={{ width: '100%', maxHeight: 340 }}>
        <defs>
          <marker id="rr-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="4.5" markerHeight="4.5" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="context-stroke" />
          </marker>
        </defs>
        {edges.map((e, i) => {
          const a = at.get(e.a), b = at.get(e.c)
          if (!a || !b) return null
          // Stop short of the circles so the arrowhead is seen.
          const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1, pad = 12
          return <line key={i} data-testid="role-link" data-role={e.role} x1={a.x + (dx / len) * pad} y1={a.y + (dy / len) * pad}
            x2={b.x - (dx / len) * pad} y2={b.y - (dy / len) * pad}
            stroke={roleColor(e.role)} strokeOpacity={0.7} strokeWidth={0.9 + 2.2 * ((e.lift - 1) / (top - 1 || 1))}
            markerEnd={e.role === 'A' ? 'url(#rr-arrow)' : undefined}>
            <title>{`${e.a} ${e.role === 'A' ? '→' : '↔'} ${e.c} · ${t('mdl.net.lift', { x: e.lift.toFixed(2) })}`}</title>
          </line>
        })}
        {items.map(n => {
          const p = at.get(n.id)!
          const out = Math.cos(p.a) >= 0
          return (
            <g key={n.id} data-testid="role-node" data-role={n.role}>
              <circle cx={p.x} cy={p.y} r={5 + 5 * (n.rules / most)} fill={roleColor(n.role)}>
                <title>{`${n.id} · ${t(ROLE_KEY[n.role])} · ${t('mdl.role.inRules', { n: n.rules })}`}</title>
              </circle>
              <text x={p.x + (out ? 13 : -13)} y={p.y + 3} fontSize={9.5} textAnchor={out ? 'start' : 'end'} fill="currentColor">{short(name(n), 18)}</text>
            </g>
          )
        })}
      </svg>
      <Legend counts={counts} />
    </div>
  )
}

/** 2 — every value against every other: the row's role towards the column. */
function Matrix({ items }: { items: RoleItem[] }) {
  const t = useT()
  const name = namer(items)
  const cell = { padding: '3px 4px', textAlign: 'center' as const, fontSize: 11, border: '1px solid var(--surface)' }
  return (
    <div data-testid="rule-roles-matrix" style={{ overflow: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead><tr>
          <th />
          {items.map(c => <th key={c.id} title={c.id} style={{ ...cell, fontWeight: 600, background: 'none', whiteSpace: 'nowrap' }}>{short(name(c), 10)}</th>)}
        </tr></thead>
        <tbody>
          {items.map(r => (
            <tr key={r.id}>
              <th title={r.id} style={{ ...cell, textAlign: 'start', fontWeight: 500, whiteSpace: 'nowrap', background: 'none' }}>{short(name(r), 16)}</th>
              {items.map(c => {
                const role = r.id === c.id ? null : r.partners[c.id]
                return (
                  <td key={c.id} data-role={role ?? ''} title={role ? `${r.id} — ${c.id}: ${t(ROLE_KEY[role])}` : undefined}
                    style={{ ...cell, fontWeight: 700, color: role ? 'var(--surface)' : 'var(--muted)', background: role ? roleColor(role) : 'var(--surface2)' }}>
                    {role ?? '–'}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <Legend />
      <div style={{ fontSize: 10.5, color: 'var(--muted)' }}>{t('mdl.role.matrixHint')}</div>
    </div>
  )
}

/** 3 — for each value, how many others it leads to, is led to by, or both. */
function Summary({ items }: { items: RoleItem[] }) {
  const name = namer(items)
  const rows = items.map(i => {
    const n = { A: 0, C: 0, B: 0 } as Record<Role, number>
    for (const r of Object.values(i.partners)) n[r] += 1
    return { i, n, total: n.A + n.C + n.B }
  }).sort((a, b) => b.total - a.total)
  const most = Math.max(...rows.map(r => r.total), 1)
  return (
    <div data-testid="rule-roles-summary">
      <Legend />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        {rows.map(({ i, n, total }) => (
          <div key={i.id} data-testid="role-bar" style={{ display: 'grid', gridTemplateColumns: 'minmax(70px, 30%) 1fr 2.2em', gap: 6, alignItems: 'center', fontSize: 11.5 }}>
            <span title={i.id} style={{ textAlign: 'end', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name(i)}</span>
            <span style={{ display: 'flex', height: 13, borderRadius: 3, overflow: 'hidden', width: `${(total / most) * 100}%`, minWidth: 4 }}>
              {(['A', 'C', 'B'] as Role[]).map(r => n[r] > 0 && <span key={r} data-role={r} style={{ flex: n[r], background: roleColor(r) }} />)}
            </span>
            <b style={{ fontVariantNumeric: 'tabular-nums' }}>{total}</b>
          </div>
        ))}
      </div>
    </div>
  )
}

/** 4 — the rules one by one, each value tagged with the role it plays there. */
function Table({ rules }: { rules: Rule[] }) {
  const t = useT()
  const th = { textAlign: 'start' as const, fontSize: 11, color: 'var(--muted)', padding: '4px 6px', borderBottom: '1px solid var(--border)', fontWeight: 600 }
  const td = { fontSize: 12, padding: '5px 6px', borderBottom: '1px solid var(--border)' }
  const numCell = { textAlign: 'end' as const, fontVariantNumeric: 'tabular-nums' as const }
  const chip = (i: Item, role: Role) => (
    <span key={`${idOf(i)}${role}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, marginInlineEnd: 8, whiteSpace: 'nowrap' }}>
      <span aria-hidden style={{ width: 8, height: 8, borderRadius: 8, background: roleColor(role), display: 'inline-block' }} />
      <bdi title={idOf(i)}>{String(i[1])}</bdi><span style={{ color: 'var(--muted)', fontSize: 10.5 }}>({role})</span>
    </span>
  )
  return (
    <div data-testid="rule-roles-table" style={{ overflow: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead><tr>
          <th style={th}>#</th><th style={th}>{t('mdl.r.rule')}</th><th style={th}>{t('mdl.role.items')}</th>
          <th style={{ ...th, ...numCell }}>{t('mdl.role.support')}</th><th style={{ ...th, ...numCell }}>{t('mdl.r.conf')}</th>
          <th style={{ ...th, ...numCell }}>{t('mdl.r.lift')}</th>
        </tr></thead>
        <tbody>
          {rules.map((r, k) => (
            <tr key={k}>
              <td style={{ ...td, color: 'var(--muted)' }}>{k + 1}</td>
              <td style={td}><bdi>{(r.if_items ?? []).map(i => String(i[1])).join(' + ')}</bdi> → <bdi>{(r.then_items ?? []).map(i => String(i[1])).join(' + ')}</bdi></td>
              <td style={td}>{(r.if_items ?? []).map(i => chip(i, 'A'))}{(r.then_items ?? []).map(i => chip(i, 'C'))}</td>
              <td style={{ ...td, ...numCell }}>{r.support_pct != null ? `${Number(r.support_pct).toFixed(1)}%` : '—'}</td>
              <td style={{ ...td, ...numCell }}>{r.confidence != null ? `${(Number(r.confidence) * 100).toFixed(1)}%` : '—'}</td>
              <td style={{ ...td, ...numCell, fontWeight: 700 }}>{r.lift != null ? `${Number(r.lift).toFixed(2)}×` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** 5 — the values as arcs of a ring, a ribbon for every pair that rules link;
 *  the more rules between two, the thicker the ribbon. */
function Chord({ rules, items }: { rules: Rule[]; items: RoleItem[] }) {
  const t = useT()
  const name = namer(items)
  const W = 360, H = 300, cx = W / 2, cy = H / 2, R = 104, ring = 9, gap = 0.035
  const total = items.reduce((s, i) => s + i.rules, 0) || 1
  const free = 2 * Math.PI - gap * items.length
  let angle = -Math.PI / 2
  const arcs = new Map(items.map(i => {
    const span = (i.rules / total) * free
    const a0 = angle, a1 = angle + span
    angle = a1 + gap
    return [i.id, { a0, a1, mid: (a0 + a1) / 2 }]
  }))
  const pt = (a: number, r: number) => `${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`
  const pairs = new Map<string, { a: string; c: string; n: number }>()
  for (const r of rules) for (const a of r.if_items ?? []) for (const c of r.then_items ?? []) {
    const key = [idOf(a), idOf(c)].sort().join('||')
    const p = pairs.get(key) ?? { a: idOf(a), c: idOf(c), n: 0 }
    p.n += 1; pairs.set(key, p)
  }
  const thick = Math.max(...[...pairs.values()].map(p => p.n), 1)
  return (
    <div data-testid="rule-roles-chord">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t('mdl.role.chordAria', { n: items.length, k: pairs.size })} style={{ width: '100%', maxHeight: 360 }}>
        {[...pairs.values()].map((p, i) => {
          const a = arcs.get(p.a), b = arcs.get(p.c)
          if (!a || !b) return null
          return <path key={i} data-testid="chord-ribbon" d={`M${pt(a.mid, R - ring)} Q${cx},${cy} ${pt(b.mid, R - ring)}`} fill="none"
            stroke={roleColor(items.find(n => n.id === p.a)?.role ?? 'A')} strokeOpacity={0.35} strokeWidth={2 + 9 * (p.n / thick)} strokeLinecap="round">
            <title>{`${p.a} — ${p.c} · ${t('mdl.role.inRules', { n: p.n })}`}</title>
          </path>
        })}
        {items.map(i => {
          const a = arcs.get(i.id)!
          const large = a.a1 - a.a0 > Math.PI ? 1 : 0
          const out = Math.cos(a.mid) >= 0
          return (
            <g key={i.id} data-testid="chord-arc" data-role={i.role}>
              <path d={`M${pt(a.a0, R)} A${R},${R} 0 ${large} 1 ${pt(a.a1, R)}`} fill="none" stroke={roleColor(i.role)} strokeWidth={ring} strokeLinecap="butt">
                <title>{`${i.id} · ${t(ROLE_KEY[i.role])} · ${t('mdl.role.inRules', { n: i.rules })}`}</title>
              </path>
              <text x={cx + (R + 12) * Math.cos(a.mid)} y={cy + (R + 12) * Math.sin(a.mid) + 3} fontSize={9.5}
                textAnchor={Math.abs(Math.cos(a.mid)) < 0.2 ? 'middle' : out ? 'start' : 'end'} fill="currentColor">{short(name(i), 16)}</text>
            </g>
          )
        })}
      </svg>
      <Legend />
      <div style={{ fontSize: 10.5, color: 'var(--muted)' }}>{t('mdl.role.chordHint', { n: rules.length })}</div>
    </div>
  )
}

/** One view of the rules by role. `limit`: the most-connected values shown (the rest of a long list would not be readable). */
export default function RuleRoles({ rules, view, limit = 10 }: { rules: Rule[]; view: RuleView; limit?: number }) {
  const t = useT()
  if (!rules.length) return <p style={{ fontSize: 12, color: 'var(--muted)' }}>{t('mdl.r.none')}</p>
  const all = ruleRoles(rules)
  const items = all.slice(0, Math.max(2, limit))
  const kept = new Set(items.map(i => i.id))
  const within = rules.filter(r => [...(r.if_items ?? []), ...(r.then_items ?? [])].every(i => kept.has(idOf(i))))
  const note = all.length > items.length
    ? <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 2 }}>{t('mdl.role.top', { n: items.length, of: all.length })}</div> : null
  if (view === 'table') return <Table rules={rules} />
  return (
    <>
      {view === 'network' && <Network rules={within} items={items} />}
      {view === 'matrix' && <Matrix items={items} />}
      {view === 'summary' && <Summary items={items} />}
      {view === 'chord' && <Chord rules={within} items={items} />}
      {note}
    </>
  )
}
