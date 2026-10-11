/**
 * The Ask AI hero picture (step 10, from the design handoff's `ill()`): a
 * small assistant -- a light rounded head with a dark glowing screen face,
 * an antenna and a torso -- with five floating cards around it (a bar chart,
 * a donut, a chat bubble, a table and a "typing" bubble), tied to it by
 * dotted lines.
 *
 * Built from boxes and two small SVGs, app tokens only (the robot's light
 * body and dark screen are tokens set in askLayout.css, the same in both
 * themes). The motion -- cards floating, the robot bobbing and blinking, the
 * antenna pulsing, the dots flowing, the bars regrowing -- is CSS, transform
 * and opacity only, and stops under prefers-reduced-motion.
 *
 * Purely decorative: the headline under it carries the meaning.
 */
export default function AskIllustration({ small = false }: { small?: boolean }) {
  return (
    <div className={`dl-ill${small ? ' dl-ill--sm' : ''}`} aria-hidden="true">
      <div className="dl-ill__glow" />
      <svg className="dl-ill__lines" viewBox="0 0 460 240" fill="none">
        <g className="dl-ill__dash">
          <path d="M156 70Q190 84 198 104" /><path d="M326 64Q290 76 262 100" />
          <path d="M150 186Q176 182 196 164" /><path d="M314 180Q288 176 266 160" />
        </g>
        <g className="dl-ill__dots">
          <circle cx="156" cy="70" r="3" /><circle cx="326" cy="64" r="3" />
          <circle cx="150" cy="186" r="3" /><circle cx="314" cy="180" r="3" />
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
      <div className="dl-ill__bot">
        <div className="dl-ill__ant" />
        <div className="dl-ill__head">
          <span className="dl-ill__ear is-l" /><span className="dl-ill__ear is-r" />
          <div className="dl-ill__face">
            <svg viewBox="0 0 100 70">
              <rect x="29" y="19" width="11" height="16" rx="5.5" />
              <rect x="60" y="19" width="11" height="16" rx="5.5" />
              <path d="M36 45Q50 56 64 45" />
            </svg>
          </div>
        </div>
        <div className="dl-ill__torso" />
        <div className="dl-ill__shadow" />
      </div>
    </div>
  )
}
