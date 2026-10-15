import type { MessageKey } from '../../i18n'

/**
 * Which sentence explains why AI is unavailable: the role does not include it
 * (QA E-08), the person turned it off (F-11), or the model is unreachable.
 */
export function aiOffKey(ai: { off?: boolean; role?: boolean }, kind: 'title' | 'composer'): MessageKey {
  if (ai.role) return kind === 'title' ? 'off.titleRole' : 'off.composerRole'
  if (ai.off) return kind === 'title' ? 'off.titleMine' : 'off.composerMine'
  return kind === 'title' ? 'off.title' : 'off.composer'
}
