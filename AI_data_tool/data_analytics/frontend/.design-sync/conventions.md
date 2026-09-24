# Building with Datalytics

Datalytics is an analytics product: datasets, reports, dashboards, charts. The
design language is deliberately quiet — the accent sits *behind* chart colour,
because in an analytics surface the data should pull the eye, not the chrome.

## Setup

Link `styles.css` and load `_ds_bundle.js` (React first). No wrapper element is
required: all 156 theme tokens resolve at `:root`. (The only custom
properties that don't are component-scoped locals — `.dl-loader`'s `--dl-ball`
/ `--dl-rise` and `--dl-shell-pad` — which are internals, not part of the
token vocabulary below.)

- **Dark mode**: set `data-theme="dark"` on `<html>`. Every token is redefined for
  it; nothing else changes. The dark canvas is deep slate, never pure black.
- **`ConfirmProvider` / `PromptProvider`**: only needed if you call `useConfirm()`
  or `usePrompt()`. Those hooks **throw** outside their provider. Nothing else in
  this system needs a provider.

## Styling idiom

There are **no utility classes** — this is not Tailwind. Style your own layout with
`var(--*)` tokens, and use the component classes below for anything the system
already names. Never write a colour, radius, font stack or spacing literal: every
one of them exists as a token, and hard-coding breaks dark mode silently.

**Tokens you will reach for most** (`--mc-*` is the brand layer underneath; prefer
these app-facing names):

| Group | Names |
|---|---|
| Surface / text | `--bg` `--surface` `--surface2` `--border` `--text` `--muted` |
| Accent / semantic | `--accent` `--accent-strong` `--accent-soft` `--success` `--warning` `--danger` |
| Chart series | `--dl-series-1` … `--dl-series-8`, plus `--dl-series-null` |
| Spacing | `--space-1` … `--space-8` |
| Radius | `--radius` `--radius-sm` `--radius-md` `--radius-lg` `--radius-xl` `--radius-pill` |
| Type | `--font-display` `--font-sans` `--font-mono`; `--text-xs` … `--text-4xl`; `--weight-regular` … `--weight-bold` |
| Elevation | `--shadow-card` `--shadow-sm` `--shadow-md` `--shadow-lg` `--shadow-focus` |

Use `--dl-series-1..8` **in order** for chart categories. They step away in hue so
eight series stay separable, including for red-green colour vision deficiency.

**Component classes.** Two families:

- Plain: `card`, `btn` (+ `btn-primary`, `btn-danger`, `btn-ghost`, `btn-sm`),
  `badge` (+ `badge-numeric`, `badge-text`, `badge-datetime`, `badge-categorical`).
- Product chrome, in BEM (block, then element after a double underscore, then
  modifier after a double dash): `dl-shell`, `dl-rail`,
  `dl-page-head`, `dl-toolbar`, `dl-table` / `dl-table-card`, `dl-stat` / `dl-stats`,
  `dl-chip`, `dl-modal`, `dl-tree`, `dl-fold`, `dl-pager`, `dl-dash-card`,
  `dl-empty`, `dl-loading`. Follow that naming if you add a block.

**RTL is first-class.** Arabic is a supported audience, so use logical properties
only — `margin-inline-start`, `border-inline-start`, `padding-block` — never
`left`/`right`. Chart internals stay LTR while the surrounding layout flips.

**Tables**: horizontal rules only, no zebra striping or vertical rules — these
tables run long and every extra rule adds ink per row. Figures use `dl-num`, which
aligns on the decimal.

**Motion**: only movement that answers an action. Nothing animates on load.

## Where the truth lives

Read before styling: `styles.css` and the files it `@import`s hold every token with
the comments explaining *why* each value is what it is. For any component, read
`components/<group>/<Name>/<Name>.prompt.md` — each one carries its API and the
judgement about when to use it (especially the three state surfaces, which must
never be substituted for each other).

## An idiomatic screen

```jsx
const { EmptyState } = window.Datalytics;
import { Database } from 'lucide-react';

<div className="dl-shell__main" style={{ padding: 'var(--space-6)' }}>
  <div className="dl-page-head">
    <h1 className="dl-page-head__title">Datasets</h1>
    <p className="dl-page-head__sub">Sources you can build reports from.</p>
  </div>

  <EmptyState
    icon={Database}
    title="No datasets yet"
    description="Import a file or connect a source to start building reports."
    action={<button className="btn btn-primary">Add a connection</button>}
  />
</div>
```
