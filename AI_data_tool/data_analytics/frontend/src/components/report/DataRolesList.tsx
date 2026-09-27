import { useEffect, useState, type ReactNode } from 'react'
import type { RoleField } from '../../types/report'
import { useModalDialog } from '../ui/useModalDialog'

/**
 * The Data roles pane as SAS VA lays it out: one collapsible section per role,
 * each with "+ Add", and the fields already assigned listed under it as links.
 * Clicking a field opens its own settings (name, aggregation, date grouping)
 * right under it.
 *
 * Presentational only. Which fields a role accepts, and every rule about
 * assigning them, stays in the role pickers of the Assign data dialog -- "+ Add"
 * opens that dialog on the role instead of carrying a second copy of the rules.
 */

export type FieldKind = 'category' | 'measure' | 'date'

export interface DataRolesListProps {
  specs: RoleField[]
  /** Assigned fields per role, in order. */
  values: Record<string, string[]>
  kindOf: (field: string) => FieldKind
  /** Shown instead of the column name, e.g. "Region (hierarchy)". */
  displayName?: (role: string, field: string) => string
  onAdd: (role: string) => void
  onRemove: (role: string, field: string) => void
  /** The settings a field opens with; null = the field has none to open. */
  renderDetails?: (role: string, field: string) => ReactNode | null
  /** Why a role cannot take a field just now (another role's choice rules
   *  it out), or null. Its "+ Add" is greyed and says so. */
  addBlocked?: (role: string) => string | null
}

/** "Dimension (Group / X-axis)" -> heading "Dimension", hint "Group / X-axis". */
function splitLabel(rf: RoleField): { heading: string; hint?: string } {
  const text = rf.label ?? rf.role
  const m = /^(.*?)\s*\((.*)\)\s*$/.exec(text)
  return m ? { heading: m[1], hint: m[2] } : { heading: text }
}

export function FieldIcon({ kind }: { kind: FieldKind }) {
  const common = { width: 14, height: 14, viewBox: '0 0 16 16', fill: 'none', stroke: 'currentColor',
    strokeWidth: 1.4, 'aria-hidden': true as const, style: { flex: '0 0 auto', color: 'var(--muted)' } }
  if (kind === 'measure') {
    // A ruler: a quantity.
    return (
      <svg {...common}><path d="M2.5 10.5 10.5 2.5l3 3-8 8z" /><path d="M5 8l1.2 1.2M7 6l1.2 1.2M9 4l1.2 1.2" /></svg>
    )
  }
  if (kind === 'date') {
    return (<svg {...common}><rect x="2.5" y="3.5" width="11" height="10" rx="1" /><path d="M2.5 6.5h11M5.5 2v3M10.5 2v3" /></svg>)
  }
  // A category: distinct bars.
  return (<svg {...common}><path d="M3 13V6M6.3 13V3M9.6 13V8M13 13V5" /><path d="M2 13.5h12" /></svg>)
}

export default function DataRolesList({ specs, values, kindOf, displayName, onAdd, onRemove, renderDetails, addBlocked }: DataRolesListProps) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [open, setOpen] = useState<string | null>(null)
  const toggleRole = (role: string) => setCollapsed(prev => {
    const next = new Set(prev)
    if (next.has(role)) next.delete(role); else next.add(role)
    return next
  })

  return (
    <div data-testid="data-roles-list">
      {specs.map(rf => {
        const { heading, hint } = splitLabel(rf)
        const fields = values[rf.role] ?? []
        const isCollapsed = collapsed.has(rf.role)
        // A single-field role is full once it has its field. SAS still shows
        // its "+ Add", greyed; replacing is done from the field's × or from
        // Assign data.
        const blocked = addBlocked?.(rf.role) ?? null
        const canAdd = !blocked && (rf.multi || fields.length === 0)
        const sectionId = `data-role-section-${rf.role}`
        return (
          <section key={rf.role} data-roles-section={rf.role} style={{ marginBottom: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, minHeight: 28 }}>
              <button type="button" aria-expanded={!isCollapsed} aria-controls={sectionId}
                onClick={() => toggleRole(rf.role)} title={hint}
                style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, minWidth: 0, background: 'none',
                  border: 'none', padding: '2px 0', cursor: 'pointer', font: 'inherit', fontSize: 13,
                  color: 'var(--text)', textAlign: 'start' }}>
                <span aria-hidden style={{ display: 'inline-block', width: 10, fontSize: 10, color: 'var(--muted)',
                  transform: isCollapsed ? 'rotate(-90deg)' : 'none', transition: 'transform .12s' }}>⌄</span>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{heading}</span>
                {rf.required && fields.length === 0 && (
                  <span style={{ fontSize: 11, color: 'var(--danger, #c0392b)' }} title="Required">*</span>
                )}
              </button>
              <button type="button" onClick={() => onAdd(rf.role)} aria-label={`Add ${heading}`}
                disabled={!canAdd}
                title={blocked ?? (canAdd ? undefined : `${heading} takes one field. Remove it to choose another.`)}
                style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'none', border: 'none',
                  cursor: canAdd ? 'pointer' : 'default', font: 'inherit', fontSize: 13, padding: '2px 4px',
                  color: canAdd ? 'var(--text)' : 'var(--muted)', opacity: canAdd ? 1 : 0.55 }}>
                <span aria-hidden style={{ fontSize: 16, lineHeight: 1 }}>+</span> Add
              </button>
            </div>
            {!isCollapsed && (
              <ul id={sectionId} style={{ listStyle: 'none', margin: 0, padding: '0 0 0 18px' }}>
                {fields.length === 0 && (
                  <li style={{ fontSize: 12, color: 'var(--muted)', padding: '2px 0' }}>
                    {rf.required ? 'Required' : 'None'}
                  </li>
                )}
                {fields.map(f => {
                  const key = `${rf.role}:${f}`
                  const details = renderDetails?.(rf.role, f) ?? null
                  const isOpen = open === key && details !== null
                  const name = displayName?.(rf.role, f) ?? f
                  return (
                    <li key={key} data-role-field={key} style={{ padding: '2px 0' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <FieldIcon kind={kindOf(f)} />
                        {/* Named with its role: "sales, Measure" -- the same field can
                            sit in two roles, and the field list beside the canvas
                            has a "sales" button of its own. */}
                        <button type="button" aria-expanded={details !== null ? isOpen : undefined}
                          aria-label={`${name}, ${heading}`}
                          onClick={() => setOpen(isOpen ? null : key)}
                          style={{ flex: 1, minWidth: 0, textAlign: 'start', background: 'none', border: 'none', padding: 0,
                            font: 'inherit', fontSize: 13, color: 'var(--accent)',
                            cursor: details !== null ? 'pointer' : 'default',
                            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {name}
                        </button>
                        <button type="button" onClick={() => onRemove(rf.role, f)} aria-label={`Remove ${f} from ${heading}`}
                          title="Remove"
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)',
                            fontSize: 14, lineHeight: 1, padding: '0 2px' }}>×</button>
                      </div>
                      {isOpen && (
                        <div style={{ margin: '6px 0 8px', padding: '8px 10px', borderInlineStart: '2px solid var(--border)' }}>
                          {details}
                        </div>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        )
      })}
    </div>
  )
}

/**
 * "Assign data", level one: every role of the object and what it holds. Each
 * role's "+ Add" opens level two, AddFieldDialog, on top of it. Opened from
 * the pane's button and on its own right after a chart is inserted -- a new
 * chart's first job is to be given its data. `children` is the role list.
 */
export function AssignDataDialog({ objectName, focusRole, onClose, children }: {
  objectName: string
  focusRole?: string | null
  onClose: () => void
  children: ReactNode
}) {
  const ref = useModalDialog<HTMLDivElement>(onClose)
  useEffect(() => {
    if (!focusRole) return
    const row = ref.current?.querySelector<HTMLElement>(`[data-roles-section="${focusRole}"]`)
    row?.scrollIntoView?.({ block: 'nearest' })
    row?.querySelector<HTMLElement>('button:not([disabled])')?.focus()
  }, [focusRole, ref])
  return (
    <div onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}
      style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center',
        justifyContent: 'center', background: 'rgba(0,0,0,.45)', padding: 16 }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={`Assign data: ${objectName}`}
        style={{ width: 'min(460px, 100%)', maxHeight: 'min(640px, calc(100vh - 32px))', display: 'flex',
          flexDirection: 'column', background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', boxShadow: '0 16px 48px rgba(0,0,0,.35)', color: 'var(--text)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '14px 16px 10px',
          borderBottom: '1px solid var(--border)' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 650, fontSize: 15 }}>Assign data</div>
            <div style={{ fontSize: 12, color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis',
              whiteSpace: 'nowrap' }}>{objectName}</div>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="btn btn-ghost btn-sm">×</button>
        </div>
        <div style={{ overflowY: 'auto', padding: '14px 16px', fontSize: 13 }}>
          {children}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '10px 16px',
          borderTop: '1px solid var(--border)' }}>
          <button type="button" className="btn btn-primary btn-sm" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  )
}

export interface FieldChoice { value: string; label: string; group?: string }

/**
 * "+ Add" on a role: only the fields that role accepts, grouped (Categories,
 * Dates, Numbers...). A role that takes several fields is a checklist -- what
 * it holds already ticked, new ones appended in the order ticked -- applied
 * with Add; a one-field role applies on the click.
 */
export function AddFieldDialog({ heading, multi, choices, selected, onApply, onClose, emptyText }: {
  heading: string
  multi: boolean
  choices: FieldChoice[]
  selected: string[]
  /** What to say when no field fits this role at all. */
  emptyText?: string
  onApply: (values: string[]) => void
  onClose: () => void
}) {
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const [picked, setPicked] = useState<string[]>(selected)
  const [q, setQ] = useState('')
  const needle = q.trim().toLowerCase()
  const shown = choices.filter(c => !needle || c.label.toLowerCase().includes(needle))
  const groups = [...new Set(shown.map(c => c.group ?? ''))]
  const toggle = (v: string) => setPicked(p => p.includes(v) ? p.filter(x => x !== v) : [...p, v])
  const choose = (v: string) => { onApply([v]); onClose() }
  const changed = picked.length !== selected.length || picked.some((v, i) => v !== selected[i])
  return (
    <div onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}
      style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center',
        justifyContent: 'center', background: 'rgba(0,0,0,.45)', padding: 16 }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={`Add ${heading}`}
        style={{ width: 'min(380px, 100%)', maxHeight: 'min(560px, calc(100vh - 32px))', display: 'flex',
          flexDirection: 'column', background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', boxShadow: '0 16px 48px rgba(0,0,0,.35)', color: 'var(--text)' }}>
        <div style={{ padding: '14px 16px 10px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontWeight: 650, fontSize: 15, marginBottom: 2 }}>Add {heading}</div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>
            {multi ? 'Choose one or more fields.' : 'Choose a field.'}
          </div>
          <input type="search" value={q} onChange={e => setQ(e.target.value)} aria-label="Search fields"
            placeholder="Search fields…" style={{ width: '100%' }} />
        </div>
        <div role={multi ? 'group' : 'listbox'} aria-label={`${heading} fields`}
          style={{ overflowY: 'auto', padding: '6px 8px', fontSize: 13 }}>
          {shown.length === 0 && (
            <div style={{ padding: '10px 8px', color: 'var(--muted)', fontSize: 12 }}>
              {choices.length === 0 ? (emptyText ?? 'No field in this data fits this role.') : 'No field matches.'}
            </div>
          )}
          {groups.map(g => (
            <div key={g || '_'}>
              {g && <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase',
                letterSpacing: '.06em', padding: '8px 8px 4px' }}>{g}</div>}
              {shown.filter(c => (c.group ?? '') === g).map(c => {
                const on = picked.includes(c.value)
                return multi ? (
                  <label key={c.value} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 8px',
                    borderRadius: 6, cursor: 'pointer' }}>
                    <input type="checkbox" checked={on} onChange={() => toggle(c.value)} />
                    <span style={{ flex: 1 }}>{c.label}</span>
                    {on && <span style={{ fontSize: 11, color: 'var(--accent)' }}>#{picked.indexOf(c.value) + 1}</span>}
                  </label>
                ) : (
                  <button key={c.value} type="button" role="option" aria-selected={on} onClick={() => choose(c.value)}
                    style={{ display: 'block', width: '100%', textAlign: 'start', padding: '6px 8px', borderRadius: 6,
                      border: 'none', font: 'inherit', fontSize: 13, cursor: 'pointer', color: 'var(--text)',
                      background: on ? 'var(--surface2)' : 'transparent' }}>
                    {c.label}
                  </button>
                )
              })}
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, padding: '10px 16px',
          borderTop: '1px solid var(--border)' }}>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
          {multi && (
            <button type="button" className="btn btn-primary btn-sm" disabled={!changed}
              onClick={() => { onApply(picked); onClose() }}>Add</button>
          )}
        </div>
      </div>
    </div>
  )
}
