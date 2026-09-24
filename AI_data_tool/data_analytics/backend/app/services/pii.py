"""Detect personal data in a sample, and mask it before the sample leaves.

ARCHITECTURE.md Stage 3.3: masking happens BEFORE anything is written to the
sample cache or sent to the model. There is no path where a raw personal value
reaches either — not "usually", not "unless the model is self-hosted". A
self-hosted endpoint is still a disclosure, and a cache is still a copy.

WHY THE TOKEN CARRIES A HASH
-----------------------------
The obvious masker turns alice@corp.com into a****@c***.com. It is
deterministic and shape-preserving, and it is WRONG for this system.

Stage 4 infers foreign keys by measuring value overlap between two columns in
the masked sample. Under shape-only masking, alice@corp.com and adam@corp.com
both become a****@c***.com — a thousand distinct customers collapse into a
handful of tokens. Overlap ratios computed against that are meaningless, and
inference would confidently propose joins that do not exist, which then
silently corrupts every number a user sees downstream.

So the token embeds a short HMAC of the original value. That buys three things
at once:

  deterministic   same input, same token, every sync
  injective       distinct inputs stay distinct, so overlap survives masking
  irreversible    the HMAC is keyed on the app secret; the token identifies a
                  value without revealing it

Shape is still preserved, because the point of keeping the column at all is
that the model and the review UI can tell what it IS.
"""
from __future__ import annotations

import hashlib
import hmac
import re

from ..core.config import settings

# ── Classifiers ─────────────────────────────────────────────────────────────
# Anchored, because a match anywhere inside free text is not evidence that the
# column holds that kind of value.

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")),
    ("url", re.compile(r"^https?://\S+$", re.IGNORECASE)),
    ("ip", re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")),
    ("iban", re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$")),
    ("phone", re.compile(r"^\+?\d[\d\s\-()]{7,17}\d$")),
    ("coordinate", re.compile(r"^-?\d{1,3}\.\d{3,},\s*-?\d{1,3}\.\d{3,}$")),
]

#: Digit strings of card length are checked with Luhn before being called a
#: card — an order number of the same length would otherwise be masked away.
_CARD_CANDIDATE = re.compile(r"^\d{13,19}$")

#: A national ID here is a long digit run that is NOT a valid card number.
#: Deliberately loose: national formats vary by country, and over-masking an ID
#: column is a far cheaper mistake than leaking one.
_NATIONAL_ID = re.compile(r"^\d{9,20}$")

#: Types that identify a person. Only these are masked. `url`, `coordinate` and
#: the numeric-shape types stay legible because the model needs them to reason
#: about what a column means, and none of them names an individual.
_PII_TYPES = frozenset({"email", "phone", "iban", "credit_card", "national_id"})

#: A column is only classified when most of its non-null values agree. One email
#: address inside a free-text notes column must not turn the whole column into
#: PII — masking it would destroy real data to protect one value.
_MAJORITY = 0.8

#: How many non-null values a sample needs before a verdict is trustworthy.
_MIN_SAMPLE = 3


def _luhn_ok(digits: str) -> bool:
    """The check digit every real payment card carries. Cheap, and it is the
    difference between masking card numbers and masking order numbers."""
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


#: An ISO date or datetime: 2026-02-14, optionally with a time after a space or T.
_ISO_INSTANT = re.compile(
    r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?)?$")


def _classify_one(value: str) -> str | None:
    """The semantic type of a single value, or None."""
    v = value.strip()
    if not v:
        return None

    # A date, first. Deliberately ahead of the pattern list, because an ISO
    # datetime contains colons and digits in shapes that the phone pattern will
    # happily claim, and because an epoch integer must never reach the
    # national-ID branch below -- that mistake masked every date in the database
    # and left the model reasoning about random numbers. `timestamp` is NOT in
    # `_PII_TYPES`: an instant identifies nobody, and masking one is what caused
    # the original damage.
    if _ISO_INSTANT.match(v) or _in_epoch_window(v):
        return "timestamp"

    for name, pattern in _PATTERNS:
        if pattern.match(v):
            # A bare digit run can match the phone pattern; prefer the stricter
            # numeric classifications for something that is all digits.
            if name == "phone" and v.isdigit():
                break
            return name

    if _CARD_CANDIDATE.match(v):
        return "credit_card" if _luhn_ok(v) else "national_id"
    if _NATIONAL_ID.match(v):
        # A Unix epoch in seconds is exactly 10 digits, so `^\d{9,20}$` matched
        # every date in a Moodle/WordPress/log-style schema and masked it. The
        # model then reasoned about a database whose every timestamp it had been
        # shown as a random number -- silently, because a masked national ID and a
        # masked timestamp look alike. The epoch window is narrow (2000-2040) and
        # real national IDs carry a birth date and a checksum, which puts them
        # well outside it: Egypt's are 14 digits, India's 12, South Africa's 13.
        # Trading a rare under-mask for a systematic one is the right way round.
        if _in_epoch_window(v):
            return None
        return "national_id"
    return None


#: Kept in step with `services/ingest.epoch_unit` by the tests, not by an import:
#: this module is Layer 2's masking primitive and must stay free of frame handling.
_EPOCH_S_MIN, _EPOCH_S_MAX = 946684800, 2208988800


def _in_epoch_window(digits: str) -> bool:
    """Is this digit run a plausible Unix timestamp, in seconds or milliseconds?"""
    try:
        n = int(digits)
    except ValueError:
        return False
    return (_EPOCH_S_MIN <= n <= _EPOCH_S_MAX
            or _EPOCH_S_MIN * 1000 <= n <= _EPOCH_S_MAX * 1000)


def classify_value(value) -> str | None:
    """Classify ONE value, with no majority or sample-size rule.

    The column-level `detect_semantic_type` below deliberately refuses to judge
    fewer than `_MIN_SAMPLE` values, because a verdict about a COLUMN drawn from
    one row is not a verdict. That floor makes it useless for the other
    question, which the automation chain has to answer before it hands a profile
    to a model: is THIS particular sampled value an address or a phone number?

    A column of mostly city names with one bare email in it is correctly not a
    personal column -- and that email is still an email. Both readings are
    right; they are answers to different questions, and this is the second one.

    Same anchored patterns as everything else here, so a match still means the
    whole value is of that type rather than containing one. See the module
    docstring on why that anchoring is deliberate.
    """
    if value is None:
        return None
    text = str(value).strip()
    return _classify_one(text) if text else None


def detect_semantic_type(values) -> str | None:
    """Classify a column from a sample of its values.

    Nulls are skipped rather than counted as disagreement — a mostly-empty email
    column is still an email column. Returns None unless a clear majority of the
    non-null values agree, and None for a sample too small to judge.
    """
    present = [str(v) for v in values if v is not None and str(v).strip() != ""]
    if len(present) < _MIN_SAMPLE:
        return None

    counts: dict[str, int] = {}
    for value in present:
        kind = _classify_one(value)
        if kind:
            counts[kind] = counts.get(kind, 0) + 1

    if not counts:
        return None

    kind, hits = max(counts.items(), key=lambda kv: kv[1])
    return kind if hits / len(present) >= _MAJORITY else None


def is_pii(semantic_type: str | None) -> bool:
    """Whether a semantic type names a person and must therefore be masked."""
    return semantic_type in _PII_TYPES


def _token(value: str, length: int = 8) -> str:
    """A short, stable, irreversible discriminator for one value.

    Keyed on the app secret so the mapping cannot be rebuilt from a leaked cache
    with a rainbow table. Eight hex characters is 4 billion buckets — collisions
    within a 1000-row sample are negligible, which is what keeps masked overlap
    ratios faithful to the real ones.
    """
    key = (settings.connector_secret_key or settings.secret_key).encode()
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:length]


def mask_value(value, semantic_type: str | None) -> str | None:
    """Mask one value, preserving its shape.

    None passes through as None. Masking a null would invent a value that is not
    there, and the null_ratio statistic computed from this same sample would
    then be wrong.
    """
    if value is None:
        return None
    text = str(value)
    if not text.strip():
        return text

    digest = _token(text)

    if semantic_type == "email":
        # Keep the TLD so the column still reads as an address; the local part
        # and the domain are both replaced.
        _, _, domain = text.partition("@")
        tld = domain.rsplit(".", 1)[-1] if "." in domain else "com"
        return f"{digest}@masked.{tld}"

    if semantic_type == "phone":
        prefix = "+" if text.strip().startswith("+") else ""
        digits = "".join(ch for ch in text if ch.isdigit())
        # Same digit count, so length-based validation downstream still passes.
        numeric = str(int(digest, 16))
        return prefix + numeric.rjust(len(digits), "0")[-len(digits):]

    if semantic_type == "iban":
        country = text[:2] if len(text) >= 2 else "XX"
        return f"{country}00{digest.upper()}"

    if semantic_type == "credit_card":
        # Last four is the conventional retained fragment, and it is what makes
        # a masked card recognisable to a human reviewing the column.
        return f"****-****-****-{text[-4:]}" if len(text) >= 4 else "****"

    if semantic_type == "national_id":
        numeric = str(int(digest, 16))
        return numeric.rjust(len(text), "0")[-len(text):]

    # Unknown type flagged as PII by a caller: replace wholesale rather than
    # guessing at a shape we do not understand.
    return f"masked_{digest}"


def mask_rows(rows: list[dict], column_types: dict[str, str | None]) -> list[dict]:
    """Mask every PII column across a sample.

    Returns new dicts; the caller's rows are never mutated, because the same
    rows are also used to compute statistics that must reflect the real values.
    """
    pii_columns = {name for name, kind in column_types.items() if is_pii(kind)}
    if not pii_columns:
        return [dict(row) for row in rows]

    masked = []
    for row in rows:
        out = dict(row)
        for name in pii_columns:
            if name in out:
                out[name] = mask_value(out[name], column_types[name])
        masked.append(out)
    return masked
