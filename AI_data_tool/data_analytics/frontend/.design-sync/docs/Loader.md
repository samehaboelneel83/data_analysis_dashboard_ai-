---
category: State
---

# Loader

The route-level loader: three balls bouncing on their shadows, centred on an
otherwise empty screen while the next route's chunk arrives.

```jsx
const { Loader } = window.Datalytics;

<Suspense fallback={<Loader label="Loading your workspace…" />}>
  <Routes />
</Suspense>
```

**Use it only when the screen is otherwise empty.** Every wait that happens with
content already around it uses `LoadingState` instead — an animation next to text
someone is reading competes with it, while on a blank screen it is the only thing
there. In the product this has exactly one caller, the router's Suspense fallback.

## Behaviour worth knowing

- Balls and shadows read from the theme, so the same markup works in light and dark.
- The animation stops under `prefers-reduced-motion`.
- `label` renders as visible text, not just an `aria-label` — an animation alone
  does not say what is being waited on.

Styling hooks: `.dl-loading`, `.dl-loader`, `.dl-loader__ball`,
`.dl-loader__shadow`, `.dl-loading__label`.
