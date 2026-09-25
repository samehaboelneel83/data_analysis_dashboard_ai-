import type { CSSProperties } from 'react'

/**
 * The one inline style a form field may still carry: its size.
 *
 * Nine admin forms each defined their own `inp` object -- 12px text, 5px
 * padding, a 4px radius, and a background and border copied from the theme --
 * so their fields were ~27px tall beside 34px buttons, squarer than every
 * other control, and immune to the hover and focus treatment in index.css
 * (an inline border outranks it). Colour, border and radius now come from
 * the global field rule; this only sets the size, from the same control
 * height the buttons use.
 */
export const fieldStyle: CSSProperties = {
  width: '100%',
  fontSize: 13,
  padding: '7px 10px',
  boxSizing: 'border-box',
}

/** The same field, sized to its content rather than its container. */
export const inlineFieldStyle: CSSProperties = {
  fontSize: 13,
  padding: '6px 10px',
  boxSizing: 'border-box',
}
