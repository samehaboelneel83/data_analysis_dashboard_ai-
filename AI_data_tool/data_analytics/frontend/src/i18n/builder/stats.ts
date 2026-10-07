/**
 * QA4: stats strings, in English and Arabic. Spread into en.ts / ar.ts.
 * Keys start with "bc.stats." and the two objects must hold the same keys.
 *
 * QA4 T5, the "Is this difference real?" dialog. The English templates
 * repeat the server's own wording (backend inferential.py difference_check),
 * so a translated verdict says what the English one says. In English the
 * dialog still shows the server's sentence as sent.
 */
export const en = {
  // The two questions the server asks (DifferenceTest.question).
  'bc.stats.qRowCounts': 'row counts',
  'bc.stats.qTypicalRow': 'typical row',
  // Effect-size words (DifferenceTest.effect_label).
  'bc.stats.effectNegligible': 'negligible',
  'bc.stats.effectSmall': 'small',
  'bc.stats.effectMedium': 'medium',
  'bc.stats.effectLarge': 'large',
  // Test names (DifferenceTest.test).
  'bc.stats.testWelch': "Welch's t-test",
  'bc.stats.testMannWhitney': 'Mann-Whitney U',
  'bc.stats.testBinomial': 'Exact binomial test (even split)',
  // Verdicts: what was tested x not significant / significant but negligible / significant.
  'bc.stats.countsNotSig': 'No statistically significant difference in how many rows {a} and {b} have ({p}). The data does not support a difference; it does not prove there is none.',
  'bc.stats.countsSigNegligible': 'Statistically significant difference in how many rows {a} and {b} have ({p}), with a negligible statistical effect size. That measures how much the two groups overlap, not how big the gap is for the business -- see the size of the gap.',
  'bc.stats.countsSig': 'Statistically significant difference in how many rows {a} and {b} have ({p}), with a {label} effect.',
  'bc.stats.meanNotSig': 'No statistically significant difference in average {measure} between {a} and {b} ({p}). The data does not support a difference; it does not prove there is none.',
  'bc.stats.meanSigNegligible': 'Statistically significant difference in average {measure} between {a} and {b} ({p}), with a negligible statistical effect size. That measures how much the two groups overlap, not how big the gap is for the business -- see the size of the gap.',
  'bc.stats.meanSig': 'Statistically significant difference in average {measure} between {a} and {b} ({p}), with a {label} effect.',
  'bc.stats.medianNotSig': 'No statistically significant difference in a typical {measure} between {a} and {b} ({p}). The data does not support a difference; it does not prove there is none.',
  'bc.stats.medianSigNegligible': 'Statistically significant difference in a typical {measure} between {a} and {b} ({p}), with a negligible statistical effect size. That measures how much the two groups overlap, not how big the gap is for the business -- see the size of the gap.',
  'bc.stats.medianSig': 'Statistically significant difference in a typical {measure} between {a} and {b} ({p}), with a {label} effect.',
  // The three footnotes (DifferenceCheck.caveats).
  'bc.stats.footTested': "Tested on the {n} rows behind these two bars, after this chart's filters.",
  'bc.stats.footSignificance': "Significance at {alpha}; with many rows, tiny differences are 'significant'. The effect size says how much the groups overlap; the size of the gap says how much it matters.",
  'bc.stats.footNotCause': 'An observed difference, not a cause.',
} as const

export const ar: Record<keyof typeof en, string> = {
  'bc.stats.qRowCounts': 'عدد الصفوف',
  'bc.stats.qTypicalRow': 'الصف النموذجي',
  'bc.stats.effectNegligible': 'ضئيل',
  'bc.stats.effectSmall': 'صغير',
  'bc.stats.effectMedium': 'متوسط',
  'bc.stats.effectLarge': 'كبير',
  'bc.stats.testWelch': 'اختبار t لـ Welch',
  'bc.stats.testMannWhitney': 'اختبار Mann-Whitney U',
  'bc.stats.testBinomial': 'اختبار ذي الحدين الدقيق (تقسيم متساوٍ)',
  'bc.stats.countsNotSig': 'لا يوجد فرق ذو دلالة إحصائية بين عدد صفوف {a} وعدد صفوف {b} ({p}). البيانات لا تدعم وجود فرق، لكنها لا تثبت انعدامه.',
  'bc.stats.countsSigNegligible': 'يوجد فرق ذو دلالة إحصائية بين عدد صفوف {a} وعدد صفوف {b} ({p})، بحجم أثر إحصائي ضئيل. وهذا يقيس مدى تداخل المجموعتين، لا حجم الفجوة بالنسبة للعمل — انظر «حجم الفجوة».',
  'bc.stats.countsSig': 'يوجد فرق ذو دلالة إحصائية بين عدد صفوف {a} وعدد صفوف {b} ({p})، بأثر {label}.',
  'bc.stats.meanNotSig': 'لا يوجد فرق ذو دلالة إحصائية في متوسط {measure} بين {a} و{b} ({p}). البيانات لا تدعم وجود فرق، لكنها لا تثبت انعدامه.',
  'bc.stats.meanSigNegligible': 'يوجد فرق ذو دلالة إحصائية في متوسط {measure} بين {a} و{b} ({p})، بحجم أثر إحصائي ضئيل. وهذا يقيس مدى تداخل المجموعتين، لا حجم الفجوة بالنسبة للعمل — انظر «حجم الفجوة».',
  'bc.stats.meanSig': 'يوجد فرق ذو دلالة إحصائية في متوسط {measure} بين {a} و{b} ({p})، بأثر {label}.',
  'bc.stats.medianNotSig': 'لا يوجد فرق ذو دلالة إحصائية في القيمة النموذجية لـ {measure} بين {a} و{b} ({p}). البيانات لا تدعم وجود فرق، لكنها لا تثبت انعدامه.',
  'bc.stats.medianSigNegligible': 'يوجد فرق ذو دلالة إحصائية في القيمة النموذجية لـ {measure} بين {a} و{b} ({p})، بحجم أثر إحصائي ضئيل. وهذا يقيس مدى تداخل المجموعتين، لا حجم الفجوة بالنسبة للعمل — انظر «حجم الفجوة».',
  'bc.stats.medianSig': 'يوجد فرق ذو دلالة إحصائية في القيمة النموذجية لـ {measure} بين {a} و{b} ({p})، بأثر {label}.',
  'bc.stats.footTested': 'اختُبرت الصفوف الواقعة خلف هذين العمودين، وعددها {n}، بعد تطبيق عوامل تصفية هذا المخطط.',
  'bc.stats.footSignificance': 'مستوى الدلالة {alpha}؛ ومع كثرة الصفوف تصبح الفروق الضئيلة «ذات دلالة». يبيّن حجم الأثر مدى تداخل المجموعتين، ويبيّن حجم الفجوة مدى أهميتها.',
  'bc.stats.footNotCause': 'فرق مُلاحَظ، لا علاقة سببية.',
}
