from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from abu_alia.arabic.normalize import normalize_search, tokenize_search


def score_categories(
    *,
    categories: Sequence[Any],
    title: str,
    description: str = "",
    source_genres: Optional[Sequence[str]] = None,
    author_subjects: Optional[Sequence[str]] = None,
    publisher: str = "",
    tags: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """categories items need slug, name_ar, name_normalized, triggers, path, id."""
    hay_tokens = set(tokenize_search(" ".join([title, description, publisher, " ".join(tags or [])])))
    source_genres = [normalize_search(g) for g in (source_genres or [])]
    author_subjects = [normalize_search(s) for s in (author_subjects or [])]
    results: List[Dict[str, Any]] = []
    for cat in categories:
        triggers = [normalize_search(t) for t in (cat.triggers or [])]
        evidence: List[str] = []
        score = 0.0
        # title/description token overlap with triggers
        hit = 0
        for tr in triggers:
            parts = tr.split()
            if all(p in hay_tokens for p in parts if p):
                hit += 1
                evidence.append("trigger:" + tr)
        if triggers:
            score += min(0.7, 0.18 * hit + (0.35 if hit else 0))
        for g in source_genres:
            for tr in triggers:
                if tr and tr in g:
                    score += 0.45
                    evidence.append("source_genre:" + g)
                    break
        for subj in author_subjects:
            for tr in triggers:
                if tr and tr in subj:
                    score += 0.25
                    evidence.append("author_subject:" + subj)
                    break
        name_toks = set(tokenize_search(cat.name_ar))
        if name_toks and name_toks <= hay_tokens:
            score += 0.2
            evidence.append("name_in_title")
        score = min(1.0, score)
        if score <= 0:
            continue
        results.append(
            {
                "category_id": cat.id,
                "slug": cat.slug,
                "path": cat.path,
                "name_ar": cat.name_ar,
                "score": round(score, 3),
                "evidence": evidence,
            }
        )
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def select_assignments(scored: List[Dict[str, Any]], low: float = 0.45, extra: float = 0.55) -> Tuple[List[Dict[str, Any]], bool]:
    if not scored:
        return [], True
    top = scored[0]
    needs_review = top["score"] < low
    chosen = []
    if top["score"] >= low:
        item = dict(top)
        item["is_primary"] = True
        chosen.append(item)
        top_path = top["path"]
        for row in scored[1:]:
            if row["score"] < extra:
                break
            # skip ancestors/descendants of primary
            p = row["path"]
            if p == top_path or p.startswith(top_path + "/") or top_path.startswith(p + "/"):
                continue
            extra_item = dict(row)
            extra_item["is_primary"] = False
            chosen.append(extra_item)
            if len(chosen) >= 3:
                break
    return chosen, needs_review
