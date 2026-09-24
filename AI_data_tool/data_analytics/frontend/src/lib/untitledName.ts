/** "Untitled dashboard", then "Untitled dashboard 2", 3, ... -- never a name
 *  already on the list, so two quick creates are still told apart. */
export function nextUntitledName(existing: string[]): string {
  const base = 'Untitled dashboard'
  const taken = new Set(existing.map(n => n.trim().toLowerCase()))
  if (!taken.has(base.toLowerCase())) return base
  for (let i = 2; ; i++) if (!taken.has(`${base} ${i}`.toLowerCase())) return `${base} ${i}`
}
