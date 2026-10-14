/** "Untitled dashboard", then "Untitled dashboard 2", 3, ... -- never a name
 *  already on the list, so two quick creates are still told apart. `base` is
 *  the reader's language (QA T1: Arabic showed the English name). */
export function nextUntitledName(existing: string[], base = 'Untitled dashboard'): string {
  const taken = new Set(existing.map(n => n.trim().toLowerCase()))
  if (!taken.has(base.toLowerCase())) return base
  for (let i = 2; ; i++) if (!taken.has(`${base} ${i}`.toLowerCase())) return `${base} ${i}`
}
