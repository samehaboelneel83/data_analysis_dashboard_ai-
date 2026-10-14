/**
 * Names that read like leftovers from testing: "qa_sample…", "test 3",
 * "tmp_orders", "Untitled dashboard 7", "… (copy)".
 *
 * Used to PRE-SELECT rows for a person to review in a bulk action, and (4.7)
 * to tuck such names out of dataset PICKERS behind a "Show n test-looking"
 * button -- never to delete anything, and never to hide a certified dataset.
 * A false positive costs one click; that is why it may be a little generous.
 */
const TEST_NAME = /^(qa|test|tests|testing|tmp|temp|debug|dummy|scratch|sample)(?=$|[\s_\-.:#\d])|^untitled\b|\bqa[_\s-]?sample\b|\(copy( \d+)?\)$|^copy of\b/i

/** 4.7: what the HR evaluation actually found in front of a new user --
 *  "13", "2", "kjhkjhkjhkjh", "claude job check". A bare number, a name of one
 *  character, a chunk typed three times over, or a "… check" run. */
const BARE_NUMBER = /^\d+$/
const KEYBOARD_MASH = /^([a-z]{2,4})\1{2,}[a-z]*$/i
const CHECK_RUN = /\b(job|smoke|sanity|import|connection|claude)\s+(check|test|run)\b/i
/** Also seen live: "sss", "report_pagessss" (a key held down), "data-1777154203914"
 *  (a timestamped upload nobody named), "Metrics Snapshot Test", and the
 *  outputs built from them ("ss output"). */
const HELD_KEY = /([a-z])\1{2,}/i
const UNNAMED_UPLOAD = /^data-\d{9,}$/i
const TEST_WORD = /\b(test|testing)\b/i
const SCRAP_OUTPUT = /^[a-z]{1,3}[\s_-]+output$/i

export function looksLikeTestData(name: string | null | undefined): boolean {
  if (!name) return false
  const n = name.trim()
  return TEST_NAME.test(n) || BARE_NUMBER.test(n) || n.length === 1 || KEYBOARD_MASH.test(n) || CHECK_RUN.test(n)
    || HELD_KEY.test(n) || UNNAMED_UPLOAD.test(n) || TEST_WORD.test(n) || SCRAP_OUTPUT.test(n)
}
