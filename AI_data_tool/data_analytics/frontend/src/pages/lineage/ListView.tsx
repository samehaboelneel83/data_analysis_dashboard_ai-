import { Fragment, useState } from 'react'
import { ArrowRight, ChevronRight } from 'lucide-react'
import { formatTimeAgo, useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { NodeIcon, useNodeText } from './Graph'
import { downstream, type LNode, type Model } from './model'

/**
 * The same estate as a table (step 11, design `listView()`): each node with
 * its type, how many things feed it and how many it reaches, its last refresh
 * and its status. A row opens to its whole chain, upstream → it → downstream.
 * Filters keep only what passes them. The name shows the node in the graph.
 */
export default function ListView({ model, nodes, onShow, selected }: { model: Model; nodes: LNode[]; onShow: (key: string) => void; selected?: string | null }) {
  const t = useT()
  const text = useNodeText()
  const [open, setOpen] = useState<Set<string>>(new Set())
  const upstream = (key: string) => {
    const out = new Set<string>(), stack = [key]
    while (stack.length) { const cur = stack.pop()!; for (const e of model.edges) if (e.to === cur && !out.has(e.from)) { out.add(e.from); stack.push(e.from) } }
    return out
  }
  const byCol = (keys: Set<string>) => [...keys].map(k => model.byKey[k]).sort((a, b) => a.col - b.col)
  // QAF 19: one rule with the side panel -- a file upload is never refreshed,
  // whether or not its upload left a time behind.
  const refreshed = (n: LNode) => n.col !== 1 || n.fromFile ? '—' : n.mode === 'directquery' ? t('lin2.live')
    : n.never || !n.refreshed ? t('lin2.never') : localDigits(formatTimeAgo(n.refreshed, t) ?? '')
  // QAF 22: the graph knows nothing of a connection's health; a source is
  // neither green nor "Connected" here (Connections tests it).
  const dot = (n: LNode) => (n.issue === 'fail' || n.issue === 'broken' ? 'err' : n.issue ? 'warn' : n.col === 0 ? 'none' : 'ok')
  const chip = (n: LNode, me: LNode) => <span key={n.key} className={`dl-ln-chain__c${n === me ? ' is-me' : ''}`} dir="auto">{n.name}</span>

  if (!nodes.length) return <p className="dl-ln-list__none">{t('lin2.l.none')}</p>
  return (
    <div className="dl-ln-list">
      <table>
        <thead>
          <tr>
            <th className="dl-ln-list__x"><span className="dl-sr-only">{t('lin2.l.expand', { name: '' })}</span></th>
            <th>{t('lin2.l.item')}</th><th>{t('lin2.m.type')}</th>
            <th className="is-num">{t('lin2.l.up')}</th><th className="is-num">{t('lin2.l.down')}</th>
            <th>{t('lin2.m.refreshed')}</th><th>{t('lin2.m.status')}</th>
          </tr>
        </thead>
        <tbody>
          {nodes.map(n => {
            const x = open.has(n.key)
            const ups = byCol(upstream(n.key)), downs = byCol(downstream(model.edges, n.key))
            return (
              <Fragment key={n.key}>
                {/* QAF 19: the focused node stays marked across Graph and List. */}
                <tr className={n.key === selected ? 'is-focus' : undefined} aria-current={n.key === selected ? 'true' : undefined}
                  ref={n.key === selected ? (el => el?.scrollIntoView?.({ block: 'nearest' })) : undefined}>
                  <td>
                    <button type="button" className="dl-ln-ib dl-ln-ib--sm dl-ln-list__xb" aria-expanded={x}
                      aria-label={t('lin2.l.expand', { name: n.name })}
                      onClick={() => setOpen(s => { const next = new Set(s); if (next.has(n.key)) next.delete(n.key); else next.add(n.key); return next })}>
                      <ChevronRight size={15} aria-hidden className="dl-flip" />
                    </button>
                  </td>
                  <td>
                    <span className="dl-ln-list__nm">
                      <NodeIcon n={n} size={28} />
                      <button type="button" className="dl-ln-list__link" dir="auto" aria-label={t('lin2.l.showInGraph', { name: n.name })}
                        onClick={() => onShow(n.key)}>{n.name}</button>
                    </span>
                  </td>
                  <td className="is-muted">{n.col === 1 ? text.mode(n) : text.kind(n)}</td>
                  <td className="is-num" dir="ltr">{localDigits(String(model.edges.filter(e => e.to === n.key).length))}</td>
                  <td className="is-num" dir="ltr">{localDigits(String(downs.length))}</td>
                  <td className="is-muted" title={n.fromFile ? t('qaf.lin.fileNoRefresh') : undefined}>{refreshed(n)}</td>
                  <td><span className="dl-ln-list__st"><span className={`dl-ln-sdot dl-ln-sdot--${dot(n)}`} aria-hidden />
                    {n.issue ? text.issue(n) : n.col === 0 ? t('qaf.lin.notChecked') : t('lin2.st.ok')}</span></td>
                </tr>
                {x && (
                  <tr className="dl-ln-list__chainrow">
                    <td />
                    <td colSpan={6}>
                      <div className="dl-ln-chain">
                        {ups.length > 0 && <><span className="dl-ln-chain__g">{ups.map(u => chip(u, n))}</span><ArrowRight size={14} aria-hidden className="dl-flip" /></>}
                        {chip(n, n)}
                        {downs.length > 0 && <><ArrowRight size={14} aria-hidden className="dl-flip" /><span className="dl-ln-chain__g">{downs.map(d => chip(d, n))}</span></>}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
