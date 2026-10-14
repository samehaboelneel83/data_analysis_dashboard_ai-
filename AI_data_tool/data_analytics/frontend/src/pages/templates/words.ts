import type { MessageKey, TranslateFn } from '../../i18n'
import { en } from '../../i18n'
import type { TemplateCard, TemplateSlot } from '../../services/api'

/** The platform's templates are worded by the catalogue (`tpl.b.<key>.*`,
 *  `tpl.sl.<label>`); a saved template shows the words its author gave it. */
const known = (key: string): key is MessageKey => key in en

export function templateName(c: Pick<TemplateCard, 'source' | 'key' | 'name'>, t: TranslateFn): string {
  const key = `tpl.b.${c.key}.name`
  return c.source === 'builtin' && known(key) ? t(key) : c.name
}
export function templateDescription(c: Pick<TemplateCard, 'source' | 'key' | 'description'>, t: TranslateFn): string {
  const key = `tpl.b.${c.key}.desc`
  return c.source === 'builtin' && known(key) ? t(key) : c.description
}
export function slotLabel(s: Pick<TemplateSlot, 'label'>, t: TranslateFn): string {
  const key = `tpl.sl.${s.label}`
  return known(key) ? t(key) : s.label
}
export function categoryName(category: string, t: TranslateFn): string {
  const key = `tpl.cat.${category}`
  return known(key) ? t(key) : category
}
export const kindName = (kind: string, t: TranslateFn): string => {
  const key = `tpl.kind.${kind}`
  return known(key) ? t(key) : kind
}
