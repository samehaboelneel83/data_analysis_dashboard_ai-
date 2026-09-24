import type { ConnectorSpec } from '../../services/api'

/* Icon/label maps, filled from the connector catalog once fetched (see the page
   component). Populated in place so list rows and the schema browser keep
   reading them; a fresh connector needs no frontend change. */
export const TYPE_ICON: Record<string, string> = {}
export const TYPE_LABEL: Record<string, string> = {}

export function blankConfigFor(spec: ConnectorSpec | undefined): Record<string, unknown> {
  if (!spec) return {}
  return Object.fromEntries(spec.config_fields.map(f => [f.name, f.default ?? '']))
}

