---
category: Overlays
---

# ConfirmProvider

Promise-based replacement for `window.confirm`. Mount the provider once near the
root; call the `useConfirm()` hook anywhere beneath it.

```jsx
const { ConfirmProvider, useConfirm } = window.Datalytics;

// once, near the root
<ConfirmProvider>
  <App />
</ConfirmProvider>

// anywhere inside
const confirm = useConfirm();
if (!(await confirm({ title: `Delete "${name}"?` }))) return;
await api.delete(id);
```

`useConfirm()` throws outside a `<ConfirmProvider>`, so the provider is not
optional. There is no `<ConfirmDialog>` element to render — the dialog exists only
while an `await` is pending.

## Options

| Option | Meaning |
|---|---|
| `title` | Short question. Becomes the dialog's accessible name. Required. |
| `body` | What exactly happens, and whether it can be undone. |
| `confirmLabel` | Say the verb — "Delete", "Remove", "Replace" — never "OK". Defaults to `Delete`. |
| `cancelLabel` | Defaults to `Cancel`. |
| `destructive` | Defaults to **true**. Pass `false` for a benign confirmation, which styles the affirmative button with `--accent` instead of `--danger`. |

Resolves `true` on confirm and `false` on cancel, Escape, or a backdrop click —
the safe answer is always "no" for an action the user has not yet agreed to.

## Why not `window.confirm`

It blocks the JS thread, cannot be themed, and browsers let a user tick "prevent
this page from creating additional dialogs" — after which `confirm()` returns false
forever and every guarded action silently does nothing, with no way for the app to
tell it was suppressed.

Accessibility is built in: `role="alertdialog"`, `aria-modal`, focus moved to the
affirmative button on open, Tab trapped between the two buttons, and focus restored
to the triggering element on close.
