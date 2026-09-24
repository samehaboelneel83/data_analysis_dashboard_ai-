"""How do people feel in this free text? — lexicon sentiment, Arabic first.

Offline and dependency-free: a weighted word list (English and Arabic, MSA plus
common dialect review words) with the three rules that make a lexicon usable on
business text -- negation ("not bad", "مش كويس"), intensifiers on either side of
the word ("very good", "ممتازة جدا") and the "but" shift, where the clause after
"but"/"لكن" outweighs the one before. See services/text_lang.

What it reports beyond the split, because a lexicon is easy to over-trust:

  * **Coverage.** A comment with no lexicon word gets no score -- it is counted
    as *unscored*, never folded into "neutral", which would claim an opinion
    the scorer never read.
  * **The words that drove it**, with how often each fired, so a domain word
    scored wrongly ("cold" in a review of cold drinks) is visible at a glance.
  * **Agreement with a label column** when the data already has one (a star
    rating or a tagged sentiment): the share of comments where the lexicon and
    the label agree. That turns "trust me" into a number.
"""
from __future__ import annotations

from collections import Counter, defaultdict

import pandas as pd

from ..text_lang import LANGUAGE_NAMES, detect_languages, label_of, score_text

MIN_DOCUMENTS = 10
MIN_DOCUMENT_CHARS = 3
EXAMPLES = 3
TOP_WORDS = 12
MAX_GROUPS = 12


class TextSentimentError(ValueError):
    """Not something sentiment can be read from, with the reason."""


def _label_from_column(v) -> str | None:
    """Map a label column's value onto positive/neutral/negative, or None."""
    if v is None or (isinstance(v, float) and v != v):
        return None
    if isinstance(v, (int, float)):
        # a rating: 1-2 negative, 3 neutral, 4-5 positive (or a signed score)
        x = float(v)
        if -1.0 <= x <= 1.0 and x != int(x):
            return "positive" if x > 0.05 else "negative" if x < -0.05 else "neutral"
        return "negative" if x <= 2 else "neutral" if x < 4 else "positive"
    s = str(v).strip().lower()
    if s in ("positive", "pos", "good", "happy", "promoter", "إيجابي", "ايجابي", "positif", "positivo"):
        return "positive"
    if s in ("negative", "neg", "bad", "unhappy", "detractor", "سلبي", "négatif", "negatif", "negativo"):
        return "negative"
    if s in ("neutral", "neu", "mixed", "passive", "محايد", "neutre", "neutro"):
        return "neutral"
    return None


def text_sentiment(df: pd.DataFrame, column: str, group_by: str | None = None,
                   validate_against: str | None = None) -> dict:
    if column not in df.columns:
        raise TextSentimentError(f"Column '{column}' not found")
    series = df[column]
    if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
        raise TextSentimentError(
            f"'{column}' is not text. Sentiment is read from what people wrote, so "
            f"this needs a column of comments or reviews.")
    for extra, what in ((group_by, "Group"), (validate_against, "Label")):
        if extra and extra not in df.columns:
            raise TextSentimentError(f"{what} column '{extra}' not found")

    mask = series.notna() & (series.astype(str).str.strip().str.len() >= MIN_DOCUMENT_CHARS)
    frame = df.loc[mask]
    if len(frame) < MIN_DOCUMENTS:
        raise TextSentimentError(
            f"Only {len(frame)} usable comments; at least {MIN_DOCUMENTS} are needed "
            f"for a split worth reading.")
    texts = frame[column].astype(str).tolist()
    langs = detect_languages(texts)

    scores: list[float | None] = []
    labels: list[str] = []
    word_pos: Counter = Counter()
    word_neg: Counter = Counter()
    for t in texts:
        s, hits = score_text(t)
        if not hits:
            scores.append(None)
            labels.append("unscored")
            continue
        scores.append(s)
        labels.append(label_of(s))
        for w, c in hits:
            (word_pos if c > 0 else word_neg)[w] += 1

    counts = Counter(labels)
    scored = len(texts) - counts.get("unscored", 0)
    if scored == 0:
        raise TextSentimentError(
            f"None of the {len(texts):,} comments contains a word the lexicon knows "
            f"(it covers English and Arabic). Nothing can be said about tone here.")
    scored_values = [s for s in scores if s is not None]
    split = {k: counts.get(k, 0) for k in ("positive", "neutral", "negative", "unscored")}

    ranked = sorted((i for i, s in enumerate(scores) if s is not None), key=lambda i: scores[i])

    def distinct(order, keep) -> list[dict]:
        # distinct comments: a templated reply repeated 30 times is one example
        seen, out = set(), []
        for i in order:
            key = texts[i].strip().lower()
            if key in seen or not keep(scores[i]):
                continue
            seen.add(key)
            out.append({"text": texts[i][:300], "score": scores[i]})
            if len(out) == EXAMPLES:
                break
        return out
    most_negative = distinct(ranked, lambda v: v < 0)
    most_positive = distinct(ranked[::-1], lambda v: v > 0)

    groups = None
    if group_by:
        acc: dict = defaultdict(lambda: {"n": 0, "scored": 0, "sum": 0.0, "positive": 0, "negative": 0})
        for g, s, lab in zip(frame[group_by].astype(str).fillna("(blank)"), scores, labels):
            a = acc[g]
            a["n"] += 1
            if s is not None:
                a["scored"] += 1
                a["sum"] += s
                a["positive"] += lab == "positive"
                a["negative"] += lab == "negative"
        rows = [{"group": g, "comments": a["n"], "scored": a["scored"],
                 "average": round(a["sum"] / a["scored"], 3) if a["scored"] else None,
                 "positive_share": round(a["positive"] / a["scored"], 3) if a["scored"] else None,
                 "negative_share": round(a["negative"] / a["scored"], 3) if a["scored"] else None}
                for g, a in acc.items()]
        rows.sort(key=lambda r: (r["average"] is None, r["average"] if r["average"] is not None else 0))
        groups = {"column": group_by, "rows": rows[:MAX_GROUPS],
                  "omitted": max(0, len(rows) - MAX_GROUPS)}

    agreement = None
    if validate_against:
        truth = [_label_from_column(v) for v in frame[validate_against].tolist()]
        pairs = [(t, lab) for t, lab in zip(truth, labels) if t is not None and lab != "unscored"]
        if pairs:
            agree = sum(1 for t, lab in pairs if t == lab)
            polar = [(t, lab) for t, lab in pairs if t != "neutral"]
            polar_agree = sum(1 for t, lab in polar if t == lab)
            agreement = {
                "column": validate_against, "compared": len(pairs),
                "agreement": round(agree / len(pairs), 3),
                "polar_compared": len(polar),
                "polar_agreement": round(polar_agree / len(polar), 3) if polar else None,
                "unreadable_labels": sum(1 for t in truth if t is None),
            }
        else:
            agreement = {"column": validate_against, "compared": 0, "agreement": None,
                         "note": "None of its values reads as positive/neutral/negative or as a 1–5 rating."}

    lang_names = [LANGUAGE_NAMES.get(code, code) for code in langs["languages"]]
    uncovered = [n for n in lang_names if n not in ("English", "Arabic")]
    caveats = [
        "A lexicon estimate: each comment is scored from the words it contains, with "
        "negation, intensifiers and 'but' handled. It misses sarcasm, and a domain word "
        "can read the wrong way -- check the words that drove the result.",
        f"{split['unscored']:,} of {len(texts):,} comments contain no scored word and are "
        f"left unscored rather than counted as neutral.",
    ]
    if uncovered:
        caveats.append(f"The lexicon covers English and Arabic; this column also looks "
                       f"{', '.join(uncovered)}, whose words are not scored.")
    if agreement and agreement.get("agreement") is not None:
        caveats.append(f"Against '{validate_against}', the lexicon agrees on "
                       f"{agreement['agreement'] * 100:.0f}% of {agreement['compared']:,} comments.")

    return {
        "kind": "text_sentiment",
        "column": column,
        "documents_used": len(texts),
        "documents_skipped": int(len(series) - len(texts)),
        "languages": langs,
        "split": split,
        "coverage": round(scored / len(texts), 3),
        "average": round(sum(scored_values) / len(scored_values), 3),
        "top_positive_words": [{"word": w, "count": c} for w, c in word_pos.most_common(TOP_WORDS)],
        "top_negative_words": [{"word": w, "count": c} for w, c in word_neg.most_common(TOP_WORDS)],
        "most_positive": most_positive,
        "most_negative": most_negative,
        "groups": groups,
        "agreement": agreement,
        "caveats": caveats,
    }
