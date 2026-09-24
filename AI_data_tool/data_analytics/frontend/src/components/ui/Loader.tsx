/**
 * The navigation loader: three balls bouncing on their shadows, centred on the
 * page while the next route's chunk arrives.
 *
 * ONE CALLER, ON PURPOSE. `App.tsx` renders this as the router's Suspense
 * fallback and nothing else does. Every other wait in the product — a panel
 * fetching rows, a dialog loading roles, a widget querying — happens with the
 * page already drawn around it, and those keep the quiet one-line
 * `LoadingState`. An animation next to content someone is reading competes
 * with it; an animation on an otherwise empty screen is the only thing there.
 *
 * Adapted from Uiverse.io by mobinkakei. Two changes from the original, both
 * deliberate:
 *
 *   - the balls were `#fff` and the shadows `rgba(0,0,0,.9)`, which is a white
 *     ball on a white page in light mode — invisible. They read from the theme
 *     instead, so the same markup works in both.
 *   - the animation stops under `prefers-reduced-motion`. An infinite bounce
 *     is exactly the kind of motion that rule exists for.
 *
 * `label` stays rendered as text, not just an aria-label: an animation alone
 * does not say what is being waited on.
 */
export default function Loader({ label }: { label?: string }) {
  return (
    <div className="dl-loading" role="status" aria-live="polite">
      <div className="dl-loader" aria-hidden>
        <span className="dl-loader__ball" />
        <span className="dl-loader__ball" />
        <span className="dl-loader__ball" />
        <span className="dl-loader__shadow" />
        <span className="dl-loader__shadow" />
        <span className="dl-loader__shadow" />
      </div>
      {label && <p className="dl-loading__label">{label}</p>}
    </div>
  )
}
