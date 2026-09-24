import { LoadingState } from 'datalytics-frontend'

// The quiet in-place wait: one muted line, no motion, used wherever the page is
// already drawn around it.

export function Default() {
  return <LoadingState />
}

export function CustomLabel() {
  return <LoadingState label="Running query…" />
}

export function InPanel() {
  return (
    <div className="card" style={{ padding: 20, width: 280 }}>
      <p style={{ fontWeight: 600, marginBottom: 10 }}>Column statistics</p>
      <LoadingState label="Profiling 1.2M rows…" />
    </div>
  )
}
