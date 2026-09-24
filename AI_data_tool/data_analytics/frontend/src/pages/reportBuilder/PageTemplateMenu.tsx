import { useEffect, useState, type CSSProperties } from 'react'
import toast from 'react-hot-toast'
import { reportsApi, pageTemplatesApi } from '../../services/api'
import { useConfirm } from '../../components/ui/ConfirmDialog'

function ImportPagePicker({ reportId, onAdded, itemStyle }: {
  reportId: number; onAdded: () => void; itemStyle: CSSProperties
}) {
  const [reports, setReports] = useState<{ id: number; name: string }[]>([])
  const [source, setSource] = useState<{ id: number; pages: { id: number; name: string }[] } | null>(null)
  useEffect(() => {
    reportsApi.list().then(list => setReports(list.filter(r => r.id !== reportId))).catch(() => {})
  }, [reportId])
  if (reports.length === 0) return null

  return (
    <div style={{ borderTop: '1px solid var(--border)', marginTop: 4, paddingTop: 4 }}>
      <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', padding: '4px 10px' }}>
        Import a page from…
      </div>
      <select aria-label="Source report" value={source?.id ?? ''} style={{ margin: '0 10px 6px', fontSize: 11, width: 'calc(100% - 20px)' }}
        onChange={e => {
          const id = Number(e.target.value)
          if (!id) { setSource(null); return }
          reportsApi.get(id).then(r => setSource({ id, pages: r.pages.map(p => ({ id: p.id, name: p.name })) })).catch(() => {})
        }}>
        <option value="">— choose a report —</option>
        {reports.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
      </select>
      {source?.pages.map(p => (
        <button key={p.id} role="menuitem" style={itemStyle}
          onClick={() => pageTemplatesApi.addFrom(reportId, { source_report_id: source.id, source_page_id: p.id })
            .then(onAdded).catch(() => toast.error('Could not import the page'))}>
          {p.name}
        </button>
      ))}
    </div>
  )
}

export function PageTemplateMenu({ reportId, activePageId, onClose, onAdded }: {
  reportId: number; activePageId: number | null; onClose: () => void; onAdded: () => void
}) {
  const [builtins, setBuiltins] = useState<{ key: string; name: string; widgets: number }[]>([])
  const [saved, setSaved] = useState<{ id: number; name: string; widgets: number }[]>([])
  const [savedFailed, setSavedFailed] = useState(false)
  //: The name being typed for a template about to be saved. SAS's own tip is
  //: "give templates meaningful names"; this used to stamp `Template <date>`,
  //: which tells the next author nothing.
  const [naming, setNaming] = useState<string | null>(null)
  const confirm = useConfirm()
  useEffect(() => {
    pageTemplatesApi.builtins().then(setBuiltins).catch(() => {})
    // A swallowed failure here read as "No saved templates yet", inviting the
    // author to rebuild a template they already have.
    pageTemplatesApi.list().then(t => { setSaved(t); setSavedFailed(false) })
      .catch(() => setSavedFailed(true))
  }, [])

  const item: CSSProperties = { display: 'block', width: '100%', textAlign: 'start',
    background: 'none', border: 'none', padding: '6px 10px', fontSize: 11,
    color: 'var(--text)', cursor: 'pointer', whiteSpace: 'nowrap' }

  return (
    <div role="menu" aria-label="Page templates" style={{ position: 'absolute', top: '100%', insetInlineStart: 0, zIndex: 50,
      background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8,
      boxShadow: '0 8px 24px rgba(0,0,0,.2)', padding: 4, minWidth: 200 }}>
      <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', padding: '4px 10px' }}>Built-in layouts</div>
      {builtins.map(t => (
        <button key={t.key} role="menuitem" style={item}
          onClick={() => pageTemplatesApi.addFrom(reportId, { builtin: t.key })
            .then(onAdded).catch(() => toast.error('Could not add the page'))}>
          {t.name} <span style={{ color: 'var(--muted)' }}>({t.widgets} widgets)</span>
        </button>
      ))}
      {saved.length > 0 && (
        <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', padding: '4px 10px', borderTop: '1px solid var(--border)', marginTop: 4 }}>Your templates</div>
      )}
      {saved.map(t => (
        <div key={t.id} style={{ display: 'flex', alignItems: 'center' }}>
          <button role="menuitem" style={{ ...item, flex: 1 }}
            onClick={() => pageTemplatesApi.addFrom(reportId, { template_id: t.id })
              .then(onAdded).catch(() => toast.error('Could not add the page'))}>
            {t.name} <span style={{ color: 'var(--muted)' }}>({t.widgets} widgets)</span>
          </button>
          <button aria-label={`Delete template ${t.name}`} title={`Delete template ${t.name}`}
            style={{ background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--muted)', fontSize: 12, padding: '0 8px' }}
            onClick={async () => {
              if (!await confirm({ title: `Delete template "${t.name}"?`,
                body: 'This cannot be undone. Pages already built from it are not affected.' })) return
              try {
                await pageTemplatesApi.delete(t.id)
                setSaved(list => list.filter(x => x.id !== t.id))
              } catch { toast.error('Could not delete the template') }
            }}>×</button>
        </div>
      ))}
      <ImportPagePicker reportId={reportId} onAdded={onAdded} itemStyle={item} />
      {activePageId != null && naming === null && (
        <button role="menuitem" style={{ ...item, borderTop: '1px solid var(--border)', marginTop: 4 }}
          onClick={() => setNaming('')}>
          Save current page as a template
        </button>
      )}
      {activePageId != null && naming !== null && (
        <div style={{ display: 'flex', gap: 4, padding: '6px 10px', borderTop: '1px solid var(--border)', marginTop: 4 }}>
          <input aria-label="New template name" autoFocus value={naming}
            placeholder="e.g. Quarterly layout"
            onChange={e => setNaming(e.target.value)}
            onKeyDown={e => { if (e.key === 'Escape') setNaming(null) }}
            style={{ fontSize: 11, width: 150 }} />
          <button className="btn btn-primary btn-sm" style={{ fontSize: 11 }}
            aria-label="Save page template"
            onClick={() => {
              const name = naming.trim()
              // No silent fallback name: an empty box means the author has not
              // decided yet, and `Template 9/11/2026` is what this used to do.
              if (!name) return
              pageTemplatesApi.saveFrom(reportId, activePageId, name)
                .then(() => { toast.success(`Saved "${name}"`); onClose() })
                .catch(() => toast.error('Could not save the template'))
            }}>Save</button>
        </div>
      )}
    </div>
  )
}
