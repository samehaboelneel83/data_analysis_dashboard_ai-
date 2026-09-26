# Custom visuals: the extension protocol (version 1)

A **custom visual** widget shows a page you host, in a sandboxed frame, fed
with the widget's data. This page is the contract between that page and the
app: what the app sends, what the page may send back, and how versions work.

## Quick start

```html
<script src="/sdk/datalytics-visual-1.js"></script>
<script>
  DatalyticsVisual.onData(function (data, context) {
    draw(data.rows, context)                  // [{ name, value }, ...]
  })
  // on a click in your drawing:
  DatalyticsVisual.select('Europe')           // filter the page by this value
  DatalyticsVisual.clear()                    // drop the selection
</script>
```

`/sdk/example-bars.html` is a complete example: bars in the report's accent
colour, numbers in the reader's language, a click filters the page. Point a
custom visual widget's URL at it to see it work.

## Messages

All messages are `postMessage` objects with a `type` and a `version`.

| From | Type | Fields | When |
|---|---|---|---|
| visual | `datalytics:hello` | `version` | On load (the SDK sends it). |
| app | `datalytics:hello` | `version`, `capabilities` (`["select", "clear"]`, or `[]` when the page's interactions forbid it) | In reply, followed by the data. |
| app | `datalytics:data` | `version`, `data` (the widget's shaped result), `context` | On load, on hello, and whenever the data changes. |
| visual | `datalytics:select` | `value` | The reader picked a value. |
| visual | `datalytics:clear` | | The reader dropped the selection. |

`context` is `{ title, widget_type, locale, dir, can_select, theme: { accent, text, muted, surface } }`:
the widget's title, the reader's language (`en`, `ar`) and direction (`ltr`,
`rtl`), whether a selection will be acted on, and the theme's colours (the
frame cannot read the app's styles).

`data` is the same result the built-in charts draw. For a widget with a
dimension and a measure it is `{ rows: [{ name, value }, ...] }`; bind them
in the widget's settings.

## What a visual can and cannot do

- The frame is `sandbox="allow-scripts"`: an opaque origin, no access to the
  app, its cookies, its storage or its requests. It sees only the data the
  widget sends, which the reader's row and column rules have already shaped.
- The app accepts messages only from that frame's own window (identity, not
  origin: every sandboxed frame's origin is `null`).
- A selection carries a **value** only. The app applies it to the widget's own
  dimension, through the same path as a click on a bar: a visual cannot name
  another column, and cannot filter a page whose interactions forbid it. A
  `column` in the message is ignored.
- The page must be `https://…`, `http://…` or a path on this server (`/…`).

## Versions

- Within version 1, changes are additive only: a new optional field in
  `context`, a new message type a visual may ignore. A visual written against
  version 1 keeps working.
- Anything else is version 2, served as `/sdk/datalytics-visual-2.js`, with the
  app answering each visual's hello in the version it asked for.
- A page written before the protocol had versions (one that only listens for
  `datalytics:data` and reads `data`) keeps working: the message still carries
  `data` in the same place.
