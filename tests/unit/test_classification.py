from types import SimpleNamespace

from abu_alia.classification.engine import score_categories, select_assignments


def test_hadith_from_source_genre():
    cats = [
        SimpleNamespace(id=1, slug="hadith", name_ar="الحديث وعلومه", path="din/hadith", triggers=["حديث", "gal@hadith"]),
        SimpleNamespace(id=2, slug="novels", name_ar="الروايات", path="novels", triggers=["رواية"]),
    ]
    scored = score_categories(categories=cats, title="صحيح البخاري", source_genres=["GAL@hadith"])
    assert scored[0]["slug"] == "hadith"
    chosen, review = select_assignments(scored)
    assert chosen[0]["is_primary"] is True
