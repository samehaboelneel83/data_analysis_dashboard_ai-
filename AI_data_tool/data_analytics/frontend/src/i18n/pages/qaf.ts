/**
 * FIX-QAF: strings for the fixes from the final QA. Spread into en.ts / ar.ts.
 * Keys start with "qaf." and both objects hold the same keys and {placeholders}.
 */
// Every Arabic count form: zero, one, two, few (3-10), many (11-99), other.
const arCount = (v: string, one: string, two: string, few: string, many: string, other: string) =>
  `{${v}, plural, zero{# ${other}} one{${one}} two{${two}} few{# ${few}} many{# ${many}} other{# ${other}}}`

export const en = {
  // M2: a dashboard made before drafts and publishing (no author) is open to the whole organisation
  'qaf.st.open': 'Everyone',
  'qaf.st.openTitle': 'Made before drafts and publishing: everyone in the organisation can see it.',
  'qaf.home.status': '{pub} published · {draft} drafts · {open} for everyone',
  'qaf.home.status2': '{pub} published · {draft} drafts',
  // M3: stop waiting for an answer
  'qaf.ask.stop': 'Stop',
  'qaf.ask.stopTitle': 'Stop waiting for this answer',
  'qaf.ask.stopped': 'Stopped waiting. The server may still finish.',
  // M4: Lineage impact, a zero part left out
  'qaf.lin.impactBoth': 'If {name} changes, {ds, plural, one {# dataset} other {# datasets}} and {rep, plural, one {# report} other {# reports}} are affected.',
  'qaf.lin.impactDs': 'If {name} changes, {ds, plural, one {# dataset is} other {# datasets are}} affected.',
  'qaf.lin.impactRep': 'If {name} changes, {rep, plural, one {# report is} other {# reports are}} affected.',
  // 11: Overview "Used by", by kind
  'qaf.ov.dash': '{n, plural, one {# dashboard} other {# dashboards}}',
  'qaf.ov.ds': '{n, plural, one {# dataset} other {# datasets}}',
  'qaf.ov.alerts': '{n, plural, one {# alert} other {# alerts}}',
  // 13: key influencers' effect as a percentage
  'qaf.ki.higher': '{p}% higher',
  'qaf.ki.lower': '{p}% lower',
  // 15: the chooser's time is the data's update time
  'qaf.pick.updated': 'Updated {ago}',
  // 18: Lineage minimap
  'qaf.lin.hideMini': 'Hide the minimap',
  'qaf.lin.showMini': 'Show the minimap',
  // 19 / 22: Lineage list and panel
  'qaf.lin.fileNoRefresh': 'A file upload: refresh does not apply.',
  'qaf.lin.notChecked': 'Not checked here',
  // 25: SSO switched on with nothing filled in
  'qaf.sso.emptyEnabled': 'Single sign-on is switched on, but the email domain or issuer is empty, so no one can sign in with it yet.',
  // 26: audit trail details
  'qaf.audit.expires': 'Expires after {n, plural, one {# day} other {# days}}',
  'qaf.audit.link': 'Link #{id}',
  'qaf.audit.raw': 'Recorded by the server as is',
}

export const ar: Record<keyof typeof en, string> = {
  'qaf.st.open': 'للجميع',
  'qaf.st.openTitle': 'أُنشئت قبل المسودات والنشر: يراها كل من في المؤسسة.',
  'qaf.home.status': '{pub} منشورة · {draft} مسودات · {open} للجميع',
  'qaf.home.status2': '{pub} منشورة · {draft} مسودات',
  'qaf.ask.stop': 'إيقاف',
  'qaf.ask.stopTitle': 'التوقف عن انتظار هذه الإجابة',
  'qaf.ask.stopped': 'توقّف الانتظار. قد يُكمل الخادم العمل.',
  'qaf.lin.impactBoth': `تغيير «\u2068{name}\u2069» يؤثر في ${arCount('ds', 'مجموعة بيانات واحدة', 'مجموعتي بيانات', 'مجموعات بيانات', 'مجموعة بيانات', 'مجموعة بيانات')} و${arCount('rep', 'تقرير واحد', 'تقريرين', 'تقارير', 'تقريرًا', 'تقرير')}.`,
  'qaf.lin.impactDs': `تغيير «\u2068{name}\u2069» يؤثر في ${arCount('ds', 'مجموعة بيانات واحدة', 'مجموعتي بيانات', 'مجموعات بيانات', 'مجموعة بيانات', 'مجموعة بيانات')}.`,
  'qaf.lin.impactRep': `تغيير «\u2068{name}\u2069» يؤثر في ${arCount('rep', 'تقرير واحد', 'تقريرين', 'تقارير', 'تقريرًا', 'تقرير')}.`,
  'qaf.ov.dash': arCount('n', 'لوحة واحدة', 'لوحتان', 'لوحات', 'لوحة', 'لوحة'),
  'qaf.ov.ds': arCount('n', 'مجموعة بيانات واحدة', 'مجموعتا بيانات', 'مجموعات بيانات', 'مجموعة بيانات', 'مجموعة بيانات'),
  'qaf.ov.alerts': arCount('n', 'تنبيه واحد', 'تنبيهان', 'تنبيهات', 'تنبيهًا', 'تنبيه'),
  'qaf.ki.higher': 'أعلى بنسبة {p}%',
  'qaf.ki.lower': 'أقل بنسبة {p}%',
  'qaf.pick.updated': 'حُدّثت {ago}',
  'qaf.lin.fileNoRefresh': 'ملف مرفوع: لا ينطبق عليه التحديث.',
  'qaf.lin.notChecked': 'لم تُفحص هنا',
  'qaf.lin.hideMini': 'إخفاء الخريطة المصغّرة',
  'qaf.lin.showMini': 'إظهار الخريطة المصغّرة',
  'qaf.sso.emptyEnabled': 'الدخول الموحّد مفعَّل، لكن نطاق البريد أو جهة الإصدار فارغ، فلا يمكن لأحد الدخول به بعد.',
  'qaf.audit.expires': `تنتهي بعد ${arCount('n', 'يوم واحد', 'يومين', 'أيام', 'يومًا', 'يوم')}`,
  'qaf.audit.link': 'الرابط رقم {id}',
  'qaf.audit.raw': 'كما سجّله الخادم',
}
