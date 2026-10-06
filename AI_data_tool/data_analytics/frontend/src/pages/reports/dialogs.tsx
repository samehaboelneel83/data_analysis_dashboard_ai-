import { useEffect, useState } from 'react'
import { Folder, FolderOpen, LayoutTemplate, Plus, Sparkles, SquareDashedBottom, X } from 'lucide-react'
import { useModalDialog } from '../../components/ui/useModalDialog'
import { useT, type MessageKey } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { pageTemplatesApi, type DatasetSummary } from '../../services/api'
import type { FlatFolder } from './model'
import type { Widget } from '../../types/report'
import Thumb from '../home/Thumb'

/**
 * The Dashboards page's two dialogs (redesign 7b): New dashboard and Move to
 * folder. Both hand their answer back to the page, which owns the calls.
 */

export type NewMode = 'blank' | 'tpl' | 'ai'
export interface NewChoice {
  mode: NewMode
  name: string
  datasetId: number | null
  folderId: number | null
  template: string | null
  goal: string
}

const OPTIONS: { k: NewMode; icon: typeof Plus; title: MessageKey; sub: MessageKey }[] = [
  { k: 'blank', icon: SquareDashedBottom, title: 'dsh.new.blank', sub: 'dsh.new.blankSub' },
  { k: 'tpl', icon: LayoutTemplate, title: 'dsh.new.tpl', sub: 'dsh.new.tplSub' },
  { k: 'ai', icon: Sparkles, title: 'dsh.new.ai', sub: 'dsh.new.aiSub' },
]

/** Folder options, indented by depth, after "Not in a folder". */
function FolderSelect({ id, folders, value, onChange }: {
  id: string; folders: FlatFolder[]; value: number | null; onChange: (v: number | null) => void
}) {
  const t = useT()
  return (
    <select id={id} className="dsh-in" value={value ?? ''} onChange={e => onChange(e.target.value ? Number(e.target.value) : null)}>
      <option value="">{t('dsh.notInFolder')}</option>
      {folders.map(f => <option key={f.id} value={f.id}>{'  '.repeat(f.depth)}{f.name}</option>)}
    </select>
  )
}

/** The built-in templates' names, in the reader's language by their key (QA
 *  T1); a template this build does not know keeps the name the server sent. */
const TEMPLATE_NAMES: Record<string, MessageKey> = {
  'kpi-strip': 'dsh.tpl.kpi', quad: 'dsh.tpl.quad', 'geo-overview': 'dsh.tpl.geo', 'detail-page': 'dsh.tpl.detail',
}

export function NewDashboardDialog({ datasets, folders, initialMode, initialFolder, placeholderName, busy, onClose, onCreate }: {
  datasets: DatasetSummary[]
  folders: FlatFolder[]
  initialMode: NewMode
  initialFolder: number | null
  placeholderName: string
  busy: boolean
  onClose: () => void
  onCreate: (c: NewChoice) => void
}) {
  const t = useT()
  const tplName = (tp: { key: string; name: string }) => (TEMPLATE_NAMES[tp.key] ? t(TEMPLATE_NAMES[tp.key]) : tp.name)
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const [mode, setMode] = useState<NewMode>(initialMode)
  const [name, setName] = useState('')
  const [datasetId, setDatasetId] = useState<number | null>(null)
  const [folderId, setFolderId] = useState<number | null>(initialFolder)
  const [goal, setGoal] = useState('')
  const [templates, setTemplates] = useState<{ key: string; name: string; widgets: number }[] | null>(null)
  const [tplFailed, setTplFailed] = useState(false)
  const [template, setTemplate] = useState<string | null>(null)

  useEffect(() => {
    if (mode !== 'tpl' || templates) return
    pageTemplatesApi.builtins()
      .then(ts => { setTemplates(ts); setTemplate(x => x ?? ts[0]?.key ?? null) })
      .catch(() => setTplFailed(true))
  }, [mode, templates])

  // With AI proposes from a dataset; the others can choose data later.
  const blocked = busy || (mode === 'ai' && datasetId == null) || (mode === 'tpl' && !template)
  const submit = () => { if (!blocked) onCreate({ mode, name: name.trim(), datasetId, folderId, template, goal: goal.trim() }) }

  return (
    <div className="dsh-scrim">
      <div ref={ref} className="dsh-dlg" role="dialog" aria-modal="true" aria-labelledby="dsh-new-t">
        <div className="dsh-dh">
          <div className="tt"><h2 id="dsh-new-t">{t('dsh.new.title')}</h2></div>
          <button type="button" className="dsh-ib" onClick={onClose} aria-label={t('common.cancel')} title={t('common.cancel')}><X size={16} aria-hidden /></button>
        </div>
        <div className="dsh-db">
          <div className="dsh-opts" role="radiogroup" aria-label={t('dsh.new.how')}>
            {OPTIONS.map(o => (
              <button key={o.k} type="button" role="radio" aria-checked={mode === o.k} className="dsh-opt" onClick={() => setMode(o.k)}>
                <span className="ic" aria-hidden><o.icon size={18} /></span><b>{t(o.title)}</b>{t(o.sub)}
              </button>
            ))}
          </div>
          {mode === 'tpl' && (
            tplFailed ? <p className="dsh-note" role="alert">{t('dsh.new.tplFailed')}</p>
            : !templates ? <p className="dsh-note">{t('common.loading')}</p>
            : (
              <div className="dsh-tpls" role="radiogroup" aria-label={t('dsh.new.tpl')}>
                {templates.map(tp => (
                  <button key={tp.key} type="button" role="radio" aria-checked={template === tp.key} className="dsh-tpl" onClick={() => setTemplate(tp.key)}>
                    <TemplateArt k={tp.key} />
                    <b>{tplName(tp)}</b>
                    <span>{t('dsh.new.widgets', { n: localDigits(String(tp.widgets)) })}</span>
                  </button>
                ))}
              </div>
            )
          )}
          {mode === 'ai' && (
            <div className="dsh-aiw">
              <label className="dsh-lbl" htmlFor="dsh-goal">{t('dsh.new.goal')}</label>
              <textarea id="dsh-goal" className="dsh-in ta" value={goal} onChange={e => setGoal(e.target.value)} dir="auto"
                placeholder={t('dsh.new.goalPh')} maxLength={500} />
              <p>{t('dsh.new.aiNote')}</p>
            </div>
          )}
          <div className="dsh-fl">
            {mode !== 'ai' && (
              <div>
                <label htmlFor="dsh-name">{t('dsh.new.name')}</label>
                <input id="dsh-name" className="dsh-in" value={name} onChange={e => setName(e.target.value)} placeholder={placeholderName} dir="auto"
                  onKeyDown={e => { if (e.key === 'Enter') submit() }} />
              </div>
            )}
            <div>
              <label htmlFor="dsh-ds">{t('dsh.dataset')}</label>
              <select id="dsh-ds" className="dsh-in" value={datasetId ?? ''} onChange={e => setDatasetId(e.target.value ? Number(e.target.value) : null)}>
                <option value="">{t(mode === 'ai' ? 'dsh.new.pickDataset' : 'dsh.new.chooseLater')}</option>
                {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </div>
            {mode !== 'ai' && (
              <div>
                <label htmlFor="dsh-folder">{t('dsh.folder')}</label>
                <FolderSelect id="dsh-folder" folders={folders} value={folderId} onChange={setFolderId} />
              </div>
            )}
          </div>
        </div>
        <div className="dsh-df">
          <span className="dsh-sp" />
          <button type="button" className="btn btn-ghost dsh-btn-line" onClick={onClose}>{t('common.cancel')}</button>
          <button type="button" className="btn btn-primary" disabled={blocked} onClick={submit}
            title={mode === 'ai' && datasetId == null ? t('dsh.new.pickDataset') : undefined}>
            {mode === 'ai' ? <Sparkles size={14} aria-hidden /> : <Plus size={14} aria-hidden />}
            {t(mode === 'ai' ? 'dsh.new.createAi' : 'dsh.new.create')}
          </button>
        </div>
      </div>
    </div>
  )
}

/** Each built-in page template's own layout (services/page_templates.py),
 *  drawn with the same schematic thumbnails as the dashboards. The builtins
 *  endpoint returns names and counts only, so the layouts are mirrored here. */
const TEMPLATE_LAYOUT: Record<string, [string, number, number, number, number][]> = {
  'kpi-strip': [['kpi', 0, 0, 3, 3], ['kpi', 3, 0, 3, 3], ['kpi', 6, 0, 3, 3], ['kpi', 9, 0, 3, 3], ['bar', 0, 3, 6, 6], ['line', 6, 3, 6, 6]],
  quad: [['bar', 0, 0, 6, 5], ['line', 6, 0, 6, 5], ['donut', 0, 5, 6, 5], ['table', 6, 5, 6, 5]],
  'geo-overview': [['map_choropleth', 0, 0, 8, 8], ['kpi', 8, 0, 4, 3], ['bar', 8, 3, 4, 5]],
  'detail-page': [['slicer', 0, 0, 3, 6], ['bar', 3, 0, 9, 6], ['table', 0, 6, 12, 6]],
}

function TemplateArt({ k }: { k: string }) {
  const ws = (TEMPLATE_LAYOUT[k] ?? []).map(([widget_type, x, y, w, h], i) =>
    ({ id: i, widget_type, layout: { x, y, w, h } }) as unknown as Widget)
  return <Thumb widgets={ws} />
}

export function MoveDialog({ names, folders, current, onClose, onMove }: {
  names: string[]
  folders: FlatFolder[]
  current: number | null | undefined
  onClose: () => void
  onMove: (folderId: number | null, folderName: string | null) => void
}) {
  const t = useT()
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const [to, setTo] = useState<number | null>(null)
  const [picked, setPicked] = useState(false)
  const title = names.length === 1 ? t('dsh.move.titleOne', { name: names[0] }) : t('dsh.move.titleMany', { n: localDigits(String(names.length)) })
  const choose = (id: number | null) => { setTo(id); setPicked(true) }
  return (
    <div className="dsh-scrim">
      <div ref={ref} className="dsh-dlg sm" role="dialog" aria-modal="true" aria-labelledby="dsh-move-t">
        <div className="dsh-dh">
          <div className="tt"><h2 id="dsh-move-t">{title}</h2></div>
          <button type="button" className="dsh-ib" onClick={onClose} aria-label={t('common.cancel')} title={t('common.cancel')}><X size={16} aria-hidden /></button>
        </div>
        <div className="dsh-db">
          <div className="dsh-folders" role="radiogroup" aria-label={t('dsh.folders')}>
            {current !== null && (
              <button type="button" role="radio" aria-checked={picked && to === null} onClick={() => choose(null)}>
                <FolderOpen size={15} aria-hidden />{t('dsh.notInFolder')}
              </button>
            )}
            {folders.filter(f => f.id !== current).map(f => (
              <button key={f.id} type="button" role="radio" aria-checked={picked && to === f.id} onClick={() => choose(f.id)}
                style={{ paddingInlineStart: 10 + f.depth * 16 }}>
                <Folder size={15} aria-hidden /><bdi>{f.name}</bdi>
              </button>
            ))}
          </div>
          {/* A folder's grants reach everything in it, so a move can widen who
              sees the dashboard. Said before it happens, as v1 did. */}
          <p className="dsh-note">{t('dsh.move.note')}</p>
        </div>
        <div className="dsh-df">
          <span className="dsh-sp" />
          <button type="button" className="btn btn-ghost dsh-btn-line" onClick={onClose}>{t('common.cancel')}</button>
          <button type="button" className="btn btn-primary" disabled={!picked}
            onClick={() => onMove(to, to == null ? null : folders.find(f => f.id === to)?.name ?? null)}>{t('dsh.move.go')}</button>
        </div>
      </div>
    </div>
  )
}
