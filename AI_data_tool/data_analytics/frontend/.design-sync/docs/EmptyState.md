---
category: State
---

# EmptyState

"There is nothing here yet" — **not** "we could not load it". Reach for `LoadError`
when a request failed; showing an empty state after a failed fetch tells the user
their data is gone and gets duplicate work created.

A card, a muted icon, a bold one-line title, an optional explanation, and a primary
button when there is a next action worth naming.

```jsx
const { EmptyState } = window.Datalytics;
import { Database } from 'lucide-react';

<EmptyState
  icon={Database}
  title="No datasets yet"
  description="Import a file or connect a source to start building reports."
  action={<button className="btn btn-primary">Add a connection</button>}
/>
```

## Writing the copy

- **title** — state the absence in the user's nouns: "No reports yet", "No connections".
- **description** — optional; say what would fill the space, not why it is empty.
- **action** — pass a real `<button className="btn btn-primary">`. Omit it when there
  is nothing the user can do from here; a disabled button is worse than none.

The icon renders at 40px in `var(--muted)`, so pass the outline glyph that names the
missing thing (`Database`, `FolderOpen`, `Plug`), not a decorative one.
