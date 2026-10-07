import { ChevronDown, EyeOff, Plus } from 'lucide-react'
import type { ReactNode } from 'react'
import ActionMenu from '../../components/ActionMenu'
import { useDirection } from '../../contexts/DirectionContext'
import { useT } from '../../i18n'

export interface PageTab { id: number; name: string; page_type?: string | null }

/**
 * The builder's page tabs (redesign 7e1), after the prototype's second row:
 * the open page is a raised pill, each page has a ⌄ menu (Rename, Move left /
 * right, Page settings, Delete), and + adds a page. v1's double-click rename,
 * the hidden / pop-up markers and the "last page cannot go" rule are kept;
 * Delete moved from a bare "x" on every tab into the menu.
 */
export default function PageTabs({ pages, activeId, renamingId, renameValue, onRenameValue, onSelect,
  onStartRename, onSaveName, onDelete, onMove, onSettings, onAdd, addExtra, label }: {
  pages: PageTab[]
  activeId: number | null
  renamingId: number | null
  renameValue: string
  onRenameValue: (v: string) => void
  onSelect: (p: PageTab) => void
  onStartRename: (p: PageTab) => void
  onSaveName: (p: PageTab) => void
  onDelete: (p: PageTab) => void
  onMove: (p: PageTab, by: -1 | 1) => void
  onSettings: (p: PageTab) => void
  onAdd: () => void
  /** Beside +: v1's "Add page from a template" menu. */
  addExtra?: ReactNode
  label: (name: string) => string
}) {
  const t = useT()
  // Left and right are where the tab moves on screen: in Arabic the order runs
  // right to left, so "Move left" is later in the order.
  const { rtl } = useDirection()
  const left: -1 | 1 = rtl ? 1 : -1
  return (
    // A group of buttons, not a tablist: each page carries its own menu and
    // the group ends with +, which a tablist may not contain (axe).
    <div className="dl-bd-pages" role="group" aria-label={t('view.pages')}>
      {pages.map((p, i) => {
        const on = p.id === activeId
        const kind = p.page_type === 'hidden' ? t('bd.pg.hidden') : p.page_type === 'popup' ? t('bd.pg.popup') : null
        return (
          <span key={p.id} className="dl-bd-pg" data-on={on || undefined} data-kind={p.page_type ?? undefined}>
            {renamingId === p.id ? (
              <input className="dl-bd-pg__in" aria-label={t('bd.pg.name')} value={renameValue} autoFocus dir="auto"
                onChange={e => onRenameValue(e.target.value)} onBlur={() => onSaveName(p)}
                onKeyDown={e => { if (e.key === 'Enter') onSaveName(p) }} />
            ) : (
              <button type="button" aria-current={on ? 'page' : undefined} className="dl-bd-pg__b"
                aria-label={kind ? `${label(p.name)} (${kind})` : undefined}
                onClick={() => onSelect(p)} onDoubleClick={() => onStartRename(p)}>
                {kind && <EyeOff size={12} aria-hidden className="dl-bd-pg__k" />}
                <bdi>{label(p.name)}</bdi>
              </button>
            )}
            <ActionMenu label={t('bd.pg.menu', { name: label(p.name) })} portal triggerClassName="dl-bd-pg__m"
              trigger={<ChevronDown size={13} aria-hidden />}
              items={[
                { key: 'rename', label: t('bd.pg.rename'), onSelect: () => onStartRename(p) },
                { key: 'left', label: t('bd.pg.left'), disabled: left === -1 ? i === 0 : i === pages.length - 1, onSelect: () => onMove(p, left) },
                { key: 'right', label: t('bd.pg.right'), disabled: left === -1 ? i === pages.length - 1 : i === 0, onSelect: () => onMove(p, left === -1 ? 1 : -1) },
                { key: 'settings', label: t('bd.pg.settings'), onSelect: () => onSettings(p) },
                ...(pages.length > 1 ? [{ key: 'delete', label: t('bd.pg.delete'), danger: true, onSelect: () => onDelete(p) }] : []),
              ]} />
          </span>
        )
      })}
      <span className="dl-bd-add">
        <button type="button" className="dl-bd-ib" aria-label={t('bd.pg.add')} title={t('bd.pg.add')} onClick={onAdd}>
          <Plus size={15} aria-hidden />
        </button>
        {addExtra}
      </span>
    </div>
  )
}
