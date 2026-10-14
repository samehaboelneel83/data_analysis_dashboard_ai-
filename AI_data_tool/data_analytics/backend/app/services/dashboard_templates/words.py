"""The platform's templates in the reader's language.

A dashboard made from a template is the person's own content: its chart
titles, page names and measure names are WRITTEN when it is made, so they are
written in the language the person is working in. (The gallery's own words --
a template's name, its description -- are the browser's catalogue, `tpl.b.*`.)

Only the built-in templates are worded here; a saved template says what its
author wrote. `{slot}` stays as it is: it becomes the mapped column's name.
"""
from __future__ import annotations

import copy

AR: dict[str, str] = {
    # Page names
    "Overview": "نظرة عامة", "Scorecard": "بطاقة الأرقام", "Trends": "الاتجاهات", "Stages": "المراحل",
    "Target": "المستهدف", "Activity": "النشاط", "Comparison": "المقارنة", "Places": "الأماكن",
    "Spread": "التوزيع", "Rows": "الصفوف",
    "What goes together": "ما الذي يجتمع معًا",
    "Values and what links them": "القيم وما يربط بينها",
    "The role of each value towards each other": "دور كل قيمة تجاه الأخرى",
    "How each value is linked": "كيف ترتبط كل قيمة",
    "The rules, with each value's role": "القواعد، مع دور كل قيمة",
    "Which values are linked, and how strongly": "أي القيم مرتبطة، وبأي قوة",
    "A column of labels": "عمود تسميات", "A second column of labels": "عمود تسميات ثانٍ",
    "A third column of labels": "عمود تسميات ثالث", "A fourth column of labels": "عمود تسميات رابع",
    "What is in the data": "ما في البيانات",
    "Which numbers move together": "أي الأرقام تتحرك معًا",
    "Natural groups": "المجموعات الطبيعية",
    "Which outcome": "أي نتيجة",
    "What it depends on": "علامَ يعتمد",
    "Through time": "عبر الوقت",
    "Out of the ordinary": "خارج المألوف",
    "What the text says": "ما يقوله النص",
    "What is connected": "ما المتصل بماذا",
    "Where it comes from": "من أين يأتي",
    "Rows by {group2}": "عدد الصفوف حسب {group2}",
    "Every pair of numbers": "كل زوج من الأرقام",
    "{value} against {c}": "{value} مقابل {c}",
    "Each row across the numbers": "كل صف عبر الأرقام",
    "The groups as a picture": "المجموعات كصورة",
    "What each group is like": "كيف تبدو كل مجموعة",
    "How well the groups hold apart": "مدى تمايز المجموعات",
    "How well it predicts": "مدى دقة التنبؤ",
    "Right and wrong": "الصواب والخطأ",
    "Against a coin toss": "مقارنةً برمي عملة",
    "What matters most": "الأكثر أهمية",
    "What each factor does to the odds": "أثر كل عامل على الاحتمال",
    "How well it is explained": "مدى جودة التفسير",
    "Actual against predicted": "الفعلي مقابل المتوقَّع",
    "Where it misses": "أين يخطئ",
    "What each factor adds": "ما يضيفه كل عامل",
    "{value} by month of the year": "{value} حسب شهر السنة",
    "{value} by month, and the months outside the usual": "{value} شهريًا، والأشهر الخارجة عن المعتاد",
    "{text}, sized by how often": "{text}، بحجم يتبع التكرار",
    "The most frequent {text}": "أكثر {text} تكرارًا",
    "{text} by {group}": "{text} حسب {group}",
    "{source} and {target} as a network": "{source} و{target} كشبكة",
    "{source} with the most links": "أكثر {source} روابطَ",
    "From {source} to {target}": "من {source} إلى {target}",
    "{source} against {target}": "{source} مقابل {target}",
    "How {group} adds up to total {value}": "كيف يكوّن {group} إجمالي {value}",
    "The yes-or-no outcome": "النتيجة بنعم أو لا",
    "The number to explain": "الرقم المراد تفسيره",
    "A number it may depend on": "رقم قد يعتمد عليه",
    "The column of text": "عمود النص",
    "Where a link starts": "أين يبدأ الرابط",
    "Where a link ends": "أين ينتهي الرابط",
    "Summary": "الملخص", "Groups": "المجموعات", "Detail": "التفاصيل",
    # Chart titles
    "Total {value3}": "إجمالي {value3}",
    "{value} by month, and where it is heading": "{value} شهريًا، وإلى أين يتجه",
    "What goes with a higher {value}": "ما الذي يصاحب ارتفاع {value}", "{value} by quarter": "{value} حسب الربع",
    "{value} by {group2} over time": "{value} حسب {group2} عبر الوقت",
    "Total {value}": "إجمالي {value}", "Average {value}": "متوسط {value}", "Total {value2}": "إجمالي {value2}",
    "{value} over time": "{value} عبر الوقت", "{value} by {group2}": "{value} حسب {group2}",
    "{value} by {group}": "{value} حسب {group}", "{group} in detail": "تفاصيل {group}",
    "{a} over time": "{a} عبر الوقت", "{a} by {group}": "{a} حسب {group}",
    "Highest {value}": "أعلى {value}", "{value} by month": "{value} شهريًا",
    "{value} by day of the week": "{value} حسب يوم الأسبوع", "{value} by year and month": "{value} حسب السنة والشهر",
    "{value} by {group} over time": "{value} حسب {group} عبر الوقت",
    "Rows at each {stage}": "عدد الصفوف في كل {stage}", "Rows over time": "عدد الصفوف عبر الوقت",
    "{value} by {stage}": "{value} حسب {stage}", "{stage} within each {group}": "{stage} داخل كل {group}",
    "Gap": "الفرق", "Reached (%)": "نسبة التحقق (%)",
    "{actual} and {target} over time": "{actual} و{target} عبر الوقت",
    "Reached (%) by {group}": "نسبة التحقق (%) حسب {group}", "Gap by {group}": "الفرق حسب {group}",
    "{actual} as % of {target}": "{actual} كنسبة من {target}", "{actual} minus {target}": "{actual} ناقص {target}",
    "Rows by {kind}": "عدد الصفوف حسب {kind}", "Rows by day and hour": "عدد الصفوف حسب اليوم والساعة",
    "Rows by {where}": "عدد الصفوف حسب {where}", "Number of {group}": "عدد {group}",
    "{value} by {group}, largest first": "{value} حسب {group}، الأكبر أولًا",
    "Share of {value} by {group2}": "حصة {value} حسب {group2}",
    "{value} by {group} and {group2}": "{value} حسب {group} و{group2}",
    "Number of {place}": "عدد {place}", "{value} by {place}": "{value} حسب {place}",
    "{place} ranked by {value}": "{place} مرتبةً حسب {value}",
    "Typical {value}": "القيمة المعتادة لـ {value}", "Lowest {value}": "أدنى {value}",
    "How {value} is spread": "كيف يتوزع {value}", "{value} within each {group}": "{value} داخل كل {group}",
    "{value} against {other}": "{value} مقابل {other}", "Typical {value} by {group}": "القيمة المعتادة لـ {value} حسب {group}",
    "Rows by {group}": "عدد الصفوف حسب {group}",
    # Slot labels (the sample preview names its columns by them)
    "The number to follow": "الرقم المراد متابعته", "When each row happened": "متى حدث كل صف",
    "The main way to split it": "الطريقة الرئيسية لتقسيمه", "A second way to split it": "طريقة ثانية لتقسيمه",
    "A second number": "رقم ثانٍ", "First number": "الرقم الأول", "Second number": "الرقم الثاني",
    "Third number": "الرقم الثالث", "Fourth number": "الرقم الرابع", "Fifth number": "الرقم الخامس",
    "Sixth number": "الرقم السادس", "A way to split them": "طريقة لتقسيمها", "A way to split it": "طريقة لتقسيمه",
    "The stage each row is at": "المرحلة التي فيها كل صف", "What each row is worth": "قيمة كل صف",
    "What was reached": "ما تحقق", "What was expected": "ما كان متوقعًا",
    "The groups to compare": "المجموعات المراد مقارنتها", "The kind of each row": "نوع كل صف",
    "A number to follow": "رقم للمتابعة", "Where it happened": "أين حدث",
    "The number to compare": "الرقم المراد مقارنته", "The place of each row": "مكان كل صف",
    "The number to look into": "الرقم المراد فحصه", "The columns to show": "الأعمدة المراد عرضها",
    "A filter": "فلتر", "A second filter": "فلتر ثانٍ", "A number to total": "رقم لجمعه",
}
BY_LANGUAGE = {"ar": AR}


def localise(spec: dict, lang: str | None) -> dict:
    """A built-in template with its page names, chart titles, measure names
    and slot labels in `lang`; the specification itself for English, for a
    language with no words here, and for a template somebody saved."""
    words = BY_LANGUAGE.get(str(lang or "")[:2])
    if not words or not spec.get("key"):
        return spec
    out = copy.deepcopy(spec)
    for s in out.get("slots") or []:
        s["label"] = words.get(s.get("label"), s.get("label"))
    for m in out.get("metrics") or []:
        m["label"] = words.get(m.get("label"), m.get("label"))
    for p in out.get("pages") or []:
        p["name"] = words.get(p.get("name"), p.get("name"))
        for w in p.get("widgets") or []:
            w["title"] = words.get(w.get("title"), w.get("title"))
    return out
