from types import SimpleNamespace

from abu_alia.classification.engine import contradictions, score_categories, select_assignments
from abu_alia.classification.reclassify import clean_display_title, prefer_arabic_segment


def _cats():
    return [
        SimpleNamespace(id=1, slug="hadith", name_ar="الحديث وعلومه", path="din/hadith", triggers=[]),
        SimpleNamespace(id=2, slug="novels", name_ar="الروايات", path="novels", triggers=[]),
        SimpleNamespace(id=3, slug="physics", name_ar="الفيزياء", path="sciences/physics", triggers=[]),
        SimpleNamespace(id=4, slug="chemistry", name_ar="الكيمياء", path="sciences/chemistry", triggers=[]),
        SimpleNamespace(id=5, slug="modern-history", name_ar="التاريخ الحديث", path="history/modern-history", triggers=[]),
        SimpleNamespace(id=6, slug="sciences", name_ar="العلوم", path="sciences", triggers=[]),
        SimpleNamespace(id=7, slug="medicine", name_ar="الطب والصحة", path="medicine", triggers=[]),
        SimpleNamespace(id=8, slug="math", name_ar="الرياضيات", path="math", triggers=[]),
        SimpleNamespace(id=9, slug="fiqh", name_ar="الفقه", path="din/fiqh", triggers=[]),
        SimpleNamespace(id=10, slug="quran", name_ar="القرآن وعلومه", path="din/quran", triggers=[]),
        SimpleNamespace(id=11, slug="poetry", name_ar="الشعر", path="adab/poetry", triggers=[]),
        SimpleNamespace(id=12, slug="tarajim", name_ar="التراجم والسير", path="tarajim", triggers=[]),
        SimpleNamespace(id=13, slug="arabic-adab", name_ar="الأدب العربي", path="adab/arabic-adab", triggers=[]),
        SimpleNamespace(id=14, slug="astronomy", name_ar="الفلك", path="sciences/astronomy", triggers=[]),
        SimpleNamespace(id=15, slug="sociology", name_ar="علم الاجتماع", path="sociology", triggers=[]),
        SimpleNamespace(id=16, slug="economics", name_ar="الاقتصاد", path="economics", triggers=[]),
        SimpleNamespace(id=17, slug="balagha", name_ar="البلاغة", path="arabic-lang/balagha", triggers=[]),
    ]


def test_hadith_from_source_genre():
    scored = score_categories(categories=_cats(), title="صحيح البخاري", source_genres=["GAL@hadith"])
    assert scored[0]["slug"] == "hadith"
    chosen, review = select_assignments(scored)
    assert chosen[0]["is_primary"] is True
    assert review is False


def test_openiti_hadith_tag_not_modern_history():
    scored = score_categories(
        categories=_cats(),
        title="من حديث أبي عبيدة",
        tags=["_HADITH", "_AJZA"],
    )
    assert scored[0]["slug"] == "hadith"
    slugs = [r["slug"] for r in scored]
    assert "modern-history" not in slugs


def test_fiqh_not_in_physics():
    scored = score_categories(categories=_cats(), title="كتاب الفقه الأكبر", tags=["_FIQH"])
    assert scored[0]["slug"] == "fiqh"
    assert all(r["slug"] != "physics" for r in scored)


def test_quran_not_in_sciences():
    scored = score_categories(categories=_cats(), title="غريب القرآن في شعر العرب", tags=["_QURAN"])
    assert scored[0]["slug"] in {"quran", "poetry"}
    assert all(r["slug"] not in {"sciences", "physics", "chemistry"} for r in scored)


def test_medicine_keeps_real_medical_title():
    scored = score_categories(categories=_cats(), title="فردوس الحكمة في الطب", tags=["_TIBB"])
    assert scored[0]["slug"] == "medicine"


def test_tabaqat_not_medicine():
    scored = score_categories(categories=_cats(), title="طبقات الصوفية", tags=["_TABAQAT"])
    chosen, _ = select_assignments(scored)
    if chosen:
        assert chosen[0]["slug"] != "medicine"


def test_math_requires_evidence():
    scored = score_categories(categories=_cats(), title="رياض الأفهام في شرح عمدة الأحكام", tags=["_FIQH"])
    assert scored[0]["slug"] == "fiqh"
    assert all(r["slug"] != "math" for r in scored)


def test_riwaya_isnad_is_not_a_novel():
    scored = score_categories(
        categories=_cats(),
        title="مسند أبي حنيفة رواية الحصكفي",
        tags=["_HADITH", "_MASANID"],
    )
    assert scored[0]["slug"] == "hadith"
    assert all(r["slug"] != "novels" for r in scored)


def test_uncertain_title_unclassified():
    scored = score_categories(categories=_cats(), title="الدرة اليتيمة")
    chosen, needs = select_assignments(scored)
    assert chosen == []
    assert needs is True


def test_contradictions_religion_in_physics():
    issues = contradictions("فقه العبادات", "physics")
    assert "religion_in_science" in issues


def test_contradictions_physics_without_evidence():
    issues = contradictions("رسالة في الأخلاق", "physics")
    assert "physics_without_evidence" in issues


def test_prefer_arabic_segment():
    t = prefer_arabic_segment("الموطأ :: al-Muwatta")
    assert "الموطأ" in t
    assert "Muwatta" not in t


def test_clean_pilcrow():
    t = clean_display_title("مسائل الامام أحمد¶    بن حنبل")
    assert "¶" not in t
    assert "أحمد" in t


def test_poetry_from_diwan():
    scored = score_categories(categories=_cats(), title="ديوان أوس بن حجر", tags=["_SHICR"])
    assert scored[0]["slug"] == "poetry"


def test_astronomy_almagest():
    scored = score_categories(categories=_cats(), title="al-Majisṭī", tags=["GAL@astronomy"])
    assert scored[0]["slug"] == "astronomy"


def test_sociology_not_from_letter_ayn():
    scored = score_categories(categories=_cats(), title="مسائل علي بن جعفر")
    assert all(r["slug"] != "sociology" for r in scored)


def test_muallaqa_is_poetry():
    scored = score_categories(categories=_cats(), title="معلقة عنترة")
    chosen, needs = select_assignments(scored)
    assert chosen and chosen[0]["slug"] == "poetry"


def test_kimiya_al_saada_not_chemistry():
    scored = score_categories(categories=_cats(), title="كيمياء السعادة")
    assert all(r["slug"] != "chemistry" for r in scored)


def test_iqtisad_belief_not_economics():
    cats = _cats() + [SimpleNamespace(id=20, slug="economics", name_ar="الاقتصاد", path="economics", triggers=[])]
    scored = score_categories(categories=cats, title="الاقتصاد في الاعتقاد")
    assert all(r["slug"] != "economics" for r in scored)


def test_diwan_prefers_poetry_over_balagha_tag():
    cats = _cats() + [SimpleNamespace(id=21, slug="balagha", name_ar="البلاغة", path="arabic-lang/balagha", triggers=[])]
    scored = score_categories(categories=cats, title="ديوان طرفة بن العبد", tags=["_BALAGHA", "_SHICR"])
    assert scored[0]["slug"] == "poetry"
