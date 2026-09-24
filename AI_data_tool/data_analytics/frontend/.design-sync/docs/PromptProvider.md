---
category: Overlays
---

# PromptProvider

Promise-based replacement for `window.prompt`, and the sibling of
`ConfirmProvider`. Mount once near the root; call `usePrompt()` beneath it.

```jsx
const { PromptProvider, usePrompt } = window.Datalytics;

// once, near the root
<PromptProvider>
  <App />
</PromptProvider>

// anywhere inside
const prompt = usePrompt();
const name = await prompt({ title: 'Rename folder', defaultValue: folder.name });
if (name === null) return;   // cancelled
```

Resolves the entered string, or `null` when cancelled. `usePrompt()` throws outside
a `<PromptProvider>`.

## Options

| Option | Meaning |
|---|---|
| `title` | Short question. Becomes the dialog's accessible name. Required. |
| `body` | Optional detail line under the title. |
| `label` | Label for the text field. Defaults to the title, visually hidden. |
| `defaultValue` | Pre-filled value — `window.prompt`'s second argument. |
| `placeholder` | Placeholder text. |
| `confirmLabel` | Say the verb ("Rename"), not "OK". |
| `cancelLabel` | Defaults to `Cancel`. |
| `required` | Default **true**: the affirmative button stays disabled while the field is blank, so callers never re-check for an empty string. |

Pass `defaultValue` for any rename. Starting blank makes the user retype a name
they did not want to change.

## Why not `window.prompt`

Besides blocking the thread and being unthemeable, it is invisible to the DOM:
assistive technology, automated tests and browser automation cannot see or drive
it, so a rename typed into a native prompt lands wherever the browser decides
rather than in the field.
