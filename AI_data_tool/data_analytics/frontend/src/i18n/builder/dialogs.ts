/**
 * QA4: dialogs strings, in English and Arabic. Spread into en.ts / ar.ts.
 * Keys start with "bc.dialogs." and the two objects must hold the same keys.
 *
 * The English texts are byte-identical to the literals they replaced (tests
 * find them by that text). In Arabic the name sits inside «» and inside
 * Unicode isolates (U+2068 ... U+2069), so a Latin or mixed-direction name
 * stays whole and the ؟ / full stop land at the sentence's end, on the left.
 */
export const en = {
  // Datasets page and Connections page: deleting a dataset / a data source.
  'bc.dialogs.deleteNamed': 'Delete "{name}"?',
  'bc.dialogs.cannotUndo': 'This cannot be undone.',
  'bc.dialogs.datasetMenu': 'More actions for dataset {name}',
  'bc.dialogs.datasetDeleted': 'Dataset deleted',
  'bc.dialogs.deleted': 'Deleted',
  // Dashboards page: same wording as dsh.deleteTitle / dsh.folderDeleteTitle /
  // dsh.move.confirmTitle in English; the Arabic isolates the names.
  'bc.dialogs.deleteDashboard': 'Delete dashboard "{name}"?',
  'bc.dialogs.deleteFolder': 'Delete the folder "{name}"?',
  'bc.dialogs.moveDashboard': 'Move "{name}" to {to}?',
  'bc.dialogs.loadErr.title': 'Could not load this',
  'bc.dialogs.loadErr.body': 'The server did not respond. This does not mean the data is missing — it means we could not reach it.',
  'bc.dialogs.loadErr.retry': 'Try again',
  'bc.dialogs.loadErr.back': 'Go back',
} as const

export const ar: Record<keyof typeof en, string> = {
  'bc.dialogs.deleteNamed': 'حذف «⁨{name}⁩»؟',
  'bc.dialogs.cannotUndo': 'لا يمكن التراجع عن ذلك.',
  'bc.dialogs.datasetMenu': 'إجراءات أخرى لمجموعة البيانات «⁨{name}⁩»',
  'bc.dialogs.datasetDeleted': 'حُذفت مجموعة البيانات',
  'bc.dialogs.deleted': 'تم الحذف',
  'bc.dialogs.deleteDashboard': 'حذف اللوحة «⁨{name}⁩»؟',
  'bc.dialogs.deleteFolder': 'حذف المجلد «⁨{name}⁩»؟',
  'bc.dialogs.moveDashboard': 'نقل «⁨{name}⁩» إلى ⁨{to}⁩؟',
  'bc.dialogs.loadErr.title': 'تعذّر تحميل هذه البيانات',
  'bc.dialogs.loadErr.body': 'لم يستجب الخادم. هذا لا يعني أن البيانات مفقودة، بل إننا لم نتمكن من الوصول إليها.',
  'bc.dialogs.loadErr.retry': 'حاول مرة أخرى',
  'bc.dialogs.loadErr.back': 'رجوع',
}
