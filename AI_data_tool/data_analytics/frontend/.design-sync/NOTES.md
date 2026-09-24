# design-sync notes — datalytics-frontend

Repo-specific gotchas for future syncs. Read this before re-running.

## What is synced, and why it is only seven components

This repo is the Datalytics **app**, not a component library: `private: true`, no
`main`/`module`/`exports`, and `dist/` is a Vite app build. The design system in it
is the MCAIT token layer plus the primitives in `src/components/ui/`.

Those eight files are not eight components:

- Five are visual: `EmptyState`, `IconLabel`, `LoadError`, `Loader`, `LoadingState`.
- Two are imperative dialog providers: `ConfirmProvider` (+ `useConfirm`) and
  `PromptProvider` (+ `usePrompt`).
- `ListFilter.tsx` exports only `matches` and `useListFilter`, and
  `useModalDialog.ts` only a hook — **no components at all**, so they are not
  synced. A card for a hook is noise.

The other ~220 `.tsx` under `src/components/` are app screens wired to
react-router, `AuthContext` and the API services. They are not reusable parts and
are deliberately out of scope. The 47 renderers under
`src/components/report/chartRenderers/` ARE presentational and would be a
reasonable future addition — each needs an authored preview with realistic data.

## The two things that will break if you skip them

**1. Run `node .design-sync/prepare-css.mjs` before every converter build.**
`cfg.cssEntry` copies ONE file and does not follow `@import`. `src/index.css` is
only a bridge — it imports the five MCAIT token files, the product theme and the
font declarations. Pointing `cssEntry` straight at it ships a stylesheet where
every `var(--mc-*)` resolves to nothing, with no error anywhere. `cfg.tokensGlob`
cannot help: `copyTokens()` returns early unless `cfg.tokensPkg` names a package
under `node_modules`, and these tokens live in `src/styles/`.
`ds-styles.css` is generated and gitignored; the script is committed.

**2. The script also anchors the product theme at `:root`.** Every Datalytics token
is scoped under `[data-product="datalytics"]`, which the app stamps on `<html>` in
`index.html`. Nothing outside the app does that, so designs would render
off-brand and silently. Each such selector gets a `:root` twin; the original
attribute scoping still works. Verified live: the Loader's dots go from MCAIT gold
to Datalytics teal once the twins are in.

## Build environment

- **Node is 18.14.1 here; Playwright ≥1.46 requires Node 20.** `playwright@1.45.3`
  is pinned in `.ds-sync/` for the render check. If you upgrade Node, drop the pin.
  Chromium lives in the shared `ms-playwright` cache, not in the repo.
- The converter is run with an explicit `--entry .design-sync/ds-entry.tsx`. Do not
  let it fall back to synth-entry mode: that synthesizes `export * from` **every**
  file under `src/`, pulling the whole 275-component app (router, axios, contexts)
  into the uploaded bundle. With the pinned entry the bundle is 22 KB.
- `--node-modules ./node_modules` (the frontend's own).

Full command sequence:

```bash
node .design-sync/prepare-css.mjs
node .ds-sync/package-build.mjs --config .design-sync/config.json \
  --node-modules ./node_modules --entry .design-sync/ds-entry.tsx --out ./ds-bundle
node .ds-sync/package-validate.mjs ./ds-bundle
```

## Other findings

- **`dtsPropsFor` carries all seven prop contracts by hand.** With no library build
  there is no `.d.ts` tree to extract from, so every `<Name>Props` came out as
  `{ [key: string]: unknown }` — no API contract for the design agent at all.
  If a component's props change in source, update `cfg.dtsPropsFor` too; nothing
  checks that they still agree.
- `cfg.docsDir` points at `.design-sync/docs/`, hand-written. The `category`
  frontmatter is what groups components into State / Overlays / Primitives;
  without it everything lands in `general`.
- `ConfirmProvider` and `PromptProvider` use `position: fixed`, so their previews
  trip `[GRID_OVERFLOW]`. Resolved with `cardMode: "single"` in `cfg.overrides` —
  keep it if you add more dialog components.
- The `rtk` shell wrapper intercepts `grep -h` and some bracket patterns; several
  audits in this repo are easier to run through `node -e`.

## Re-sync risks

- **`prepare-css.mjs` is a copy of the converter's blind spot, not a fork of it.**
  If a future converter version follows `@import` itself, this script becomes
  redundant and the `:root` twinning is the only part still needed.
- **The `:root` twinning is a deliberate deviation from shipped CSS.** It is the
  one place where what is uploaded differs semantically from what the app loads.
  If MCAIT ever ships a second product theme into this same bundle, the twins
  would make Datalytics win at `:root` — revisit then.
- **`.design-sync/previews/` and `docs/` are hand-written** and tied to the current
  props. They do not fail loudly when the component changes underneath them; the
  render check only proves something rendered, not that it still shows the right
  thing. Re-read the contact sheet on any re-sync.
- **First import landed 2026-09-24** into the design-system project
  `Datalytics` (`projectId` 9ea2d07d-0167-4ef6-b852-cdd0706d8819, now recorded in
  `config.json`). 51 files: the 28 under `components/`, 7 `_preview/*.js`, 8
  `fonts/`, 2 `_vendor/`, `_ds_bundle.{js,css}`, `styles.css`, `README.md`,
  `_ds_sync.json` and `_ds_needs_recompile`. **The next run is a re-sync**: fetch
  the remote `_ds_sync.json` anchor with `DesignSync get_file` into a local file
  and pass it to `resync.mjs --remote`, or the diff sees no anchor and re-uploads
  everything.
- **An earlier version of this file recorded the import as landed under `projectId`
  `96dd91af-…`. It had not been.** That id was written down before the upload was
  authorized, and `create_project` never ran; `get_project` on it returns 404 and
  `list_projects` was empty. The real first import is the one above, pushed once
  `/design-login` was authorized. Verify a "landed" claim with `list_projects`
  before trusting it — the local anchor in `_ds_sync.json` is content-hashed and
  carries no project id, so it cannot tell you where, or whether, it went.
- **`_screenshots/` and the dotfiles are local-only** and were deliberately left
  out of the upload: `.ds-bundle`, `.ds-build-meta.json`, `.render-check.json`,
  `.review.html`, `.stories-map.json`. Keep that exclusion — they are build/QA
  artifacts, not part of the design system.
- **Known render warns: none.** The 2026-09-24 re-sync's render check was clean
  across all 7 components (`bad`/`thin`/`variantsIdentical` all 0, no `[TAG]`
  warn lines at all). Any warn line on a future run is therefore NEW - look at
  it rather than assuming it was always there.

- **The conventions header carries a token COUNT, and a count rots.** It read
  "all 162 tokens resolve at `:root`"; the 2026-09-24 token work made it 159 at
  `:root` of 164 total. Recount before trusting it: strip `/* */` comments
  FIRST, then walk braces with a depth-tracking parser. A naive
  `/([^{}]+)\{([^{}]*)\}/` regex gets this wrong twice over - it cannot nest
  through `@media`, and it reads a block's leading comment as its selector, so
  it reports tokens as declared under a comment and `:root` twins as absent.
  Both misreads look like real breakage and cost a debugging cycle each.

- **4 custom properties are deliberately NOT at `:root`**, and should stay that
  way: `--mc-product-name` (a different product, `[data-product="cowork"]`),
  `.dl-loader`'s `--dl-ball`/`--dl-rise`, and `--dl-shell-pad`. They are
  component internals, not theme vocabulary.

- **`--dl-stat-tint` is gone on purpose (2026-09-24).** The stat tiles used to
  route their colour through a `--dl-stat-tint` custom property set on each
  `.dl-stat__icon--*` modifier. The design-system check flags custom properties
  declared on component classes, so each variant now sets `color` and its 12%
  `color-mix` background directly from `--dl-series-5`/`-7`. Do not reintroduce
  the indirection. There was never a FOURTH `--dl-stat-tint` declaration: the
  check's fourth hit in that category is `.dl-loader`'s `--dl-ball`/`--dl-rise`,
  which are animation geometry and were deliberately left alone.

- **No `register_assets` call is needed.** All seven preview HTMLs carry a
  first-line `<!-- @dsCard group="…" -->` marker, which the pane compiles into
  `_ds_manifest.json` itself. `guidelines/` is empty, so `auxShaFor` currently
  hashes only `README.md`.
