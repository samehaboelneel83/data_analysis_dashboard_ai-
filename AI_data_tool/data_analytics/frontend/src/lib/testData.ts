/**
 * Names that read like leftovers from testing: "qa_sample…", "test 3",
 * "tmp_orders", "Untitled dashboard 7", "… (copy)".
 *
 * Only ever used to PRE-SELECT rows for a person to review in a bulk action --
 * never to delete or hide anything on its own. A false positive costs one
 * unticked checkbox; that is why it may be a little generous.
 */
const TEST_NAME = /^(qa|test|tests|testing|tmp|temp|debug|dummy|scratch|sample)(?=$|[\s_\-.:#\d])|^untitled\b|\bqa[_\s-]?sample\b|\(copy( \d+)?\)$|^copy of\b/i

export function looksLikeTestData(name: string | null | undefined): boolean {
  return !!name && TEST_NAME.test(name.trim())
}
