from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from abu_alia.arabic.normalize import normalize_search, tokenize_search
from abu_alia.classification.rules import (
    CHEMISTRY_EVIDENCE,
    FICTION_SLUGS,
    GENERIC_TOKENS,
    MATH_EVIDENCE,
    MEDICINE_OVERRIDE,
    MEDICINE_SLUGS,
    PHYSICS_EVIDENCE,
    POSITIVE,
    RELIGION_MARKERS,
    SCIENCE_SLUGS,
    TAG_MAP,
)

UNCLASSIFIED_SLUG = "unclassified"
CLASSIFICATION_VERSION = 3

_TAG_SPLIT = re.compile(r"[\s:;|/]+")


def _haystack(*parts: str) -> str:
    return " " + normalize_search(" ".join(p for p in parts if p)) + " "


def _contains(hay: str, phrase: str) -> bool:
    p = normalize_search(phrase)
    if not p:
        return False
    if " " in p or len(p) >= 5:
        return p in hay
    return f" {p} " in hay


def _norm_tag(raw: str) -> str:
    s = normalize_search(raw or "")
    return s.replace(" ", "").replace("_", "").replace("@", "").replace("-", "")


def _tag_tokens(values: Sequence[str]) -> List[str]:
    tokens: List[str] = []
    for raw in values:
        if not raw:
            continue
        tokens.append(_norm_tag(raw))
        for part in _TAG_SPLIT.split(str(raw)):
            if part.strip():
                tokens.append(_norm_tag(part))
    return [t for t in tokens if t]


def _tag_slugs(source_genres: Sequence[str], extra_tags: Sequence[str]) -> List[str]:
    token_set = set(_tag_tokens(list(source_genres) + list(extra_tags)))
    found: List[str] = []
    for tkey, slug in TAG_MAP.items():
        if _norm_tag(tkey) in token_set:
            found.append(slug)
    return found


def score_categories(
    *,
    categories: Sequence[Any],
    title: str,
    description: str = "",
    source_genres: Optional[Sequence[str]] = None,
    author_subjects: Optional[Sequence[str]] = None,
    publisher: str = "",
    tags: Optional[Sequence[str]] = None,
    authors: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Score using phrase evidence + tag maps, then veto contradictions."""
    hay = _haystack(
        title,
        description or "",
        publisher or "",
        " ".join(authors or []),
    )
    tokens = set(tokenize_search(hay))
    by_slug = {c.slug: c for c in categories}
    scores: Dict[str, Dict[str, Any]] = {}

    def add(slug: str, points: float, evidence: str) -> None:
        cat = by_slug.get(slug)
        if cat is None:
            return
        row = scores.setdefault(
            slug,
            {
                "category_id": cat.id,
                "slug": slug,
                "path": cat.path,
                "name_ar": cat.name_ar,
                "score": 0.0,
                "evidence": [],
            },
        )
        row["score"] += points
        if evidence not in row["evidence"]:
            row["evidence"].append(evidence)

    for slug, phrases, weight in POSITIVE:
        for ph in phrases:
            pn = normalize_search(ph)
            if pn in GENERIC_TOKENS:
                continue
            if _contains(hay, ph):
                add(slug, weight, "phrase:" + pn)

    for slug in _tag_slugs(source_genres or [], tags or []):
        add(slug, 0.85, "tag:" + slug)

    for subj in author_subjects or []:
        ns = normalize_search(subj)
        for slug, phrases, weight in POSITIVE:
            if any(normalize_search(p) in ns for p in phrases if len(normalize_search(p)) >= 4):
                add(slug, min(0.4, weight * 0.5), "author_subject")
                break

    for cat in categories:
        name_toks = [t for t in tokenize_search(cat.name_ar) if t not in GENERIC_TOKENS and len(t) >= 4]
        if name_toks and all(t in tokens for t in name_toks):
            add(cat.slug, 0.15, "name_in_title")

    religion_hit = any(_contains(hay, m) for m in RELIGION_MARKERS)
    medicine_ok = any(_contains(hay, m) for m in MEDICINE_OVERRIDE)
    tagged = set(_tag_slugs(source_genres or [], tags or []))
    if tagged & (set(SCIENCE_SLUGS) | MEDICINE_SLUGS | {"astronomy"}):
        medicine_ok = medicine_ok or ("medicine" in tagged)

    for slug, row in list(scores.items()):
        if religion_hit and slug in SCIENCE_SLUGS and slug not in tagged:
            row["score"] = 0.0
            row["evidence"].append("veto:religion-vs-science")
        if religion_hit and slug in MEDICINE_SLUGS and not medicine_ok:
            row["score"] = 0.0
            row["evidence"].append("veto:religion-vs-medicine")
        if slug == "modern-history" and religion_hit and not _contains(hay, "التاريخ الحديث"):
            row["score"] = 0.0
            row["evidence"].append("veto:hadith-not-modern-history")
        if religion_hit and slug in FICTION_SLUGS:
            row["score"] = 0.0
            row["evidence"].append("veto:religion-vs-fiction")
        if slug == "chemistry" and _contains(hay, "سعاده"):
            row["score"] = 0.0
            row["evidence"].append("veto:kimiya-al-saada")
        if slug == "tafsir" and _contains(hay, "احلام"):
            row["score"] = 0.0
            row["evidence"].append("veto:dream-interpretation")
        if slug == "economics" and (_contains(hay, "اعتقاد") or _contains(hay, "عقيده")):
            row["score"] = 0.0
            row["evidence"].append("veto:iqtisad-in-belief")
        row["score"] = round(min(1.0, row["score"]), 3)

    results = [r for r in scores.values() if r["score"] > 0]
    results.sort(key=lambda r: (r["score"], r["path"].count("/")), reverse=True)
    return results


def select_assignments(
    scored: List[Dict[str, Any]], low: float = 0.52, extra: float = 0.72
) -> Tuple[List[Dict[str, Any]], bool]:
    if not scored or scored[0]["score"] < low:
        return [], True
    top = scored[0]
    chosen = []
    item = dict(top)
    item["is_primary"] = True
    chosen.append(item)
    top_path = top["path"]
    for row in scored[1:]:
        if row["score"] < extra:
            continue
        p = row["path"]
        if p == top_path or p.startswith(top_path + "/") or top_path.startswith(p + "/"):
            continue
        extra_item = dict(row)
        extra_item["is_primary"] = False
        chosen.append(extra_item)
        if len(chosen) >= 2:
            break
    return chosen, False


def contradictions(title: str, slug: str, tags: Optional[Sequence[str]] = None) -> List[str]:
    hay = _haystack(title)
    issues = []
    religion_hit = any(_contains(hay, m) for m in RELIGION_MARKERS)
    tagged = set(_tag_slugs([], tags or []))
    if religion_hit and slug in SCIENCE_SLUGS and slug not in tagged:
        issues.append("religion_in_science")
    if religion_hit and slug in MEDICINE_SLUGS and not any(_contains(hay, m) for m in MEDICINE_OVERRIDE):
        issues.append("religion_in_medicine")
    if religion_hit and slug in FICTION_SLUGS:
        issues.append("religion_in_fiction")
    if slug == "modern-history" and religion_hit and not _contains(hay, "التاريخ الحديث"):
        issues.append("hadith_in_modern_history")
    if slug == "physics" and not any(_contains(hay, p) for p in PHYSICS_EVIDENCE) and "physics" not in tagged:
        issues.append("physics_without_evidence")
    if slug == "chemistry" and not any(_contains(hay, p) for p in CHEMISTRY_EVIDENCE) and "chemistry" not in tagged:
        issues.append("chemistry_without_evidence")
    if slug == "math" and not any(_contains(hay, p) for p in MATH_EVIDENCE) and "math" not in tagged:
        issues.append("math_without_evidence")
    return issues
