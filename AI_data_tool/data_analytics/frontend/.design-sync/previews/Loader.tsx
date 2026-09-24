import { Loader } from 'datalytics-frontend'

// Route-level wait only - see the component's own note on why panel-level waits
// use LoadingState instead. The balls animate; a screenshot catches one frame.

export function Unlabelled() {
  return <Loader />
}

export function WithLabel() {
  return <Loader label="Loading your workspace…" />
}
