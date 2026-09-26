/**
 * Text direction by content for form controls (QA 2026-09-26).
 *
 * In the Arabic UI every control inherits `direction: rtl`. A control holding
 * Latin text -- a widget title like "price moves with price (copy)", a column
 * name in a select -- then anchors at the right and overflows to the LEFT, so
 * the reader sees "ves with price (copy)": the START of the value is what gets
 * cut. `dir="auto"` fixes inputs and textareas (the browser picks the
 * direction from the value). A <select> does not follow its selected option,
 * so its direction is set here from the selected option's first strong
 * character, and re-checked whenever the DOM or a value changes.
 *
 * Inputs and textareas follow their value (or placeholder when empty), with
 * the same first-strong-character rule. Any element marked
 * `data-autodir-text` (a one-line label with an ellipsis) is handled too.
 * Controls with an explicit `dir` are left alone, as are non-text inputs.
 */

const TEXT_TYPES = new Set(['', 'text', 'search', 'email', 'url', 'tel'])
const RTL_CHAR = /[֐-ࣿיִ-﷿ﹰ-﻿]/
const LTR_CHAR = /[A-Za-zÀ-ɏͰ-ϿЀ-ӿ]/
const MANAGED = 'data-autodir'

function firstStrongDir(text: string): 'ltr' | 'rtl' | null {
  for (const ch of text) {
    if (RTL_CHAR.test(ch)) return 'rtl'
    if (LTR_CHAR.test(ch)) return 'ltr'
  }
  return null
}

function fix(el: Element): void {
  const explicit = el.hasAttribute('dir') && !el.hasAttribute(MANAGED)
  if (explicit) return
  let text: string
  if (el instanceof HTMLInputElement) {
    if (!TEXT_TYPES.has((el.getAttribute('type') || '').toLowerCase())) return
    // Empty: follow the placeholder, so an Arabic hint stays right-aligned.
    text = el.value || el.placeholder
  } else if (el instanceof HTMLTextAreaElement) {
    text = el.value || el.placeholder
  } else if (el instanceof HTMLSelectElement) {
    text = el.options[el.selectedIndex]?.text ?? ''
  } else {
    // Any element marked data-autodir-text: a one-line label with ellipsis.
    text = el.textContent ?? ''
  }
  {
    const want = firstStrongDir(text)
    if (want === null) {
      if (el.hasAttribute(MANAGED)) { el.removeAttribute('dir'); el.removeAttribute(MANAGED) }
      return
    }
    if (el.getAttribute('dir') !== want) el.setAttribute('dir', want)
    el.setAttribute(MANAGED, '')
  }
}

function sweep(root: ParentNode = document): void {
  root.querySelectorAll('input, textarea, select, [data-autodir-text]').forEach(fix)
}

let installed = false

export function installAutoDir(): void {
  if (installed || typeof document === 'undefined' || typeof MutationObserver === 'undefined') return
  installed = true
  let queued = false
  const schedule = () => {
    if (queued) return
    queued = true
    queueMicrotask(() => { queued = false; sweep() })
  }
  new MutationObserver(schedule).observe(document.documentElement, {
    subtree: true, childList: true, characterData: true,
  })
  // A controlled <select> changes value without touching the DOM tree.
  for (const ev of ['change', 'input', 'focusin', 'click']) {
    document.addEventListener(ev, schedule, true)
  }
  schedule()
}
