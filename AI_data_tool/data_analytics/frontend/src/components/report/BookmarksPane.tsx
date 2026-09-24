import { useState } from 'react'
import { reportsApi } from '../../services/api'
import type { Bookmark, BookmarkState } from '../../types/report'

export default function BookmarksPane({ reportId, bookmarks, captureState, onCaptured, onApply, onDeleted }: {
  reportId: number
  bookmarks: Bookmark[]
  captureState: () => BookmarkState
  onCaptured: (b: Bookmark) => void
  onApply: (b: Bookmark) => void
  onDeleted: (id: number) => void
}) {
  const [naming, setNaming] = useState(false)
  const [name, setName] = useState('')

  const save = async () => {
    if (!name.trim()) return
    const bm = await reportsApi.addBookmark(reportId, { name, position: bookmarks.length, state: captureState() })
    onCaptured(bm)
    setNaming(false)
    setName('')
  }

  return (
    <div style={{ padding: '14px 14px 0' }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
        Bookmarks
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 10 }}>
        {bookmarks.map(b => (
          <div key={b.id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <button onClick={() => onApply(b)} style={{ flex: 1, textAlign: 'start', padding: '5px 7px',
              background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6,
              cursor: 'pointer', fontSize: 12 }}>
              {b.name}
            </button>
            <button onClick={() => reportsApi.deleteBookmark(reportId, b.id).then(() => onDeleted(b.id))}
              style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer' }}>×</button>
          </div>
        ))}
        {bookmarks.length === 0 && <span style={{ fontSize: 12, color: 'var(--muted)' }}>No bookmarks yet.</span>}
      </div>
      {naming ? (
        <div style={{ display: 'flex', gap: 6 }}>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="Bookmark name…" style={{ flex: 1, fontSize: 12 }} autoFocus />
          <button className="btn btn-primary btn-sm" onClick={save}>Save</button>
        </div>
      ) : (
        <button className="btn btn-ghost btn-sm" onClick={() => setNaming(true)}>+ Add bookmark</button>
      )}
    </div>
  )
}
