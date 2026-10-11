import AskRobot from './AskRobot'

/**
 * The Ask AI hero picture (step 10): the robot (`AskRobot`, a full-body
 * inline SVG) with five floating cards around it -- a bar chart, a donut, a
 * chat bubble, a table and a "typing" bubble -- tied to it by dotted lines.
 * `small` is the dataset-picked hero: the same robot, smaller, without the
 * cards.
 *
 * Built from boxes and small SVGs, app tokens only (the robot's light body
 * and dark visor are tokens set in askLayout.css). The motion -- cards
 * floating, the robot's idle loop and its reactions, the dots flowing, the
 * bars regrowing -- is CSS, transform and opacity only, and stops under
 * prefers-reduced-motion. In Arabic the whole picture is mirrored, so the
 * waving arm and the glance toward the data chooser stay on the right sides.
 *
 * `look` is where the reader types: the question box under the picture
 * (`down`) or the data chooser beside it (`side`).
 *
 * Purely decorative: the headline under it carries the meaning.
 */
export default function AskIllustration({ small = false, look = 'down' }: { small?: boolean; look?: 'down' | 'side' }) {
  if (small) {
    return (
      <div className="dl-ill dl-ill--sm" aria-hidden="true">
        <div className="dl-ill__stage"><AskRobot look={look} /></div>
      </div>
    )
  }
  return (
    <div className="dl-ill" aria-hidden="true">
      <div className="dl-ill__stage">
      <div className="dl-ill__glow" />
      <svg className="dl-ill__lines" viewBox="0 0 460 284" fill="none">
        <g className="dl-ill__dash">
          <path d="M140 84Q156 92 164 104" /><path d="M342 80Q320 86 302 100" />
          <path d="M138 204Q160 204 180 194" /><path d="M318 214Q304 212 292 204" />
        </g>
        <g className="dl-ill__dots">
          <circle cx="140" cy="84" r="3" /><circle cx="342" cy="80" r="3" />
          <circle cx="138" cy="204" r="3" /><circle cx="318" cy="214" r="3" />
        </g>
      </svg>
      <div className="dl-ill__card dl-ill__c1">
        <div className="dl-ill__ln" style={{ width: '56%' }} />
        <div className="dl-ill__bars">
          {[44, 66, 52, 92, 60].map((h, i) => (
            <i key={i} className={i === 3 ? 'is-accent' : undefined} style={{ height: `${h}%`, ['--b' as string]: i }} />
          ))}
        </div>
      </div>
      <div className="dl-ill__card dl-ill__c2">
        <svg viewBox="0 0 64 64" width="70" height="70">
          <circle cx="32" cy="32" r="24" className="dl-ill__ring" />
          <circle cx="32" cy="32" r="24" className="dl-ill__ring is-accent" strokeDasharray="57 151" transform="rotate(-90 32 32)" />
          <circle cx="32" cy="32" r="24" className="dl-ill__ring is-strong" strokeDasharray="40 151" strokeDashoffset="-60" transform="rotate(-90 32 32)" />
          <circle cx="32" cy="32" r="24" className="dl-ill__ring is-muted" strokeDasharray="28 151" strokeDashoffset="-103" transform="rotate(-90 32 32)" />
        </svg>
      </div>
      <div className="dl-ill__card dl-ill__c3">
        <div className="dl-ill__ln" style={{ width: '88%', ['--n' as string]: 0 }} />
        <div className="dl-ill__ln" style={{ width: '62%', ['--n' as string]: 1 }} />
        <div className="dl-ill__ln is-soft" style={{ width: '74%', ['--n' as string]: 2 }} />
      </div>
      <div className="dl-ill__card dl-ill__c4">
        {[0, 1, 2, 3].map(r => (
          <div key={r} className={`dl-ill__tr${r === 0 ? ' is-head' : ''}`}>
            <div className="dl-ill__ln" /><div className={`dl-ill__ln${r === 1 ? ' is-accent' : ''}`} /><div className="dl-ill__ln" />
          </div>
        ))}
      </div>
      <div className="dl-ill__card dl-ill__c5"><i /><i /><i /></div>
      <AskRobot look={look} />
      </div>
    </div>
  )
}
