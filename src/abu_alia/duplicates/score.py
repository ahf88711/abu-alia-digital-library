from __future__ import annotations

from typing import Any, Dict, Optional


def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    jacc = inter / union if union else 0.0
    # prefix bonus for shared start
    n = min(12, len(a), len(b))
    prefix = 1.0 if a[:n] == b[:n] else 0.0
    return min(1.0, jacc * 0.85 + prefix * 0.15)


def score_duplicate(
    *,
    left_sha: Optional[str] = None,
    right_sha: Optional[str] = None,
    left_isbn: Optional[str] = None,
    right_isbn: Optional[str] = None,
    left_title: str = "",
    right_title: str = "",
    left_author: str = "",
    right_author: str = "",
    left_year: Optional[int] = None,
    right_year: Optional[int] = None,
    left_pages: Optional[int] = None,
    right_pages: Optional[int] = None,
    left_size: Optional[int] = None,
    right_size: Optional[int] = None,
) -> Dict[str, Any]:
    signals: Dict[str, Any] = {}
    if left_sha and right_sha and left_sha == right_sha:
        return {
            "score": 1.0,
            "kind": "identical_file",
            "auto_merge": True,
            "signals": {"sha256": 1.0},
        }
    if left_isbn and right_isbn and left_isbn == right_isbn:
        return {
            "score": 0.95,
            "kind": "same_edition_isbn",
            "auto_merge": True,
            "signals": {"isbn": 0.95},
        }
    title_s = _sim(left_title, right_title)
    author_s = _sim(left_author, right_author)
    signals["title"] = round(title_s, 3)
    signals["author"] = round(author_s, 3)
    year_s = 0.0
    if left_year and right_year:
        year_s = 1.0 if left_year == right_year else (0.4 if abs(left_year - right_year) <= 2 else 0.0)
        signals["year"] = year_s
    pages_s = 0.0
    if left_pages and right_pages and max(left_pages, right_pages):
        delta = abs(left_pages - right_pages) / max(left_pages, right_pages)
        pages_s = max(0.0, 1.0 - delta * 4)
        signals["pages"] = round(pages_s, 3)
    size_s = 0.0
    if left_size and right_size:
        delta = abs(left_size - right_size) / max(left_size, right_size)
        size_s = max(0.0, 1.0 - delta * 5)
        signals["size"] = round(size_s, 3)

    score = title_s * 0.5 + author_s * 0.3 + year_s * 0.1 + pages_s * 0.05 + size_s * 0.05
    if title_s >= 0.92 and author_s >= 0.8 and year_s == 1.0:
        kind = "same_edition_candidate"
        auto = False
    elif title_s >= 0.9 and author_s >= 0.8:
        kind = "same_work_candidate"
        auto = False
    elif title_s >= 0.92 and author_s < 0.4:
        kind = "similar_title_different_author"
        auto = False
        score = min(score, 0.45)
    else:
        kind = "weak"
        auto = False
    return {
        "score": round(min(0.94, score), 3),
        "kind": kind,
        "auto_merge": auto,
        "signals": signals,
    }
