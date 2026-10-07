import { createElement, Fragment, type ReactNode } from 'react'
import type { MessageKey, TranslateFn } from '../index'

/**
 * QA3 Batch C: the builder's own words (panes), in English and Arabic.
 * Spread into en.ts / ar.ts, so the keys are ordinary MessageKeys; kept in
 * their own module so the builder's strings are found in one place.
 * Keys start with "bc.panes." and the two objects must hold the same keys.
 *
 * A name inside a sentence ("{name}") is the author's text, in whatever
 * script they wrote it. `richT` renders each string value bidi-isolated,
 * so a Latin widget title in an Arabic sentence (or the reverse) keeps its
 * place; quote marks belong in the template (“…” in English, «…» in Arabic).
 */
export const en = {
  // Shared
  'bc.panes.noWidgets': 'No widgets on this page.',
  'bc.panes.save': 'Save',

  // Page properties
  'bc.panes.page.type.normal': 'Normal',
  'bc.panes.page.type.normal.desc': 'Standard visible tab',
  'bc.panes.page.type.hidden': 'Hidden',
  'bc.panes.page.type.hidden.desc': 'Tab hidden in view mode',
  'bc.panes.page.type.popup': 'Popup',
  'bc.panes.page.type.popup.desc': 'Rendered as floating overlay',
  'bc.panes.page.type.tooltip': 'Tooltip',
  'bc.panes.page.type.tooltip.desc': 'Shown as a hover tooltip on another visual',
  'bc.panes.page.type.drillthrough': 'Drillthrough',
  'bc.panes.page.type.drillthrough.desc': 'Reached by drilling through from another page',
  'bc.panes.page.action.button': 'Button',
  'bc.panes.page.action.navigate': "Button '{label}' → navigate: {target}",
  'bc.panes.page.action.bookmark': "Button '{label}' → apply bookmark: {target}",
  'bc.panes.page.action.url': "Button '{label}' → open URL: {target}",
  'bc.panes.page.action.report': "Button '{label}' → go to report #{target}",
  'bc.panes.page.action.setParam': "Button '{label}' → set {param} = {value}",
  'bc.panes.page.action.other': "Button '{label}' → {action}",
  'bc.panes.page.rolesLoadFailed': 'Could not load roles',
  'bc.panes.page.visibilitySaveFailed': 'Could not save page visibility — the page is unchanged',
  'bc.panes.page.namePh': 'Page name',
  'bc.panes.page.size.custom': 'Custom',
  'bc.panes.page.size.customAria': 'custom',
  'bc.panes.page.backgroundPh': 'https://… or /uploads/…',
  'bc.panes.page.backgroundHelp': 'Objects with a transparent background let it show through. Only http(s) URLs and paths on this server are accepted.',
  'bc.panes.page.interactionMode': 'Page interaction mode',
  'bc.panes.page.mode.manual': 'Manual (per-widget settings)',
  'bc.panes.page.mode.linked': 'Linked selection (highlight everywhere)',
  'bc.panes.page.mode.oneway': 'One-way filter (single source)',
  'bc.panes.page.mode.twoway': 'Two-way filter (filters accumulate)',
  'bc.panes.page.modeHelp': "An automatic mode overrides every widget's own interaction settings on this page.",
  'bc.panes.page.lastVisibleTitle': 'This is the only visible page. Readers need one page to open on — make another page Normal first.',
  'bc.panes.page.lastVisibleRadio': 'At least one page must stay visible',
  'bc.panes.page.lastVisibleDesc': 'Not available: this is the only visible page',
  'bc.panes.page.promptIntro': 'A prompt lets viewers filter all widgets by entering a value. Select the column to filter on.',
  'bc.panes.page.noPrompt': '— no prompt —',
  'bc.panes.page.promptLabelPh': 'Filter by {column}',
  'bc.panes.page.visibilityIntro': 'Restrict this page to specific roles. No selection means everyone sees it; org admins always do. Enforced on the server — a restricted page is never sent to an excluded viewer at all.',
  'bc.panes.page.visibleToRoles': 'Visible to roles',

  // Outline
  'bc.panes.outline.rename': 'Rename {name}',
  'bc.panes.outline.hint': 'Click to select, double-click to rename',
  'bc.panes.outline.containerFor': 'Container for {name}',

  // Selection
  'bc.panes.selection.toggle': 'Toggle visibility: {name}',

  // Bookmarks
  'bc.panes.bookmarks.empty': 'No bookmarks yet.',
  'bc.panes.bookmarks.namePh': 'Bookmark name…',
  'bc.panes.bookmarks.add': '+ Add bookmark',

  // Sync slicers
  'bc.panes.sync.empty': 'No slicers in this report yet.',
  'bc.panes.sync.allPages': 'All pages',
  'bc.panes.sync.thisPage': 'This page only',

  // Comments
  'bc.panes.comments.empty': 'No comments yet. Start the discussion — participants get notified of replies.',
  'bc.panes.comments.delete': 'Delete comment {id}',
  'bc.panes.comments.deleteTitle': 'Delete this comment?',
  'bc.panes.comments.deleteBody': 'It is removed for everyone on the report. This cannot be undone.',
  'bc.panes.comments.postFailed': 'Could not post the comment',
  'bc.panes.comments.write': 'Write a comment',
  'bc.panes.comments.writePh': 'Write a comment…',
  'bc.panes.comments.pin': 'Pin to current page',
  'bc.panes.comments.writeFirst': 'Write a comment first',
  'bc.panes.comments.post': 'Post',

  // Tab order
  'bc.panes.tabOrder.help': 'Controls keyboard-Tab order through widgets in View mode.',

  // Mobile layout
  'bc.panes.mobile.help': 'Reorder and hide widgets for narrow-screen viewing. This does not affect the desktop layout.',
  'bc.panes.mobile.show': 'Show on mobile',

  // Translations
  'bc.panes.translations.help': 'Viewers whose browser locale matches see these instead of the authored text. Blank entries fall back.',
  'bc.panes.translations.locale': 'Locale',
  'bc.panes.translations.localePh': 'locale, e.g. ar or fr',
  'bc.panes.translations.saved': 'Saved {locale} translations',
  'bc.panes.translations.removed': 'Removed {locale}',
  'bc.panes.translations.saveFailed': 'Could not save translations',
  'bc.panes.translations.of': 'Translation of {name}',
  'bc.panes.translations.ofText': 'Translation of text {id}',
  'bc.panes.translations.saveLocale': 'Save {locale}',

  // Review: findings
  'bc.panes.review.untitledNoAlt': 'Untitled {type} has no alt text — a screen reader announces nothing useful',
  'bc.panes.review.unfinished': '"{name}" is unfinished — readers see a placeholder until {roles} is set',
  'bc.panes.review.imageNoAlt': 'Image has no alt text',
  'bc.panes.review.noRows': '"{name}" returned no rows — check its roles and filters',
  'bc.panes.review.brokenRules': '"{name}" has {n} broken display rule(s) — rules fail open, so they silently stop applying',
  'bc.panes.review.emptyContainer': 'Container "{name}" is empty',
  'bc.panes.review.slow': '"{name}" took {s}s to load',
  'bc.panes.review.heavyPage': 'Page "{page}" has {n} widgets — every one queries on load',
  'bc.panes.review.autoMode.linked': 'Page "{page}" is in linked selection mode, which ignores the {n} per-pair action(s) on "{name}" — automatic modes replace manual actions',
  'bc.panes.review.autoMode.oneway': 'Page "{page}" is in one-way mode, which ignores the {n} per-pair action(s) on "{name}" — automatic modes replace manual actions',
  'bc.panes.review.autoMode.twoway': 'Page "{page}" is in two-way mode, which ignores the {n} per-pair action(s) on "{name}" — automatic modes replace manual actions',
  'bc.panes.review.autoMode.other': 'Page "{page}" is in {mode} mode, which ignores the {n} per-pair action(s) on "{name}" — automatic modes replace manual actions',
  'bc.panes.review.deadTarget': '"{name}" has an action pointing at a widget that no longer exists (#{id}) — the target was deleted and the action can never fire',
  'bc.panes.review.otherPage': '"{name}" has an action on "{target}", which is on another page ("{page}") — filters are scoped to their own page unless the source syncs across pages, so this never arrives',
  'bc.panes.review.notReceiving': '"{name}" has an action on "{target}", which is set not to receive — the selection is dropped before the action is consulted',
  'bc.panes.review.deafPage': 'Nothing on this page will react to a selection — every widget on "{page}" is set not to receive, so a reader\'s clicks change nothing',
  'bc.panes.review.crossDataset': 'Clicks on "{name}" ({col}) will not filter widgets on {dataset} such as "{target}" — that dataset has no {col} and no mapping to it. Add one in Model → relationships if they should connect.',
  'bc.panes.review.crossDatasetUnnamed': 'Clicks on "{name}" ({col}) will not filter widgets on dataset {id} such as "{target}" — that dataset has no {col} and no mapping to it. Add one in Model → relationships if they should connect.',

  // Review: the pane
  'bc.panes.review.badge.wiring': 'WIRING',
  'bc.panes.review.badge.a11y': 'A11Y',
  'bc.panes.review.badge.error': 'ERROR',
  'bc.panes.review.badge.warn': 'WARN',
  'bc.panes.review.badge.info': 'INFO',
  'bc.panes.review.none': 'No problems found — titles, alt text, data, display rules and the interaction wiring all check out.',
  'bc.panes.review.gate': 'Publish gate:',
  'bc.panes.review.gateBlocked': 'on — publishing is blocked until the {n, plural, one{# error above is} other{# errors above are}} fixed.',
  'bc.panes.review.gateClear': 'on — no errors open, this report can be published.',
  'bc.panes.review.gateOff': 'off — review errors are advice only.',
  'bc.panes.review.gateTurnOff': 'Turn off for the organisation',
  'bc.panes.review.gateTurnOn': 'Block publishing while errors are open',
  'bc.panes.review.measuring': 'Measuring every widget…',
  'bc.panes.review.evaluate': '⏱ Evaluate performance',
  'bc.panes.review.evaluateFailed': 'Could not evaluate',
  'bc.panes.review.perf.summary': '{n} widgets, {s}s in total, run now without cache as you',
  'bc.panes.review.perf.slow': ' · {n} slower than {s}s',
  'bc.panes.review.perf.ms': '{ms} ms',
  'bc.panes.review.perf.where': '{page}, {rows} marks',
  'bc.panes.review.perf.history': 'its dataset, last 7 days: {runs} queries, median {median} ms, p95 {p95} ms',
  'bc.panes.review.perf.cache': ', {pct}% from cache',
} as const

export const ar: Record<keyof typeof en, string> = {
  'bc.panes.noWidgets': 'لا عناصر في هذه الصفحة.',
  'bc.panes.save': 'حفظ',

  'bc.panes.page.type.normal': 'عادية',
  'bc.panes.page.type.normal.desc': 'تبويب ظاهر عادي',
  'bc.panes.page.type.hidden': 'مخفية',
  'bc.panes.page.type.hidden.desc': 'تبويب مخفي في وضع العرض',
  'bc.panes.page.type.popup': 'منبثقة',
  'bc.panes.page.type.popup.desc': 'تُعرض طبقةً عائمة فوق التقرير',
  'bc.panes.page.type.tooltip': 'تلميح',
  'bc.panes.page.type.tooltip.desc': 'تظهر تلميحًا عند المرور فوق عنصر آخر',
  'bc.panes.page.type.drillthrough': 'تعمّق',
  'bc.panes.page.type.drillthrough.desc': 'يُوصل إليها بالتعمّق من صفحة أخرى',
  'bc.panes.page.action.button': 'زر',
  'bc.panes.page.action.navigate': 'الزر «{label}» ← الانتقال إلى: {target}',
  'bc.panes.page.action.bookmark': 'الزر «{label}» ← تطبيق الإشارة المرجعية: {target}',
  'bc.panes.page.action.url': 'الزر «{label}» ← فتح الرابط: {target}',
  'bc.panes.page.action.report': 'الزر «{label}» ← الانتقال إلى التقرير رقم {target}',
  'bc.panes.page.action.setParam': 'الزر «{label}» ← تعيين {param} = {value}',
  'bc.panes.page.action.other': 'الزر «{label}» ← {action}',
  'bc.panes.page.rolesLoadFailed': 'تعذّر تحميل الأدوار',
  'bc.panes.page.visibilitySaveFailed': 'تعذّر حفظ ظهور الصفحة. لم تتغير الصفحة.',
  'bc.panes.page.namePh': 'اسم الصفحة',
  'bc.panes.page.size.custom': 'مخصص',
  'bc.panes.page.size.customAria': 'مخصص',
  'bc.panes.page.backgroundPh': 'https://… أو /uploads/…',
  'bc.panes.page.backgroundHelp': 'تظهر الصورة من خلال العناصر ذات الخلفية الشفافة. لا تُقبل إلا روابط http(s) والمسارات على هذا الخادم.',
  'bc.panes.page.interactionMode': 'وضع التفاعل في الصفحة',
  'bc.panes.page.mode.manual': 'يدوي (إعدادات كل عنصر)',
  'bc.panes.page.mode.linked': 'تحديد مرتبط (تمييز في كل مكان)',
  'bc.panes.page.mode.oneway': 'تصفية في اتجاه واحد (مصدر واحد)',
  'bc.panes.page.mode.twoway': 'تصفية في الاتجاهين (تتراكم عوامل التصفية)',
  'bc.panes.page.modeHelp': 'الوضع التلقائي يتجاوز إعدادات التفاعل الخاصة بكل عنصر في هذه الصفحة.',
  'bc.panes.page.lastVisibleTitle': 'هذه هي الصفحة الظاهرة الوحيدة. يحتاج القراء إلى صفحة يفتحون عليها، فاجعل صفحة أخرى عادية أولًا.',
  'bc.panes.page.lastVisibleRadio': 'يجب أن تبقى صفحة واحدة ظاهرة على الأقل',
  'bc.panes.page.lastVisibleDesc': 'غير متاح: هذه هي الصفحة الظاهرة الوحيدة',
  'bc.panes.page.promptIntro': 'يتيح المُحفِّز للقراء تصفية كل العناصر بإدخال قيمة. اختر العمود الذي تجري عليه التصفية.',
  'bc.panes.page.noPrompt': '— بلا مُحفِّز —',
  'bc.panes.page.promptLabelPh': 'تصفية حسب {column}',
  'bc.panes.page.visibilityIntro': 'اقصر هذه الصفحة على أدوار محددة. إن لم تحدد شيئًا يراها الجميع، ومسؤولو المؤسسة يرونها دائمًا. يُطبَّق هذا على الخادم، فلا تُرسَل الصفحة المقيدة أبدًا إلى قارئ مستبعد.',
  'bc.panes.page.visibleToRoles': 'ظاهرة للأدوار',

  'bc.panes.outline.rename': 'إعادة تسمية {name}',
  'bc.panes.outline.hint': 'انقر للتحديد، وانقر مرتين لإعادة التسمية',
  'bc.panes.outline.containerFor': 'حاوية {name}',

  'bc.panes.selection.toggle': 'تبديل الظهور: {name}',

  'bc.panes.bookmarks.empty': 'لا إشارات مرجعية بعد.',
  'bc.panes.bookmarks.namePh': 'اسم الإشارة المرجعية…',
  'bc.panes.bookmarks.add': '+ إضافة إشارة مرجعية',

  'bc.panes.sync.empty': 'لا مرشحات في هذا التقرير بعد.',
  'bc.panes.sync.allPages': 'كل الصفحات',
  'bc.panes.sync.thisPage': 'هذه الصفحة فقط',

  'bc.panes.comments.empty': 'لا تعليقات بعد. ابدأ النقاش، وسيصل إلى المشاركين تنبيه بالردود.',
  'bc.panes.comments.delete': 'حذف التعليق {id}',
  'bc.panes.comments.deleteTitle': 'حذف هذا التعليق؟',
  'bc.panes.comments.deleteBody': 'سيُحذف لدى كل من يرى التقرير. لا يمكن التراجع عن ذلك.',
  'bc.panes.comments.postFailed': 'تعذّر نشر التعليق',
  'bc.panes.comments.write': 'اكتب تعليقًا',
  'bc.panes.comments.writePh': 'اكتب تعليقًا…',
  'bc.panes.comments.pin': 'تثبيت على الصفحة الحالية',
  'bc.panes.comments.writeFirst': 'اكتب تعليقًا أولًا',
  'bc.panes.comments.post': 'نشر',

  'bc.panes.tabOrder.help': 'يحدد ترتيب التنقل بمفتاح Tab بين العناصر في وضع العرض.',

  'bc.panes.mobile.help': 'رتّب العناصر وأخفِ ما تشاء منها للعرض على الشاشات الضيقة. لا يؤثر هذا في تخطيط سطح المكتب.',
  'bc.panes.mobile.show': 'إظهار على الجوال',

  'bc.panes.translations.help': 'القراء الذين تطابق لغة متصفحهم هذه اللغة يرون هذه الترجمات بدل النص الأصلي. الحقل الفارغ يعود إلى النص الأصلي.',
  'bc.panes.translations.locale': 'اللغة',
  'bc.panes.translations.localePh': 'رمز اللغة، مثل ar أو fr',
  'bc.panes.translations.saved': 'حُفظت ترجمات {locale}',
  'bc.panes.translations.removed': 'أُزيلت ترجمات {locale}',
  'bc.panes.translations.saveFailed': 'تعذّر حفظ الترجمات',
  'bc.panes.translations.of': 'ترجمة {name}',
  'bc.panes.translations.ofText': 'ترجمة النص {id}',
  'bc.panes.translations.saveLocale': 'حفظ {locale}',

  'bc.panes.review.untitledNoAlt': 'عنصر من نوع {type} بلا عنوان ولا نص بديل، فلا يقرأ قارئ الشاشة عنه شيئًا مفيدًا',
  'bc.panes.review.unfinished': '«{name}» غير مكتمل، ويرى القراء عنصرًا نائبًا حتى يُحدَّد: {roles}',
  'bc.panes.review.imageNoAlt': 'الصورة بلا نص بديل',
  'bc.panes.review.noRows': '«{name}» لم يُرجع أي صفوف. راجع أدواره وعوامل التصفية.',
  'bc.panes.review.brokenRules': 'في «{name}» {n, plural, one{قاعدة عرض معطلة} two{قاعدتا عرض معطلتان} few{# قواعد عرض معطلة} many{# قاعدة عرض معطلة} other{# قاعدة عرض معطلة}}. القاعدة المعطلة تتوقف عن العمل دون أي تنبيه.',
  'bc.panes.review.emptyContainer': 'الحاوية «{name}» فارغة',
  'bc.panes.review.slow': 'استغرق تحميل «{name}» {s} ث',
  'bc.panes.review.heavyPage': 'في الصفحة «{page}» {n, plural, few{# عناصر} many{# عنصرًا} other{# عنصر}}، وكل منها يرسل استعلامًا عند التحميل',
  'bc.panes.review.autoMode.linked': 'الصفحة «{page}» في وضع التحديد المرتبط، فتُتجاهل الإجراءات اليدوية على «{name}» (عددها {n}). الأوضاع التلقائية تحل محل الإجراءات اليدوية.',
  'bc.panes.review.autoMode.oneway': 'الصفحة «{page}» في وضع التصفية في اتجاه واحد، فتُتجاهل الإجراءات اليدوية على «{name}» (عددها {n}). الأوضاع التلقائية تحل محل الإجراءات اليدوية.',
  'bc.panes.review.autoMode.twoway': 'الصفحة «{page}» في وضع التصفية في الاتجاهين، فتُتجاهل الإجراءات اليدوية على «{name}» (عددها {n}). الأوضاع التلقائية تحل محل الإجراءات اليدوية.',
  'bc.panes.review.autoMode.other': 'الصفحة «{page}» في الوضع {mode}، فتُتجاهل الإجراءات اليدوية على «{name}» (عددها {n}). الأوضاع التلقائية تحل محل الإجراءات اليدوية.',
  'bc.panes.review.deadTarget': 'في «{name}» إجراء يشير إلى عنصر لم يعد موجودًا (#{id}). حُذف الهدف، فلن يعمل الإجراء أبدًا.',
  'bc.panes.review.otherPage': 'في «{name}» إجراء على «{target}»، وهو في صفحة أخرى («{page}»). تبقى عوامل التصفية في صفحتها ما لم يُزامَن المصدر عبر الصفحات، فلن يصل هذا الإجراء أبدًا.',
  'bc.panes.review.notReceiving': 'في «{name}» إجراء على «{target}»، لكن «{target}» مضبوط على عدم الاستقبال، فيُهمَل التحديد قبل الرجوع إلى الإجراء.',
  'bc.panes.review.deafPage': 'لا شيء في هذه الصفحة يستجيب للتحديد. كل العناصر في «{page}» مضبوطة على عدم الاستقبال، فنقرات القارئ لا تغيّر شيئًا.',
  'bc.panes.review.crossDataset': 'النقر على «{name}» ({col}) لن يصفّي العناصر في {dataset} مثل «{target}»، لأن مجموعة البيانات هذه ليس فيها {col} ولا ربط إليه. أضف ربطًا من النموذج ← العلاقات إن كان يجب أن تتصلا.',
  'bc.panes.review.crossDatasetUnnamed': 'النقر على «{name}» ({col}) لن يصفّي العناصر في مجموعة البيانات {id} مثل «{target}»، لأن مجموعة البيانات هذه ليس فيها {col} ولا ربط إليه. أضف ربطًا من النموذج ← العلاقات إن كان يجب أن تتصلا.',

  'bc.panes.review.badge.wiring': 'ربط',
  'bc.panes.review.badge.a11y': 'إتاحة',
  'bc.panes.review.badge.error': 'خطأ',
  'bc.panes.review.badge.warn': 'تحذير',
  'bc.panes.review.badge.info': 'معلومة',
  'bc.panes.review.none': 'لا مشكلات. العناوين والنص البديل والبيانات وقواعد العرض وربط التفاعلات كلها سليمة.',
  'bc.panes.review.gate': 'بوابة النشر:',
  'bc.panes.review.gateBlocked': 'مفعّلة: لا يمكن النشر قبل إصلاح {n, plural, one{الخطأ المذكور أعلاه} two{الخطأين المذكورين أعلاه} few{الأخطاء المذكورة أعلاه (#)} many{الأخطاء المذكورة أعلاه (#)} other{الأخطاء المذكورة أعلاه (#)}}.',
  'bc.panes.review.gateClear': 'مفعّلة: لا أخطاء مفتوحة، ويمكن نشر هذا التقرير.',
  'bc.panes.review.gateOff': 'متوقفة: أخطاء المراجعة للنصح فقط.',
  'bc.panes.review.gateTurnOff': 'إيقافها للمؤسسة',
  'bc.panes.review.gateTurnOn': 'منع النشر ما دامت هناك أخطاء مفتوحة',
  'bc.panes.review.measuring': 'جارٍ قياس كل عنصر…',
  'bc.panes.review.evaluate': '⏱ تقييم الأداء',
  'bc.panes.review.evaluateFailed': 'تعذّر التقييم',
  'bc.panes.review.perf.summary': '{n, plural, zero{لا عناصر} one{عنصر واحد} two{عنصران} few{# عناصر} many{# عنصرًا} other{# عنصر}}، {s} ث إجمالًا، قيست الآن دون ذاكرة مؤقتة وبصلاحياتك',
  'bc.panes.review.perf.slow': ' · {n} أبطأ من {s} ث',
  'bc.panes.review.perf.ms': '{ms} ملّي ث',
  'bc.panes.review.perf.where': '{page}، العلامات: {rows}',
  'bc.panes.review.perf.history': 'مجموعة بياناته، آخر 7 أيام: عدد الاستعلامات {runs}، الوسيط {median} ملّي ث، p95 {p95} ملّي ث',
  'bc.panes.review.perf.cache': '، {pct}% من الذاكرة المؤقتة',
}

/** `t(key, vars)` as React nodes, each string value bidi-isolated so a name
 *  in another script cannot be reordered into the sentence around it.
 *  Numbers stay numbers, so `{n, plural, …}` still picks the right form.
 *
 *  Each <bdi> says `display: inline` out loud. Browsers already draw it
 *  inline; jsdom reports no display at all, and the accessible-name code then
 *  treats the <bdi> as a block and pads it with spaces ("Button ' Go ' → …"),
 *  which is not the name a reader hears. */
const INLINE = { display: 'inline' } as const

export function richT(t: TranslateFn, key: MessageKey,
                      vars: Record<string, string | number>): ReactNode {
  const marked: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(vars)) marked[k] = typeof v === 'number' ? v : `\u0001${k}\u0002`
  const parts = t(key, marked).split(/\u0001(\w+)\u0002/)
  return createElement(Fragment, null, ...parts.map((p, i) =>
    i % 2 ? createElement('bdi', { key: i, style: INLINE }, String(vars[p])) : p))
}
