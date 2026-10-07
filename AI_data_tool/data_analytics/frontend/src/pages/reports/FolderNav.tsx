import { useEffect, useRef, useState } from 'react'
import { Check, Clock, Folder, FolderOpen, FolderPlus, Info, LayoutGrid, Pencil, Trash2, Users, X } from 'lucide-react'
import ActionMenu from '../../components/ActionMenu'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import type { FlatFolder } from './model'

/**
 * The Dashboards page's left column (redesign 7b): views, then the folders of
 * the workspace tree with what each holds. Every folder is a drop target for
 * a dragged dashboard. Favourites and "Suggested by AI" are not here: the
 * backend has no favourites or stored AI proposals (PLAN.md).
 */

export type View = 'all' | 'recent' | 'shared' | `f:${number}`

export interface DropProps {
  onDragOver: (e: React.DragEvent) => void
  onDragLeave: () => void
  onDrop: (e: React.DragEvent) => void
}

export default function FolderNav({ view, onView, counts, folders, treeFailed, onRetryTree, creating, onStartFolder,
  onCreateFolder, onCancelFolder, onSubfolder, onRename, onDelete, dropFor, overTarget, dragHint, ready }: {
  view: View
  onView: (v: View) => void
  counts: { all: number; recent: number | null; shared: number | null }
  folders: FlatFolder[]
  treeFailed: boolean
  onRetryTree: () => void
  creating: boolean
  onStartFolder: () => void
  onCreateFolder: (name: string) => void
  onCancelFolder: () => void
  onSubfolder: (f: FlatFolder) => void
  onRename: (f: FlatFolder) => void
  onDelete: (f: FlatFolder) => void
  dropFor: (key: string, folderId: number | null, name: string | null) => DropProps
  overTarget: string | null
  dragHint: boolean
  /** False while the list is loading or failed: counts would be zeros that
   *  are not true, and "No folders yet" would be a guess. */
  ready: boolean
}) {
  const t = useT()
  const [name, setName] = useState('')
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { if (creating) { setName(''); input.current?.focus() } }, [creating])
  const n = (v: number | null) => v == null || !ready ? null : <span className="n">{localDigits(String(v))}</span>

  const item = (v: View, icon: React.ReactNode, label: string, count: number | null) => (
    <div className="dsh-tirow">
      <button type="button" className="dsh-ti" aria-current={view === v} onClick={() => onView(v)}>
        {icon}<span className="tx" title={label}>{label}</span>{n(count)}
      </button>
    </div>
  )

  return (
    <nav className="dsh-tree" aria-label={t('dsh.folders')} data-testid="dash-nav">
      <div className="dsh-tg">{t('dsh.views')}</div>
      {item('all', <LayoutGrid size={16} aria-hidden />, t('dsh.view.all'), counts.all)}
      {item('recent', <Clock size={16} aria-hidden />, t('dsh.view.recent'), counts.recent)}
      {item('shared', <Users size={16} aria-hidden />, t('dsh.view.shared'), counts.shared)}

      <div className="dsh-tg">
        {t('dsh.folders')}
        {ready && !treeFailed && (
          <button type="button" className="dsh-ib" onClick={onStartFolder} aria-label={t('folders.newTop')} title={t('folders.newTop')}>
            <FolderPlus size={15} aria-hidden />
          </button>
        )}
      </div>
      {treeFailed && (
        <p className="dsh-tnote" role="status">{t('dsh.foldersFailed')} <button type="button" onClick={onRetryTree}>{t('hm.retry')}</button></p>
      )}
      {creating && (
        <form className="dsh-nf" onSubmit={e => { e.preventDefault(); if (name.trim()) onCreateFolder(name.trim()) }}>
          <FolderPlus size={15} aria-hidden />
          <input ref={input} value={name} onChange={e => setName(e.target.value)} aria-label={t('dsh.folderName')} placeholder={t('dsh.folderName')} dir="auto"
            onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); onCancelFolder() } }} />
          <button type="submit" className="dsh-ib" disabled={!name.trim()} aria-label={t('dsh.createFolder')} title={t('dsh.createFolder')}><Check size={15} aria-hidden /></button>
          <button type="button" className="dsh-ib" onClick={onCancelFolder} aria-label={t('common.cancel')} title={t('common.cancel')}><X size={15} aria-hidden /></button>
        </form>
      )}
      {folders.map(f => {
        const key = `nav:${f.id}`
        const v: View = `f:${f.id}`
        return (
          <div key={f.id} className="dsh-tirow" data-drop={overTarget === key || undefined} {...dropFor(key, f.id, f.name)}
            style={{ paddingInlineStart: f.depth * 14 }}>
            <button type="button" className="dsh-ti" aria-current={view === v} onClick={() => onView(v)} data-folder={f.name}>
              {view === v ? <FolderOpen size={16} aria-hidden /> : <Folder size={16} aria-hidden />}
              <span className="tx" title={f.name}><bdi>{f.name}</bdi></span>{n(f.count)}
            </button>
            {f.can_manage && (
              <span className="dsh-timenu">
                <ActionMenu label={t('folders.actions', { name: f.name })} portal align="end" triggerClassName="dsh-ib"
                  items={[
                    { key: 'sub', label: t('folders.new'), icon: <FolderPlus size={14} />, onSelect: () => onSubfolder(f) },
                    { key: 'rename', label: t('folders.rename'), icon: <Pencil size={14} />, onSelect: () => onRename(f) },
                    { key: 'delete', label: t('folders.delete'), icon: <Trash2 size={14} />, danger: true, onSelect: () => onDelete(f) },
                  ]} />
              </span>
            )}
          </div>
        )
      })}
      {ready && !treeFailed && !folders.length && !creating && <p className="dsh-tnote">{t('dsh.noFolders')}</p>}
      {dragHint && folders.length > 0 && (
        <div className="dsh-tfoot"><Info size={14} aria-hidden /><span>{t('dsh.dragHint')}</span></div>
      )}
    </nav>
  )
}
