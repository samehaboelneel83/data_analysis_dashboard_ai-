import { useEffect } from 'react'
import { ConfirmProvider, useConfirm } from 'datalytics-frontend'

// The dialog is imperative - it exists only while an await is pending - so the
// preview opens one on mount and never settles it. The overlay is
// position:fixed and covers the frame, which is why this card shows a single
// cell rather than a variant grid.

function PageBehind() {
  return (
    <div style={{ padding: 24 }}>
      <p style={{ fontWeight: 600, marginBottom: 12 }}>Reports</p>
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {['Q3 Revenue by Region', 'Churn cohorts 2026', 'Warehouse load times'].map((n) => (
          <div key={n} style={{ padding: '10px 14px', fontSize: 13, borderBottom: '1px solid var(--border)' }}>
            {n}
          </div>
        ))}
      </div>
    </div>
  )
}

function OpenOnMount({ options }: { options: Parameters<ReturnType<typeof useConfirm>>[0] }) {
  const confirm = useConfirm()
  useEffect(() => { void confirm(options) }, [confirm])
  return <PageBehind />
}

export function DeleteConfirmation() {
  return (
    <ConfirmProvider>
      <OpenOnMount
        options={{
          title: 'Delete "Q3 Revenue by Region"?',
          body: 'The report and its 12 widgets are removed for everyone it is shared with. This cannot be undone.',
          confirmLabel: 'Delete',
        }}
      />
    </ConfirmProvider>
  )
}
