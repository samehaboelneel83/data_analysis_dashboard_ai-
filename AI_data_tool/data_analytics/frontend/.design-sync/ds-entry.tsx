// Design-system entry for /design-sync.
//
// The app has no library build, so the converter would otherwise synthesize an
// entry that re-exports every file under src/ - pulling the whole product
// (router, axios, contexts, 275 components) into the uploaded bundle. This
// entry pins the surface instead: the ui/ primitives and the two imperative
// dialog providers, which is exactly what the design project is meant to hold.
//
// Hooks are exported alongside their providers because a provider is unusable
// without the hook that opens its dialog.

export { default as EmptyState } from '../src/components/ui/EmptyState'
export { default as IconLabel } from '../src/components/ui/IconLabel'
export { default as LoadError } from '../src/components/ui/LoadError'
export { default as Loader } from '../src/components/ui/Loader'
export { default as LoadingState } from '../src/components/ui/LoadingState'

export { ConfirmProvider, useConfirm } from '../src/components/ui/ConfirmDialog'
export type { ConfirmOptions } from '../src/components/ui/ConfirmDialog'
export { PromptProvider, usePrompt } from '../src/components/ui/PromptDialog'
export type { PromptOptions } from '../src/components/ui/PromptDialog'
