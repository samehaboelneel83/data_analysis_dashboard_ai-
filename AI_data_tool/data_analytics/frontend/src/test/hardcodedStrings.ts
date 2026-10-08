import ts from 'typescript'
import fs from 'node:fs'

/**
 * QA3 Batch C: English a reader can see, written straight into a component
 * instead of going through the translator (`t`/`tr`, the panel's `L`).
 *
 * Looked for: JSX text; the attributes a reader sees or hears (title,
 * aria-label, placeholder, alt, label); the messages of toasts and
 * confirm/prompt dialogs; and UI-named properties in data (`label:`, `title:`,
 * `placeholder:`, `hint:` …), as in menu items and option lists. Not looked for: anything passed to a translator,
 * class names, keys, test ids, values sent to the server.
 *
 * A line ending in `// i18n-ok` is skipped, for the rare literal that is not
 * English prose (a unit, a product name, a code sample).
 */
export interface Hit { line: number; text: string }

const SEEN_ATTRS = new Set(['title', 'aria-label', 'placeholder', 'alt', 'label', 'aria-description'])
const UI_PROPS = /^['"]?(label|title|placeholder|tooltip|hint|description|text|help|empty|ariaLabel)['"]?$/
const MESSAGE_CALLS = /^(toast(\.(success|error|loading))?|confirm|prompt|ask)$/
// Two or more letters in a row is a word; "x", "×", "#" and "Aa" glyphs are not prose.
const WORDS = /[A-Za-z]{2,}/
const NOT_PROSE = /^(Aa|ƒx|px|ms|id|ok|OK|AI|CSV|XLSX|PDF|PNG|SQL|URL|KPI|Ctrl|Shift|Alt|Enter|Esc|Tab|Datalytics)$/

function prose(s: string): boolean {
  const t = s.trim()
  if (!t || !WORDS.test(t)) return false
  // A message key ('bd.rail.properties') is what the translator is given.
  if (/^[a-z][A-Za-z0-9]*(\.[A-Za-z0-9_{}-]+)+$/.test(t)) return false
  return !NOT_PROSE.test(t)
}

export function hardcodedStrings(file: string): Hit[] {
  const src = fs.readFileSync(file, 'utf8')
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const lines = src.split('\n')
  const hits: Hit[] = []
  const add = (node: ts.Node, text: string) => {
    const line = sf.getLineAndCharacterOfPosition(node.getStart()).line
    if (/\/\/\s*i18n-ok/.test(lines[line] ?? '')) return
    hits.push({ line: line + 1, text: text.trim().slice(0, 80) })
  }
  const literal = (e: ts.Expression | undefined): string | null => {
    if (!e) return null
    if (ts.isStringLiteral(e) || ts.isNoSubstitutionTemplateLiteral(e)) return e.text
    if (ts.isTemplateExpression(e)) return [e.head.text, ...e.templateSpans.map(s => s.literal.text)].join(' ')
    if (ts.isParenthesizedExpression(e)) return literal(e.expression)
    if (ts.isConditionalExpression(e)) return [literal(e.whenTrue), literal(e.whenFalse)].filter(Boolean).join(' ') || null
    if (ts.isBinaryExpression(e) && e.operatorToken.kind === ts.SyntaxKind.PlusToken) return [literal(e.left), literal(e.right)].filter(Boolean).join(' ') || null
    return null
  }
  const visit = (node: ts.Node) => {
    if (ts.isJsxText(node) && prose(node.text)) add(node, node.text)
    else if (ts.isJsxExpression(node) && node.parent && (ts.isJsxElement(node.parent) || ts.isJsxFragment(node.parent))) {
      const s = literal(node.expression)
      if (s != null && prose(s)) add(node, s)
    } else if (ts.isJsxAttribute(node) && SEEN_ATTRS.has(node.name.getText(sf))) {
      const init = node.initializer
      const s = !init ? null : ts.isStringLiteral(init) ? init.text : ts.isJsxExpression(init) ? literal(init.expression) : null
      if (s != null && prose(s)) add(node, s)
    } else if (ts.isCallExpression(node) && MESSAGE_CALLS.test(node.expression.getText(sf))) {
      const first = node.arguments[0]
      const s = literal(first)
      if (s != null && prose(s)) add(node, s)
      if (first && ts.isObjectLiteralExpression(first)) {
        for (const p of first.properties) {
          if (ts.isPropertyAssignment(p) && /^(title|message|body|confirmLabel|cancelLabel|label)$/.test(p.name.getText(sf))) {
            const v = literal(p.initializer)
            if (v != null && prose(v)) add(p, v)
          }
        }
      }
    }
    // Menu items, option lists and the like: `{ label: 'Duplicate widget' }`.
    if (ts.isPropertyAssignment(node) && UI_PROPS.test(node.name.getText(sf))
        && !(node.parent?.parent && ts.isCallExpression(node.parent.parent) && MESSAGE_CALLS.test(node.parent.parent.expression.getText(sf)))) {
      const v = literal(node.initializer)
      if (v != null && prose(v)) add(node, v)
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  return hits
}
