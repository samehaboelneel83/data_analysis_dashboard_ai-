/**
 * The Ask AI hero picture: a small, friendly assistant (rounded white body,
 * glowing screen face with a smile) with four floating cards around it -- a
 * bar chart, a donut, a chat bubble and a table -- tied to it by thin dotted
 * lines. Drawn here in SVG, app tokens only, no remote assets.
 *
 * The cards drift slowly (6-8 s loops, out of phase). Styles and the
 * prefers-reduced-motion freeze live in pages/ask/ask.css (.dl-askart*).
 * Purely decorative: the headline beside it carries the meaning, so it is
 * aria-hidden.
 */
export default function AskIllustration({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 520 300" className={`dl-askart ${className ?? ''}`} aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id="dl-askart-glow">
          <stop offset="0%" className="dl-askart__glow0" />
          <stop offset="100%" className="dl-askart__glow1" />
        </radialGradient>
        <linearGradient id="dl-askart-body" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="100%" stopColor="#dfe5ee" />
        </linearGradient>
        <linearGradient id="dl-askart-screen" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#15212c" />
          <stop offset="100%" stopColor="#0b1219" />
        </linearGradient>
      </defs>

      {/* Dotted links from the assistant to each card. */}
      <g className="dl-askart__links">
        <path d="M218 130 C 180 118, 160 100, 142 92" />
        <path d="M302 128 C 336 112, 360 96, 382 86" />
        <path d="M222 188 C 190 204, 168 214, 146 222" />
        <path d="M298 190 C 334 206, 356 214, 380 222" />
      </g>

      <circle cx="260" cy="160" r="112" fill="url(#dl-askart-glow)" />

      {/* Bar chart card (top start). */}
      <g className="dl-askart__card dl-askart__card--a">
        <rect x="40" y="46" width="112" height="84" rx="12" className="dl-askart__panel" />
        <rect x="54" y="58" width="44" height="6" rx="3" className="dl-askart__ink" />
        <rect x="56" y="98" width="12" height="20" rx="2" className="dl-askart__bar" />
        <rect x="74" y="86" width="12" height="32" rx="2" className="dl-askart__bar" />
        <rect x="92" y="92" width="12" height="26" rx="2" className="dl-askart__bar" />
        <rect x="110" y="74" width="12" height="44" rx="2" className="dl-askart__accent" />
        <rect x="128" y="96" width="12" height="22" rx="2" className="dl-askart__bar" />
      </g>

      {/* Donut card (top end). */}
      <g className="dl-askart__card dl-askart__card--b">
        <rect x="372" y="36" width="96" height="92" rx="12" className="dl-askart__panel" />
        <circle cx="420" cy="82" r="24" className="dl-askart__ring" />
        <circle cx="420" cy="82" r="24" className="dl-askart__ring-accent" pathLength="100"
          strokeDasharray="38 100" transform="rotate(-90 420 82)" />
        <circle cx="420" cy="82" r="24" className="dl-askart__ring-2" pathLength="100"
          strokeDasharray="22 100" strokeDashoffset="-40" transform="rotate(-90 420 82)" />
      </g>

      {/* Chat bubble (bottom start). */}
      <g className="dl-askart__card dl-askart__card--c">
        <rect x="46" y="200" width="104" height="52" rx="14" className="dl-askart__panel" />
        <path d="M70 252 l -8 12 l 18 -12 z" className="dl-askart__panel-tail" />
        <rect x="60" y="214" width="72" height="6" rx="3" className="dl-askart__ink" />
        <rect x="60" y="228" width="52" height="6" rx="3" className="dl-askart__ink dl-askart__ink--soft" />
      </g>

      {/* Table card (bottom end). */}
      <g className="dl-askart__card dl-askart__card--d">
        <rect x="372" y="196" width="112" height="72" rx="12" className="dl-askart__panel" />
        {[0, 1, 2, 3].map(i => (
          <g key={i}>
            <rect x="384" y={208 + i * 13} width="26" height="5" rx="2.5"
              className={i === 0 ? 'dl-askart__ink' : 'dl-askart__ink dl-askart__ink--soft'} />
            <rect x="416" y={208 + i * 13} width="26" height="5" rx="2.5"
              className={i === 2 ? 'dl-askart__accent' : 'dl-askart__ink dl-askart__ink--soft'} />
            <rect x="448" y={208 + i * 13} width="24" height="5" rx="2.5" className="dl-askart__ink dl-askart__ink--soft" />
          </g>
        ))}
      </g>

      {/* The assistant. */}
      <g className="dl-askart__bot">
        <line x1="260" y1="84" x2="260" y2="100" className="dl-askart__antenna" />
        <circle cx="260" cy="80" r="6" className="dl-askart__accent dl-askart__beacon" />
        <ellipse cx="260" cy="266" rx="46" ry="7" className="dl-askart__shadow" />
        {/* Body */}
        <rect x="224" y="200" width="72" height="56" rx="26" fill="url(#dl-askart-body)" className="dl-askart__shell" />
        <rect x="248" y="222" width="24" height="7" rx="3.5" className="dl-askart__accent" />
        {/* Head */}
        <rect x="206" y="98" width="108" height="100" rx="40" fill="url(#dl-askart-body)" className="dl-askart__shell" />
        <rect x="196" y="136" width="12" height="26" rx="6" fill="url(#dl-askart-body)" className="dl-askart__shell" />
        <rect x="312" y="136" width="12" height="26" rx="6" fill="url(#dl-askart-body)" className="dl-askart__shell" />
        {/* Screen face */}
        <rect x="220" y="114" width="80" height="66" rx="24" fill="url(#dl-askart-screen)" />
        <rect x="220" y="114" width="80" height="66" rx="24" className="dl-askart__screen-glow" />
        <ellipse cx="244" cy="140" rx="6" ry="8" className="dl-askart__eye" />
        <ellipse cx="276" cy="140" rx="6" ry="8" className="dl-askart__eye" />
        <path d="M244 158 Q 260 170 276 158" className="dl-askart__smile" />
      </g>
    </svg>
  )
}
