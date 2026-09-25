import { useCrossFilter } from './CrossFilterContext'

export default function FilterBar() {
  const { activeFilters, clearFilter, clearAllFilters } = useCrossFilter()
  if (activeFilters.length === 0) return null

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 0', marginBottom: 8, flexWrap: 'wrap' }}>
      <span style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600 }}>Filters:</span>
      {activeFilters.map(f => (
        <span key={`${f.sourceWidgetId}-${f.column}`} style={{
          display: 'flex', alignItems: 'center', gap: 4,
          background: 'rgba(108,143,255,.15)', border: '1px solid var(--accent)',
          borderRadius: 99, padding: '2px 8px 2px 10px', fontSize: 11,
        }}>
          <span style={{ color: 'var(--accent)' }}>{f.label}</span>
          <button onClick={() => clearFilter(f.column, f.sourceWidgetId)}
            style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', padding: 0, fontSize: 13, lineHeight: 1 }}>
            ×
          </button>
        </span>
      ))}
      <button onClick={clearAllFilters} className="btn btn-ghost btn-sm" style={{ fontSize: 10, padding: '2px 8px' }}>
        Clear all
      </button>
    </div>
  )
}
