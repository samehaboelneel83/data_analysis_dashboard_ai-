---
category: State
---

# LoadError

"We could not ask" — the failure counterpart to `EmptyState`. Deliberately *not*
styled like an empty state: an interruption with a retry, carrying the only colour
of the three state surfaces, because the correct next action is to try again rather
than to create something.

```jsx
const { LoadError } = window.Datalytics;

<LoadError what="reports" error={err} onRetry={reload} />
```

## What `error` does

Whatever you caught, passed straight through. The component digs out the most
specific message available, in this order:

1. `error.response.data.detail` — the API's own message (axios shape).
2. `error.message` — when it is an `Error`.
3. Otherwise a generic line that says explicitly that the data is not missing,
   only unreachable.

So pass the raw error; do not pre-stringify it, or you will render `[object Object]`
or an axios stack where a sentence belongs.

## Props

- **what** — in the user's words, reading after "Could not load ": `"reports"`,
  `"the lineage graph"`, `"this dataset"`.
- **onRetry** — renders the "Try again" button. Omit it only when a retry is
  genuinely impossible.

Renders with `role="alert"` and a `--danger` leading border via
`border-inline-start`, so it mirrors correctly under RTL.
