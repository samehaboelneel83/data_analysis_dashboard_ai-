"""Text analytics that work offline, Arabic first (Phase 6.6).

Three pieces the topic model and the sentiment scorer share:

  * **Arabic normalisation.** The same word reaches a dataset spelled several
    ways -- with or without diacritics, a stretched letter (tatweel), any of
    four alefs, a final yaa written as alef maqsura. Counting those as
    different words splits every topic and hides every lexicon hit, so text
    is normalised before anything counts it. Light-stemming strips only the
    definite article and a leading "wa-" -- the forms that change a word's
    spelling without changing what it means.
  * **Stop lists** for Arabic, English (scikit-learn's), French, Spanish and
    German, chosen per column by a detector that reads the script and the
    share of each list's words it finds. A column that is mostly Arabic with
    English product names gets both lists, because it contains both.
  * **Lexicon sentiment** with the rules that make a word list tolerable on
    business text: a negator flips the next few words ("not bad", "مش كويس"),
    an intensifier scales them, and after "but"/"لكن" the second clause
    outweighs the first. It is still a lexicon: it misses sarcasm and domain
    words, which is why the analysis that uses it reports its coverage and, when
    the data already has a sentiment column, its agreement with it.
"""
from __future__ import annotations

import math
import re
from collections import Counter

import pandas as pd

# ── Arabic normalisation ──────────────────────────────────────────────────────
_DIACRITICS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭ]")
_TATWEEL = "ـ"
_ALEFS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ؤ": "و", "ئ": "ي",
                        "ة": "ه"})
_ARABIC_CHAR = re.compile("[؀-ۿ]")
_LATIN_CHAR = re.compile("[A-Za-zÀ-ÿ]")
_TOKEN = re.compile(r"[\w']+", re.UNICODE)


def normalize_arabic(text: str) -> str:
    """Strip diacritics and tatweel, unify alef/yaa/hamza seats. Latin text passes through."""
    if not text:
        return ""
    text = _DIACRITICS.sub("", text).replace(_TATWEEL, "")
    return text.translate(_ALEFS)


def light_stem_ar(token: str) -> str:
    """Drop a leading و / ال / وال / بال / كال / فال / لل when the rest is still a word."""
    for prefix in ("وال", "بال", "كال", "فال", "لل", "ال"):
        if token.startswith(prefix) and len(token) - len(prefix) >= 3:
            return token[len(prefix):]
    if token.startswith("و") and len(token) >= 5:
        return token[1:]
    return token


def tokens(text: str) -> list[str]:
    """Lower-cased, Arabic-normalised, light-stemmed word tokens."""
    out = []
    for t in _TOKEN.findall(normalize_arabic(str(text)).lower()):
        t = t.strip("'")
        if not t or t.isdigit():
            continue
        out.append(light_stem_ar(t) if _ARABIC_CHAR.search(t) else t)
    return out


# ── Stop lists ─────────────────────────────────────────────────────────────────
# Arabic: pronouns, prepositions, particles, auxiliaries and the everyday
# fillers of Gulf/Egyptian/Levantine review text. Written normalised (plain
# alef, final yaa) and stemmed where the article would be stripped anyway.
_AR = """
في من على الى إلى عن مع هذا هذه ذلك تلك هناك هنا الذي التي الذين اللذان اللتان اللاتي
هو هي هم هن انا أنا انت أنت انتم نحن انتما هما كان كانت كانوا يكون تكون يكونوا صار صارت
قد لقد ثم او أو ام أم بل حتى اذا إذا لو كل بعض اي أي غير سوى بين عند عندي عندنا لدى لدي
حيث حين بعد قبل فوق تحت امام خلف منذ خلال ضد نحو لدى مثل كما كيف متى اين أين لماذا ماذا
ان إن أن انه إنه لان لأن كي لكي و ف ب ل ك ما ماذا هل اما أما الا إلا ايضا أيضا فقط جدا جداً
به بها بهم لها له لهم لهن منه منها منهم عليه عليها عليهم فيه فيها فيهم اليه إليه اليها إليها
ذا ذي تلك اولئك أولئك هؤلاء هاذا دي ده دا اللي الي يعني كده كدا بس برضه برضو احنا انتو
حاجه حاجة شي شيء اشي هيك هاد هادا هادي وين شو ليش ايش إيش وش كذا زي عشان علشان لانه
يا ياريت ولا ولكن وكان وكانت وهو وهي وهذا وهذه ومن وفي وعلى والى وإلى وعن ومع
عام يوم سنه سنة الان الآن اليوم امس أمس غدا غداً مره مرة مرات
""".split()

_FR = """
le la les un une des de du et en à au aux ce ces cet cette il elle ils elles je tu nous vous
on ne pas plus que qui quoi dont où est sont été être avoir ai as a avons avez ont fait
pour par sur dans avec sans sous chez mais ou donc or ni car se sa son ses leur leurs mon ma
mes ton ta tes notre nos votre vos y lui très tout tous toute toutes comme si bien aussi
""".split()
_ES = """
el la los las un una unos unas de del y e o u en a al que qué es son fue ser estar está
están he ha han hay por para con sin sobre entre se su sus lo le les me te nos os mi mis tu
tus muy más pero como cuando donde este esta estos estas ese esa eso esto ya también todo
""".split()
_DE = """
der die das den dem des ein eine einer eines einem einen und oder aber in im an am auf aus
bei mit nach von vor zu zum zur für über unter ist sind war waren sein hat haben wird werden
ich du er sie es wir ihr nicht kein keine auch noch nur sehr so wie dass als wenn doch
""".split()


def _english() -> frozenset[str]:
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    return frozenset(ENGLISH_STOP_WORDS)


def _norm_list(words) -> frozenset[str]:
    out = set()
    for w in words:
        n = normalize_arabic(w).lower()
        out.add(n)
        if _ARABIC_CHAR.search(n):
            out.add(light_stem_ar(n))
    return frozenset(out)


STOP_LISTS: dict[str, frozenset[str]] = {
    "ar": _norm_list(_AR), "fr": _norm_list(_FR), "es": _norm_list(_ES), "de": _norm_list(_DE),
}
LANGUAGES = ("ar", "en", "fr", "es", "de")
LANGUAGE_NAMES = {"ar": "Arabic", "en": "English", "fr": "French", "es": "Spanish", "de": "German"}


def stop_words_for(langs) -> frozenset[str]:
    out: set[str] = set()
    for lang in langs:
        out |= _english() if lang == "en" else STOP_LISTS.get(lang, frozenset())
    return frozenset(out)


def detect_languages(texts, sample: int = 400) -> dict:
    """Which languages a column is written in, from a sample of its rows.

    Script decides Arabic vs Latin; among Latin languages, the share of each
    stop list's words decides. Returns ``{"primary": code, "languages": [..],
    "shares": {code: share}}`` where ``languages`` lists every language with at
    least 15% of the sample's words -- a bilingual column gets both lists.
    """
    words: Counter = Counter()
    ar_chars = latin_chars = 0
    for t in list(texts)[:sample]:
        s = str(t)
        ar_chars += len(_ARABIC_CHAR.findall(s))
        latin_chars += len(_LATIN_CHAR.findall(s))
        words.update(tokens(s))
    total_chars = ar_chars + latin_chars
    if not total_chars:
        return {"primary": "unknown", "languages": [], "shares": {}}
    shares = {"ar": ar_chars / total_chars}
    latin_share = latin_chars / total_chars
    if latin_share > 0:
        latin_words = [w for w in words.elements() if not _ARABIC_CHAR.search(w)]
        hits = {lang: sum(1 for w in latin_words if w in (_english() if lang == "en" else STOP_LISTS[lang]))
                for lang in ("en", "fr", "es", "de")}
        best = max(hits, key=hits.get)
        # Latin text with no stop-word hits at all (product codes, names) is
        # attributed to English, the list that does least harm.
        shares[best if hits[best] else "en"] = latin_share
    langs = [k for k, v in sorted(shares.items(), key=lambda kv: -kv[1]) if v >= 0.15]
    return {"primary": langs[0] if langs else "unknown", "languages": langs,
            "shares": {k: round(v, 3) for k, v in shares.items() if v > 0}}


# ── Sentiment lexicon ──────────────────────────────────────────────────────────
# Weights -3..+3, business/service vocabulary. Arabic entries are normalised
# and cover MSA plus common Egyptian/Gulf/Levantine review words.
_EN_LEX = {
    "excellent": 3, "outstanding": 3, "amazing": 3, "fantastic": 3, "perfect": 3, "love": 3,
    "loved": 3, "superb": 3, "wonderful": 3, "brilliant": 3, "best": 2.5, "great": 2.5,
    "awesome": 2.5, "delighted": 2.5, "impressed": 2, "good": 1.8, "nice": 1.5, "happy": 2,
    "pleased": 2, "satisfied": 1.8, "recommend": 2, "recommended": 2, "helpful": 1.8,
    "friendly": 1.8, "fast": 1.3, "quick": 1.3, "easy": 1.3, "smooth": 1.3, "reliable": 1.5,
    "clean": 1.2, "fresh": 1.2, "polite": 1.5, "professional": 1.5, "efficient": 1.5,
    "convenient": 1.3, "affordable": 1.3, "worth": 1.2, "quality": 0.8, "thanks": 1.2,
    "thank": 1.2, "fine": 0.8, "ok": 0.3, "okay": 0.3, "resolved": 1.2, "fixed": 1,
    "on-time": 1.2, "ontime": 1.2, "improved": 1.2, "enjoy": 2, "enjoyed": 2, "like": 1,
    "liked": 1.3, "comfortable": 1.5, "accurate": 1.2, "responsive": 1.3,
    "terrible": -3, "awful": -3, "horrible": -3, "worst": -3, "hate": -3, "hated": -3,
    "disgusting": -3, "useless": -2.5, "scam": -3, "fraud": -3, "pathetic": -2.8,
    "bad": -2, "poor": -2, "disappointed": -2.2, "disappointing": -2.2, "angry": -2.3,
    "annoyed": -1.8, "frustrated": -2, "frustrating": -2, "rude": -2.3, "unhelpful": -2,
    "slow": -1.5, "late": -1.5, "delay": -1.5, "delayed": -1.6, "delays": -1.5,
    "broken": -2, "damaged": -2, "defective": -2.2, "faulty": -2, "wrong": -1.6,
    "missing": -1.5, "lost": -1.5, "expensive": -1.2, "overpriced": -2,
    "dirty": -2, "cold": -0.8, "noisy": -1.2, "confusing": -1.5, "difficult": -1.2,
    "complicated": -1.2, "problem": -1.4, "problems": -1.4, "issue": -1.2, "issues": -1.2,
    "complaint": -1.3, "complain": -1.3, "refund": -0.8, "cancelled": -1.2, "canceled": -1.2,
    "cancel": -1, "error": -1.4, "errors": -1.4, "fail": -1.8, "failed": -1.8, "failure": -2,
    "waste": -2.2, "unacceptable": -2.5, "worse": -2.2, "crash": -1.8, "crashed": -1.8,
    "bug": -1.2, "bugs": -1.2, "wait": -0.6, "waiting": -0.8, "ignored": -1.8, "unreliable": -2,
    # product / software vocabulary
    "useful": 1.8, "clear": 1.2, "unclear": -1.4, "fair": 1, "solid": 1.5, "stable": 1.3,
    "unstable": -1.8, "intuitive": 1.8, "seamless": 2, "seamlessly": 2, "powerful": 1.5,
    "saved": 1.2, "saves": 1.2, "easier": 1.5, "simple": 1, "incredible": 2.5, "flawless": 2.8,
    "confused": -1.6, "friction": -1.2, "shaky": -1.5, "fiddly": -1.2, "outdated": -1.4,
    "clunky": -1.8, "buggy": -2, "glitch": -1.5, "glitchy": -1.8, "laggy": -1.8, "lag": -1.3,
    "awkward": -1.3, "timeout": -1.5, "freezes": -1.8, "froze": -1.8, "dropping": -1,
    "dropped": -1, "misleading": -1.8, "cumbersome": -1.6, "tedious": -1.5, "painful": -1.8,
}
_AR_LEX_RAW = {
    "ممتاز": 3, "ممتازه": 3, "رائع": 3, "رائعه": 3, "روعه": 3, "مذهل": 3, "ممتع": 2, "افضل": 2.5,
    "احسن": 2.2, "جميل": 2, "جميله": 2, "حلو": 1.8, "حلوه": 1.8, "جيد": 1.8, "جيده": 1.8,
    "كويس": 1.8, "كويسه": 1.8, "زين": 1.8, "تمام": 1.5, "مميز": 2.2, "مميزه": 2.2,
    "سريع": 1.3, "سريعه": 1.3, "سهل": 1.3, "سهله": 1.3, "نظيف": 1.3, "نظيفه": 1.3,
    "لطيف": 1.5, "محترم": 1.5, "محترمين": 1.5, "مفيد": 1.5, "انصح": 2, "انصحكم": 2,
    "شكرا": 1.2, "شكراً": 1.2, "مشكورين": 1.5, "راضي": 1.8, "سعيد": 2, "سعيده": 2,
    "مرتاح": 1.5, "احب": 2.2, "حبيت": 2.2, "عجبني": 2, "يعجبني": 2, "اعجبني": 2, "يعجبنا": 2, "عجبنا": 2, "يستاهل": 1.5, "مناسب": 1,
    "رخيص": 1, "متعاون": 1.8, "متعاونين": 1.8, "دقيق": 1.2, "بطل": 1.5, "فخم": 2,
    "سيء": -2.2, "سيئ": -2.2, "سيئه": -2.2, "سئ": -2.2, "اسوا": -3, "زفت": -2.8, "وحش": -2,
    "وحشه": -2, "خايس": -2.5, "فاشل": -2.5, "فاشله": -2.5, "رديء": -2.3, "ردي": -2.3,
    "متاخر": -1.6, "تاخير": -1.6, "تاخر": -1.6, "بطيء": -1.5, "بطئ": -1.5, "غالي": -1.2,
    "مكسور": -2, "تالف": -2, "خربان": -2, "خرب": -1.8, "ناقص": -1.5, "مفقود": -1.5,
    "مشكله": -1.4, "مشاكل": -1.5, "شكوي": -1.3, "زعلان": -2, "غاضب": -2.3, "محبط": -2,
    "سييء": -2.2, "قذر": -2.3, "وسخ": -2, "مزعج": -1.8, "صعب": -1.2, "معقد": -1.2,
    "خطا": -1.4, "غلط": -1.5, "الغاء": -1.1, "ملغي": -1.2, "استرجاع": -0.6, "نصب": -3,
    "حرامي": -3, "حراميه": -3, "ندمت": -2.3, "مستحيل": -1.2, "تعبان": -1.2, "ممل": -1.8,
    "للاسف": -1.5, "للأسف": -1.5, "مخيب": -2.2, "انتظار": -0.7, "بارد": -0.6,
    "سلس": 1.8, "سلسه": 1.8, "واضح": 1.2, "واضحه": 1.2, "عملي": 1.3, "مستقر": 1.3, "موثوق": 1.5,
    "معطل": -2, "عطلان": -2, "يعلق": -1.5, "معلق": -1.3, "مشوش": -1.3, "مربك": -1.5, "بطيئه": -1.5,
}
_AR_LEX = {light_stem_ar(normalize_arabic(k)): v for k, v in _AR_LEX_RAW.items()}
_AR_LEX.update({normalize_arabic(k): v for k, v in _AR_LEX_RAW.items()})

_NEGATORS = frozenset({"not", "no", "never", "without", "hardly", "barely", "nothing",
                       "isnt", "wasnt", "dont", "doesnt", "didnt", "cant", "couldnt",
                       "wont", "wouldnt", "arent", "werent", "havent", "hasnt", "nor",
                       "ne", "pas", "jamais", "sin", "nunca", "nicht", "kein", "keine"}
                      | {normalize_arabic(w) for w in ("لا", "لم", "لن", "ليس", "ليست", "غير", "ما",
                                                       "مش", "مو", "مب", "بدون", "مافي", "ماكو", "ولا")})
_INTENSIFIERS = {"very": 1.4, "really": 1.3, "extremely": 1.6, "so": 1.2, "too": 1.2,
                 "super": 1.4, "totally": 1.4, "absolutely": 1.5, "highly": 1.4, "incredibly": 1.5, "far": 1.2,
                 normalize_arabic("جدا"): 1.4, normalize_arabic("جداً"): 1.4, "كتير": 1.3,
                 "كثير": 1.3, "مره": 1.3, "للغايه": 1.5, "تماما": 1.4, "خالص": 1.4, "اوي": 1.4, "قوي": 1.3}
_BUT = frozenset({"but", "however", "although", "though", "mais", "pero", "aber",
                  "لكن", "بس", "الا", "إلا", "ولكن"} | {normalize_arabic("لكن")})
NEGATION_SPAN = 3


def _clean(tok: str) -> str:
    return tok.replace("'", "").replace("’", "")


def score_text(text) -> tuple[float, list[tuple[str, float]]]:
    """(compound score in [-1, 1], [(word, contribution), …]) for one comment.

    Unscored text (no lexicon word) scores exactly 0 with no hits -- which the
    caller counts as *uncovered*, not as neutral opinion.
    """
    if text is None or (isinstance(text, float) and math.isnan(text)):
        return 0.0, []
    raw = [_clean(t) for t in _TOKEN.findall(normalize_arabic(str(text)).lower())]
    total = 0.0
    hits: list[tuple[str, float]] = []
    negate_left = 0
    boost = 1.0
    clause_weight = 1.0
    prev_was_hit = False
    for tok in raw:
        if not tok:
            continue
        if tok in _INTENSIFIERS and prev_was_hit:
            # Arabic puts the intensifier AFTER the word: "ممتازة جدا".
            w_prev, c_prev = hits[-1]
            scaled = c_prev * _INTENSIFIERS[tok]
            total += scaled - c_prev
            hits[-1] = (w_prev, scaled)
            prev_was_hit = False
            continue
        prev_was_hit = False
        if tok in _BUT:
            # the clause before "but" counts half, the one after one-and-a-half
            total *= 0.5
            hits = [(w, c * 0.5) for w, c in hits]
            clause_weight = 1.5
            negate_left, boost = 0, 1.0
            continue
        if tok in _NEGATORS:
            negate_left = NEGATION_SPAN
            continue
        if tok in _INTENSIFIERS:
            boost = _INTENSIFIERS[tok]
            continue
        stem = light_stem_ar(tok) if _ARABIC_CHAR.search(tok) else tok
        w = _EN_LEX.get(tok, _AR_LEX.get(tok, _AR_LEX.get(stem)))
        if w is not None:
            c = w * boost * clause_weight
            if negate_left:
                # "not bad" is mildly positive, "not good" clearly negative
                c = -c * (0.5 if w < 0 else 0.75)
            total += c
            # a negated hit is reported as such: "not friction" drove this
            # comment positive, not the word "friction"
            hits.append((f"not {tok}" if negate_left else tok, c))
            boost = 1.0
            prev_was_hit = True
        if negate_left:
            negate_left -= 1
    if not hits:
        return 0.0, []
    compound = total / math.sqrt(total * total + 15)
    return round(compound, 4), hits


POSITIVE_AT = 0.05
NEGATIVE_AT = -0.05


def sentiment_series(series: pd.Series) -> pd.Series:
    """Compound score per row; NaN where the row has no lexicon word at all."""
    def one(v):
        s, hits = score_text(v)
        return s if hits else float("nan")
    return series.map(one).astype(float)


def label_of(score: float) -> str:
    if score != score:  # NaN
        return "unscored"
    return "positive" if score >= POSITIVE_AT else "negative" if score <= NEGATIVE_AT else "neutral"
