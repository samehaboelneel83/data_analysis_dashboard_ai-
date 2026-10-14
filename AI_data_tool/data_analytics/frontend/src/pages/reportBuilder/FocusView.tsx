import type { ReactNode } from 'react'
import { ArrowLeft, CornerDownRight } from 'lucide-react'
import AiMascot from '../../components/ai/AiMascot'
import { useModalDialog } from '../../components/ui/useModalDialog'
import { useT } from '../../i18n'
import type { Widget } from '../../types/report'

/**
 * One widget, full screen (redesign 7d): the chart large, and questions to
 * ask about it. The widget is the same WidgetRenderer with the same props, so
 * its own menu (data export, view as, analyse) is all still there.
 * "Data behind this chart" is left out: the table would need the widget's
 * query rebuilt outside WidgetRenderer, which stays untouched.
 */
export default function FocusView({ widget, render, onClose, onAsk, askDisabled }: {
  widget: Widget
  render: (w: Widget) => ReactNode
  onClose: () => void
  onAsk: (question: string) => void
  /** While the model server is unreachable: questions are shown, not sent. */
  askDisabled?: boolean
}) {
  const t = useT()
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const title = widget.title || widget.widget_type
  const questions = [t('vw.fq.explain', { title }), t('vw.fq.stands', { title }), t('vw.fq.driving', { title })]
  return (
    <div ref={ref} className="dl-vw-fx" role="dialog" aria-modal="true" aria-labelledby="dl-vw-fx-t" data-testid="focus-view">
      <div className="dl-vw-fx__h">
        <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}><ArrowLeft size={14} className="flip" aria-hidden />{t('vw.fx.exit')}</button>
        <h2 id="dl-vw-fx-t"><bdi>{title}</bdi></h2>
        <button type="button" className="btn btn-ghost btn-sm" disabled={askDisabled} onClick={() => onAsk(questions[0])}>
          <span className="dl-vw-av" aria-hidden><AiMascot size={16} /></span>{t('nav.askAi')}
        </button>
      </div>
      <div className="dl-vw-fx__b">
        <div className="dl-vw-fx__w">{render({ ...widget, layout: { ...widget.layout, x: 0, y: 0 } })}</div>
        <div className="dl-vw-fx__s">
          <section className="dl-vw-fx__card">
            <h3>{t('vw.fx.ask')}</h3>
            {askDisabled && <p role="status">{t('off.composer')}</p>}
            {questions.map(q => (
              <button key={q} type="button" className="dl-vw-q" disabled={askDisabled} onClick={() => onAsk(q)}>
                <CornerDownRight size={14} className="flip" aria-hidden /><span>{q}</span>
              </button>
            ))}
          </section>
          <section className="dl-vw-fx__card"><p>{t('vw.fx.menuNote')}</p></section>
        </div>
      </div>
    </div>
  )
}
