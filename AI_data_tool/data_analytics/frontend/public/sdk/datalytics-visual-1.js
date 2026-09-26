/*
 * Datalytics custom visual SDK, protocol version 1.
 *
 * Include it in the page a custom-visual widget points at:
 *
 *   <script src="/sdk/datalytics-visual-1.js"></script>
 *   <script>
 *     DatalyticsVisual.onData(function (data, context) { draw(data.rows, context) })
 *     // on a click in your drawing:
 *     DatalyticsVisual.select('Europe')      // filter the page by this value
 *     DatalyticsVisual.clear()               // drop the selection
 *   </script>
 *
 * `data` is the widget's shaped result (for a category/measure widget,
 * `data.rows` is [{ name, value }, ...]). `context` is { title, widget_type,
 * locale, dir, can_select, theme: { accent, text, muted, surface } }.
 * `DatalyticsVisual.host` becomes { version, capabilities } after the
 * handshake; `select` does nothing unless the host said it can.
 *
 * The page runs in a sandboxed frame (allow-scripts only): it cannot read the
 * app, its cookies or its origin, and it chooses a selection's VALUE only --
 * the column is the widget's own dimension. See docs/EXTENSIONS.md.
 */
(function (global) {
  'use strict'
  var VERSION = 1
  var listeners = []
  var last = null
  var parentWindow = global.parent

  function send(message) {
    message.version = VERSION
    // The host is the only window this frame talks to; its origin is not
    // knowable from inside a sandboxed frame, hence '*'.
    parentWindow.postMessage(message, '*')
  }

  var api = {
    version: VERSION,
    host: null,
    onData: function (callback) {
      listeners.push(callback)
      if (last) callback(last.data, last.context || {})
      return function () { listeners = listeners.filter(function (l) { return l !== callback }) }
    },
    select: function (value) {
      if (api.host && api.host.capabilities.indexOf('select') < 0) return false
      send({ type: 'datalytics:select', value: value })
      return true
    },
    clear: function () {
      if (api.host && api.host.capabilities.indexOf('clear') < 0) return false
      send({ type: 'datalytics:clear' })
      return true
    }
  }

  global.addEventListener('message', function (event) {
    if (event.source !== parentWindow) return
    var m = event.data
    if (!m || typeof m !== 'object') return
    if (m.type === 'datalytics:hello' && typeof m.version === 'number') {
      api.host = { version: m.version, capabilities: Array.isArray(m.capabilities) ? m.capabilities : [] }
    } else if (m.type === 'datalytics:data') {
      last = m
      listeners.slice().forEach(function (l) {
        try { l(m.data, m.context || {}) } catch (e) { if (global.console) global.console.error(e) }
      })
    }
  })

  global.DatalyticsVisual = api
  send({ type: 'datalytics:hello' })
})(window)
