"""Arabic normalization for matching/search. Display text is never mutated in place."""
from __future__ import annotations

import re
import unicodedata
from typing import List

TATWEEL = "\u0640"
DIACRITICS_RE = re.compile(
    r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u08D3-\u08E1\u08E3-\u08FF]"
)
PUNCT_RE = re.compile(
    r"[^\w\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\u0660-\u0669\u06F0-\u06F9]+",
    flags=re.UNICODE,
)
WHITESPACE_RE = re.compile(r"\s+")
ALEF_RE = re.compile(r"[إأآٱٲٳأ]")
# presentation forms folded via NFKC first

ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

PERSIAN_MAP = str.maketrans(
    {
        "ک": "ك",
        "ڪ": "ك",
        "ی": "ي",
        "ى": "ي",
        "ۀ": "ه",
        "ھ": "ه",
        "ە": "ه",
        "ؤ": "و",
        "ئ": "ي",
        "ة": "ه",
        "ں": "ن",
    }
)


def collapse_whitespace(text: str) -> str:
    return WHITESPACE_RE.sub(" ", (text or "").strip())


def digits_to_latin(text: str) -> str:
    return (text or "").translate(ARABIC_INDIC)


def _nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


def normalize_light(text: str) -> str:
    """Safe cleanup that does not merge distinct letters."""
    s = _nfkc(text)
    s = s.replace(TATWEEL, "")
    s = collapse_whitespace(s)
    return s


def normalize_search(text: str) -> str:
    """Aggressive matching form. Do not use for display."""
    s = _nfkc(text)
    s = s.replace(TATWEEL, "")
    s = DIACRITICS_RE.sub("", s)
    s = ALEF_RE.sub("ا", s)
    s = s.translate(PERSIAN_MAP)
    s = digits_to_latin(s)
    s = s.lower()
    s = PUNCT_RE.sub(" ", s)
    s = collapse_whitespace(s)
    return s


def tokenize_search(text: str) -> List[str]:
    s = normalize_search(text)
    return [t for t in s.split(" ") if t]


def slugify_ar(text: str, max_len: int = 80) -> str:
    s = normalize_light(text)
    s = DIACRITICS_RE.sub("", s)
    s = ALEF_RE.sub("ا", s)
    s = s.translate(str.maketrans({"ى": "ي", "ی": "ي", "ک": "ك"}))
    s = digits_to_latin(s)
    s = re.sub(r"[^\w\u0600-\u06FF]+", "-", s, flags=re.UNICODE)
    s = re.sub(r"-{2,}", "-", s).strip("-").lower()
    if not s:
        s = "item"
    return s[:max_len].rstrip("-")
