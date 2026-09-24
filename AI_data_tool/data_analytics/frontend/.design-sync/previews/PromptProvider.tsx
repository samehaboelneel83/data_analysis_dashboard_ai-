import { useEffect } from 'react'
import { PromptProvider, usePrompt } from 'datalytics-frontend'

// Same imperative shape as ConfirmProvider: opened on mount, never settled, one
// cell because the overlay is position:fixed. Shown pre-filled, which is the
// case that matters - a rename that starts blank makes the user retype a name
// they did not want to change.

function PageBehind() {
  return (
    <div style={{ padding: 24 }}>
      <p style={{ fontWeight: 600, marginBottom: 12 }}>Workspace</p>
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {['Finance', 'Operations', 'Shared with me'].map((n) => (
          <div key={n} style={{ padding: '10px 14px', fontSize: 13, borderBottom: '1px solid var(--border)' }}>
            {n}
          </div>
        ))}
      </div>
    </div>
  )
}

function OpenOnMount({ options }: { options: Parameters<ReturnType<typeof usePrompt>>[0] }) {
  const prompt = usePrompt()
  useEffect(() => { void prompt(options) }, [prompt])
  return <PageBehind />
}

export function RenameFolder() {
  return (
    <PromptProvider>
      <OpenOnMount
        options={{
          title: 'Rename folder',
          body: 'Everyone with access to this folder sees the new name.',
          label: 'Folder name',
          defaultValue: 'Finance',
          confirmLabel: 'Rename',
        }}
      />
    </PromptProvider>
  )
}
