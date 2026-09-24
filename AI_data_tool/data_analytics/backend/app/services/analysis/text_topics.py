"""What is this free text about? — topics from a column of comments.

The last analysis SAS has that this catalogue did not, and it needs no new
dependency: scikit-learn is already here for segmentation and the decision
tree.

**NMF over TF-IDF rather than LDA over counts.** Business comments are a few
dozen words each, and on short documents LDA's generative assumption has little
to work with while raw counts let common words dominate. Term weighting is what
stops "the order" and "the delivery" collapsing into one topic about "the". NMF
is also deterministic given a seed, which matters here for the same reason it
matters in `segment.py`: two runs of one analysis that disagree are two answers
presented as one fact.

Three things this is careful not to over-sell, because a topic model is
unusually easy to:

  * **A topic is a cluster of words, not a label.** "delivery late arrived
    driver" is what the model found. Calling it "Logistics complaints" is a
    human judgement, and the result says so rather than implying the machine
    made it.

  * **Stop lists follow the language.** The column's language is detected
    (Arabic by script; English, French, Spanish, German by their common words)
    and each detected language's list is removed -- a bilingual column gets
    both. Arabic is normalised first (diacritics, alef forms, the article), so
    "الخدمة" and "خدمه" are one word. Other languages are named as uncovered
    rather than left to be discovered from a topic reading "de la el los".

  * **Tone per topic, not per claim.** Each topic carries the average lexicon
    sentiment of its comments and how many of them the lexicon could score
    (services/text_lang). It is a lexicon: negation and intensifiers are
    handled, sarcasm is not, and the full split lives in `text_sentiment`.
"""
from __future__ import annotations

import pandas as pd

RANDOM_STATE = 42

#: Below this there is not enough text for any clustering to mean anything.
MIN_DOCUMENTS = 20
#: A document shorter than this is a shrug ("ok", "n/a"), not a comment.
MIN_DOCUMENT_CHARS = 5
#: Roughly this many documents per topic, or the topics are noise.
DOCUMENTS_PER_TOPIC = 5
MAX_TOPICS = 20
DEFAULT_TOPICS = 5
DEFAULT_TERMS = 8
#: Examples per topic: enough to judge the cluster, few enough to read.
EXAMPLES_PER_TOPIC = 3
#: A term appearing in nearly every document separates nothing.
MAX_DOCUMENT_FREQUENCY = 0.85


class TextTopicsError(ValueError):
    """Not something topics can be found in, with the reason."""


def text_topics(df: pd.DataFrame, column: str, topics: int = DEFAULT_TOPICS,
                max_terms: int = DEFAULT_TERMS,
                stop_words: list[str] | None = None,
                language: str | None = "auto") -> dict:
    """Cluster a free-text column into topics, with the comments behind each."""
    import numpy as np
    from sklearn.decomposition import NMF
    from sklearn.feature_extraction.text import TfidfVectorizer

    from ..text_lang import (LANGUAGE_NAMES, LANGUAGES, detect_languages, normalize_arabic,
                             score_text, stop_words_for, tokens)

    if column not in df.columns:
        raise TextTopicsError(f"Column '{column}' not found")
    series = df[column]
    if pd.api.types.is_numeric_dtype(series) or \
            pd.api.types.is_datetime64_any_dtype(series):
        raise TextTopicsError(
            f"'{column}' is not text. Topics come from what people wrote, so "
            f"this needs a column of comments, descriptions or free notes.")

    raw = series.dropna().astype(str)
    documents = [d.strip() for d in raw if len(d.strip()) >= MIN_DOCUMENT_CHARS]
    skipped = len(series) - len(documents)
    if len(documents) < MIN_DOCUMENTS:
        raise TextTopicsError(
            f"Only {len(documents)} usable comments; at least {MIN_DOCUMENTS} "
            f"are needed before clusters mean anything.")

    wanted = max(2, min(int(topics or DEFAULT_TOPICS), MAX_TOPICS))
    if wanted * DOCUMENTS_PER_TOPIC > len(documents):
        raise TextTopicsError(
            f"{wanted} topics from {len(documents)} comments would be noise -- "
            f"allow about {DOCUMENTS_PER_TOPIC} comments per topic, so at most "
            f"{max(2, len(documents) // DOCUMENTS_PER_TOPIC)} here.")

    detected = detect_languages(documents)
    if language and language != "auto":
        if language not in LANGUAGES:
            raise TextTopicsError(f"Unknown language '{language}' (use auto or one of {', '.join(LANGUAGES)})")
        langs = [language]
    else:
        langs = detected["languages"] or ["en"]
    extra = {tok for w in (stop_words or []) for tok in tokens(normalize_arabic(str(w)))}
    stop_set = stop_words_for(langs) | extra

    def analyse(doc: str) -> list[str]:
        return [t for t in tokens(doc) if t not in stop_set and len(t) > 1]

    vectoriser = TfidfVectorizer(analyzer=analyse, max_df=MAX_DOCUMENT_FREQUENCY, min_df=1)
    try:
        matrix = vectoriser.fit_transform(documents)
    except ValueError as e:
        raise TextTopicsError(
            f"No vocabulary left after removing common words: {e}")
    terms = vectoriser.get_feature_names_out()
    if len(terms) < wanted:
        raise TextTopicsError(
            f"Only {len(terms)} distinct words remain after removing common "
            f"ones -- not enough vocabulary for {wanted} topics.")

    model = NMF(n_components=wanted, random_state=RANDOM_STATE,
                init="nndsvda", max_iter=400)
    weights = model.fit_transform(matrix)          # document x topic
    components = model.components_                 # topic x term

    # Each document belongs to its strongest topic. A document may genuinely
    # touch two, but "this comment is mostly about X" is what a reader can act
    # on, and a soft assignment shown as a count would double-count.
    assignment = np.asarray(weights).argmax(axis=1)

    out_topics = []
    for index in range(wanted):
        ranked = np.asarray(components[index]).argsort()[::-1][:max_terms]
        members = [documents[i] for i, a in enumerate(assignment) if a == index]
        # The most representative examples, not the first ones found: a topic
        # judged by its weakest members reads as incoherent when it is not.
        strongest = sorted(
            (i for i, a in enumerate(assignment) if a == index),
            key=lambda i: float(weights[i][index]), reverse=True)
        member_scores = [score_text(documents[i]) for i, a in enumerate(assignment) if a == index]
        scored = [sc for sc, hits in member_scores if hits]
        out_topics.append({
            "rank": index + 1,
            "sentiment": {"average": round(sum(scored) / len(scored), 3) if scored else None,
                          "scored": len(scored)},
            "terms": [{"term": str(terms[t]),
                       "weight": round(float(components[index][t]), 4)}
                      for t in ranked if components[index][t] > 0],
            "documents": len(members),
            "examples": [documents[i][:300] for i in strongest[:EXAMPLES_PER_TOPIC]],
        })
    out_topics.sort(key=lambda t: t["documents"], reverse=True)
    for position, topic in enumerate(out_topics, start=1):
        topic["rank"] = position

    caveats = [
        "A topic is a cluster of words the model found together, not a name. "
        "Reading 'delivery late driver' as 'logistics complaints' is your "
        "judgement, not the model's.",
        f"Common {' and '.join(LANGUAGE_NAMES.get(x, x) for x in langs)} words are removed"
        + (" (detected from the text)" if not language or language == "auto" else " (as chosen)")
        + "; words of any other language will dominate topics unless added to the stop list.",
        # Named so nobody reads the tone as more than it is.
        "Each topic's tone is the average lexicon sentiment of the comments the "
        "lexicon could score (English and Arabic, with negation handled); it misses "
        "sarcasm. Run 'text sentiment' for the full split and the words behind it.",
        f"Each comment is counted under its single strongest topic, across "
        f"{len(documents):,} comments.",
    ]
    if skipped:
        caveats.append(
            f"{skipped:,} row(s) were empty or too short to be a comment.")

    return {
        "kind": "text_topics",
        "column": column,
        "topics": out_topics,
        "documents_used": len(documents),
        "documents_skipped": int(skipped),
        "vocabulary": int(len(terms)),
        "languages": langs,
        "detected": detected,
        "caveats": caveats,
    }
