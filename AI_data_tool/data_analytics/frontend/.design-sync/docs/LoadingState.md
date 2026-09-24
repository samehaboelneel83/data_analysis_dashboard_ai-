---
category: State
---

# LoadingState

The quiet in-place wait: one muted line, no motion. Use it whenever the page is
already drawn around the thing being loaded — a panel fetching rows, a dialog
loading roles, a widget querying.

```jsx
const { LoadingState } = window.Datalytics;

<LoadingState label="Profiling 1.2M rows…" />
```

Defaults to `Loading…`. Pass a `label` when you can name the work, which is almost
always better than the generic line.

## Choosing between the three waits

| Situation | Use |
|---|---|
| Page already drawn, one region is waiting | `LoadingState` |
| Whole route is waiting, screen otherwise empty | `Loader` |
| The request failed | `LoadError` |

Never leave `LoadingState` on screen after a failed request — a permanent
"Loading…" is a lie, and it is the bug this component and `LoadError` were
separated to prevent.
