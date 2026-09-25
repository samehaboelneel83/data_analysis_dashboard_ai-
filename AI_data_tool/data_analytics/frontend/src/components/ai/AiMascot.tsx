/**
 * The Ask AI mascot, small: a rounded white head with a dark glowing screen
 * face (two eyes, a smile) and an antenna with an accent tip. The same
 * character as the Ask AI page's hero illustration, cut down to read at
 * 18-32px. Decorative: whatever wraps it carries the accessible name.
 *
 * Eyes blink when the `.dl-mascot--alive` class is on (see copilot.css);
 * prefers-reduced-motion freezes them.
 */
export default function AiMascot({ size = 24, alive = false, className }: {
  size?: number
  alive?: boolean
  className?: string
}) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true" focusable="false"
      className={`dl-mascot${alive ? ' dl-mascot--alive' : ''}${className ? ` ${className}` : ''}`}>
      <defs>
        <linearGradient id="dl-mascot-shell" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="100%" stopColor="#dfe6ee" />
        </linearGradient>
      </defs>
      {/* antenna */}
      <line x1="16" y1="4.5" x2="16" y2="8" stroke="#dfe6ee" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="16" cy="4" r="2" className="dl-mascot__tip" />
      {/* ears */}
      <rect x="3.2" y="14" width="3.4" height="7" rx="1.7" fill="url(#dl-mascot-shell)" />
      <rect x="25.4" y="14" width="3.4" height="7" rx="1.7" fill="url(#dl-mascot-shell)" />
      {/* head */}
      <rect x="5.5" y="8" width="21" height="19" rx="8" fill="url(#dl-mascot-shell)" />
      {/* screen face */}
      <rect x="8.5" y="11" width="15" height="12.5" rx="5.2" fill="#122029" />
      <g className="dl-mascot__eyes">
        <ellipse cx="13" cy="16" rx="1.5" ry="1.9" className="dl-mascot__eye" />
        <ellipse cx="19" cy="16" rx="1.5" ry="1.9" className="dl-mascot__eye" />
      </g>
      <path d="M13 19.6 Q16 21.8 19 19.6" fill="none" strokeWidth="1.5" strokeLinecap="round"
        className="dl-mascot__smile" />
    </svg>
  )
}
