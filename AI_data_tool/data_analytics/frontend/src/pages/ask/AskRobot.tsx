import { useId } from 'react'
import { useRobotMood } from './robotMood'

/**
 * The Ask AI robot: an original full-body drawing -- a round helmet head with
 * a dark glossy visor and two round glowing eyes, ear pods with an accent
 * ring, a small torso, jointed arms with mitten hands, short legs in rounded
 * boots. One inline SVG, colours from tokens only (classes in askLayout.css).
 *
 * Every part that moves is its own group, so the parts animate independently:
 * the whole body floats (and hops), the head tilts, the eyes look, glance and
 * blink each in their own group, the ear rings pulse, the inline-end arm
 * waves from the shoulder and wags at the elbow.
 *
 * `data-mood` is the page's state (robotMood.ts) and `data-look` is where the
 * text box being typed in is: `down` for the question box, `side` for the
 * data chooser at the inline start.
 *
 * Purely decorative.
 */
export default function AskRobot({ look = 'down' }: { look?: 'down' | 'side' }) {
  const mood = useRobotMood()
  const uid = useId().replace(/:/g, '')
  const g = (name: string) => `${uid}-${name}`
  const fill = (name: string) => `url(#${g(name)})`
  return (
    <svg className="dl-bot" viewBox="0 0 200 250" data-mood={mood} data-look={look} aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id={g('shell')} cx="32%" cy="22%" r="85%">
          <stop offset="0" className="dl-bot__s-hi" /><stop offset=".55" className="dl-bot__s-mid" /><stop offset="1" className="dl-bot__s-lo" />
        </radialGradient>
        <linearGradient id={g('limb')} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" className="dl-bot__s-hi" /><stop offset=".6" className="dl-bot__s-mid" /><stop offset="1" className="dl-bot__s-lo" />
        </linearGradient>
        <radialGradient id={g('visor')} cx="50%" cy="34%" r="75%">
          <stop offset="0" className="dl-bot__s-screen-hi" /><stop offset="1" className="dl-bot__s-screen" />
        </radialGradient>
        <radialGradient id={g('glow')}>
          <stop offset="0" className="dl-bot__s-glow" /><stop offset="1" className="dl-bot__s-none" />
        </radialGradient>
        <radialGradient id={g('ground')}>
          <stop offset="0" className="dl-bot__s-shade" /><stop offset="1" className="dl-bot__s-shade" stopOpacity="0" />
        </radialGradient>
      </defs>

      <ellipse className="dl-bot__shadow" cx="100" cy="240" rx="52" ry="7" fill={fill('ground')} />

      <g className="dl-bot__hop">
        <g className="dl-bot__body">
          <g className="dl-bot__legs">
            <g className="dl-bot__leg dl-bot__leg--l">
              <rect x="77" y="182" width="17" height="34" rx="8.5" fill={fill('limb')} />
              <rect className="dl-bot__joint" x="77" y="198" width="17" height="4" />
              <rect x="70" y="210" width="28" height="24" rx="12" fill={fill('shell')} />
            </g>
            <g className="dl-bot__leg dl-bot__leg--r">
              <rect x="106" y="182" width="17" height="34" rx="8.5" fill={fill('limb')} />
              <rect className="dl-bot__joint" x="106" y="198" width="17" height="4" />
              <rect x="102" y="210" width="28" height="24" rx="12" fill={fill('shell')} />
            </g>
          </g>

          <g className="dl-bot__arm dl-bot__arm--l">
            <rect x="-6.5" y="-4" width="13" height="30" rx="6.5" transform="translate(66 146) rotate(28)" fill={fill('limb')} />
            <g className="dl-bot__forearm">
              <rect x="-6" y="-3" width="12" height="26" rx="6" transform="translate(54 168) rotate(6)" fill={fill('limb')} />
              <circle cx="51" cy="193" r="9" fill={fill('shell')} />
              <circle cx="58" cy="190" r="3.6" fill={fill('shell')} />
            </g>
            <circle className="dl-bot__joint" cx="54" cy="168" r="4.5" />
          </g>

          <g className="dl-bot__torso">
            <rect className="dl-bot__neck" x="88" y="114" width="24" height="18" rx="6" />
            <rect x="66" y="126" width="68" height="66" rx="27" fill={fill('shell')} />
            <rect className="dl-bot__chest" x="89" y="150" width="22" height="7" rx="3.5" />
            <circle className="dl-bot__joint" cx="66" cy="146" r="6" />
            <circle className="dl-bot__joint" cx="134" cy="146" r="6" />
          </g>

          <g className="dl-bot__arm dl-bot__arm--r">
            <rect x="-6.5" y="-4" width="13" height="30" rx="6.5" transform="translate(134 146) rotate(-28)" fill={fill('limb')} />
            <g className="dl-bot__forearm">
              <rect x="-6" y="-3" width="12" height="26" rx="6" transform="translate(146 168) rotate(-6)" fill={fill('limb')} />
              <circle cx="149" cy="193" r="9" fill={fill('shell')} />
              <circle cx="142" cy="190" r="3.6" fill={fill('shell')} />
            </g>
            <circle className="dl-bot__joint" cx="146" cy="168" r="4.5" />
          </g>

          <g className="dl-bot__head">
            <g className="dl-bot__ears">
              {[-1, 1].map(side => (
                <g key={side} className="dl-bot__ear">
                  <circle cx={100 + side * 63} cy="72" r="16" fill={fill('shell')} />
                  <circle className="dl-bot__ear-glow" cx={100 + side * 67} cy="72" r="15" fill={fill('glow')} />
                  <circle className="dl-bot__ear-ring" cx={100 + side * 67} cy="72" r="8" />
                </g>
              ))}
            </g>
            <ellipse cx="100" cy="68" rx="59" ry="54" fill={fill('shell')} />
            <g className="dl-bot__visor">
              <rect x="54" y="40" width="92" height="60" rx="30" fill={fill('visor')} />
              <path className="dl-bot__gloss" d="M68 58Q74 46 92 46" />
              <circle className="dl-bot__glint" cx="126" cy="52" r="2.6" />
              <g className="dl-bot__eyes">
                <g className="dl-bot__glance">
                  {[80, 120].map((x, i) => (
                    <g key={x} className={`dl-bot__eye dl-bot__eye--${i ? 'r' : 'l'}`} style={{ transformOrigin: `${x}px 72px` }}>
                      <circle className="dl-bot__eye-glow" cx={x} cy="72" r="17" fill={fill('glow')} />
                      <g className="dl-bot__eye-round">
                        <circle cx={x} cy="72" r="9.5" />
                        <circle className="dl-bot__eye-spark" cx={x - 3} cy="68.5" r="2.4" />
                      </g>
                      <path className="dl-bot__eye-happy" d={`M${x - 9} 76Q${x} 62 ${x + 9} 76`} />
                    </g>
                  ))}
                </g>
              </g>
            </g>
          </g>
        </g>
      </g>
    </svg>
  )
}
