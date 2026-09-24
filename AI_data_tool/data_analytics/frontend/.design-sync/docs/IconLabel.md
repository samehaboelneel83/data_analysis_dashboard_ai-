---
category: Primitives
---

# IconLabel

An icon beside a label, for buttons and menu items. Use it instead of typing an
emoji: one Lucide glyph, one stroke weight, `currentColor` — so a button's active
state tints mark and word together rather than leaving a coloured emoji stranded
on a filled background.

```jsx
const { IconLabel } = window.Datalytics;
import { Sparkles } from 'lucide-react';

<button className="btn btn-primary">
  <IconLabel icon={Sparkles}>Ask AI</IconLabel>
</button>
```

## The text is always a child

Never bake the label into the icon or pass it as a prop. Keeping it a plain child
is what lets screen readers and `getByRole('button', { name })` both read the word,
while the mark stays `aria-hidden` decoration.

`size` defaults to 13 and sets the icon only — set the surrounding font size on the
parent, so mark and word scale together.
