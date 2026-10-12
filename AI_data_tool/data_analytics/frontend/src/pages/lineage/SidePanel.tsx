import { Link } from 'react-router-dom'
import { ArrowLeftToLine, ArrowRightFromLine, ArrowUpRight, Info, Sparkles, TriangleAlert, X } from 'lucide-react'
import { formatTimeAgo, useT, type TranslateFn } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { NodeIcon, useNodeText } from './Graph'
import { UPLOADS, downstream, sourceTypeName, type LNode, type Model } from './model'

/** Where a node opens, and what Ask AI can be asked about. */
export function openLink(n: LNode): string | null {
  if (n.key === UPLOADS) return null
  return n.col === 0 ? '/connections' : n.col === 1 ? `/datasets/${n.id}` : `/reports/${n.id}`
}
function askLink(n: LNode): string | null {
  if (n.key === UPLOADS || n.col === 2) return null
  return n.col === 0 ? `/ask?source=${n.id}` : `/ask?dataset=${n.id}`
}

/**
 * The focused node's details (step 11, design `side()`): what a change to it
 * would touch, what it is, its status, what it feeds from and what uses it,
 * then Open and Ask AI. Owner, creation date and row count are not in the
 * lineage graph, so they are not shown (backend row).
 */
/** QAF M4: what a change would touch, with any zero part left out, so no
 *  language can read "no datasets and 9 reports" as "nothing is affected". */
export function impactText(t: TranslateFn, name: string, ds: number, rep: number): string {
  if (ds && rep) return t('qaf.lin.impactBoth', { name, ds, rep })
  if (ds) return t('qaf.lin.impactDs', { name, ds })
  return t('qaf.lin.impactRep', { name, rep })
}

export default function SidePanel({ model, node, onSelect, onClose }: {
  model: Model
  node: LNode
  onSelect: (key: string) => void
  onClose: () => void
}) {
  const t = useT()
  const text = useNodeText()
  const up = model.edges.filter(e => e.to === node.key).map(e => model.byKey[e.from])
  const used = model.edges.filter(e => e.from === node.key).map(e => model.byKey[e.to])
  const down = [...downstream(model.edges, node.key)].map(k => model.byKey[k])
  const nDs = down.filter(n => n.col === 1).length, nRep = down.filter(n => n.col === 2).length

  const type = node.col === 0 ? (node.sourceType === 'file' ? t('lin2.file') : sourceTypeName(node.sourceType))
    : node.col === 1 ? text.mode(node) : t('lin2.kind.report')
  const refreshed = node.col !== 1 || node.fromFile ? null
    : node.mode === 'directquery' ? t('lin2.live')
    : node.never || !node.refreshed ? t('lin2.never')
    : localDigits(formatTimeAgo(node.refreshed, t) ?? '')
  const status = node.issue ? text.issue(node) : node.col === 0 ? t('qaf.lin.notChecked') : t('lin2.st.ok')
  const dot = node.issue === 'fail' || node.issue === 'broken' ? 'err' : node.issue ? 'warn' : node.col === 0 ? 'none' : 'ok'

  const list = (nodes: LNode[], none: string) => nodes.length ? (
    <ul>
      {nodes.map(n => (
        <li key={n.key}>
          <button type="button" onClick={() => onSelect(n.key)}>
            <NodeIcon n={n} size={26} /><span className="dl-ln-side__n2" dir="auto">{n.name}</span><small>{text.kind(n)}</small>
          </button>
        </li>
      ))}
    </ul>
  ) : <p className="dl-ln-side__none">{none}</p>
  const open = openLink(node), ask = askLink(node)

  return (
    <aside className="dl-ln-side" aria-labelledby="dl-ln-side-h">
      <header>
        <NodeIcon n={node} size={40} />
        <div className="dl-ln-side__tx">
          <span className="dl-ln-side__kind">{text.kind(node)}</span>
          <h2 id="dl-ln-side-h" dir="auto">{node.name}</h2>
        </div>
        <button type="button" className="dl-ln-ib" aria-label={t('lin2.close')} title={t('lin2.close')} onClick={onClose}><X size={16} aria-hidden /></button>
      </header>
      <div className="dl-ln-side__bd">
        {down.length ? (
          <div className="dl-ln-imp" role="note"><TriangleAlert size={16} aria-hidden />
            <p>{localDigits(impactText(t, node.name, nDs, nRep))}</p></div>
        ) : (
          <div className="dl-ln-imp is-calm" role="note"><Info size={16} aria-hidden /><p>{t('lin2.impactNone')}</p></div>
        )}
        <dl className="dl-ln-meta">
          <dt>{t('lin2.m.type')}</dt><dd dir="auto">{type}</dd>
          {refreshed != null && <><dt>{t('lin2.m.refreshed')}</dt><dd>{refreshed}</dd></>}
          {!!node.steps && <><dt>{t('lin2.m.steps')}</dt><dd>{localDigits(t('lin2.steps', { n: node.steps }))}</dd></>}
          <dt>{t('lin2.m.status')}</dt><dd><span className={`dl-ln-sdot dl-ln-sdot--${dot}`} aria-hidden />{status}</dd>
        </dl>
        <section className="dl-ln-side__lst">
          <h3><ArrowLeftToLine size={13} aria-hidden className="dl-flip" />{t('lin2.feeds')}<span dir="ltr">{localDigits(String(up.length))}</span></h3>
          {list(up, t('lin2.nothingUp'))}
        </section>
        <section className="dl-ln-side__lst">
          <h3><ArrowRightFromLine size={13} aria-hidden className="dl-flip" />{t('lin2.usedBy')}<span dir="ltr">{localDigits(String(used.length))}</span></h3>
          {list(used, t('lin2.nothingDown'))}
        </section>
      </div>
      {(open || ask) && (
        <footer>
          {open && <Link to={open} className="btn btn-primary"><ArrowUpRight size={16} aria-hidden className="dl-flip" /> {t('lin2.open')}</Link>}
          {ask && <Link to={ask} className="btn btn-ghost"><Sparkles size={16} aria-hidden /> {t('lin2.ask')}</Link>}
        </footer>
      )}
    </aside>
  )
}
