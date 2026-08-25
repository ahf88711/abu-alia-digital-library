from abu_alia.arabic.normalize import normalize_light, normalize_search, slugify_ar, tokenize_search


def test_diacritics_stripped_for_search_not_light():
    raw = "الْكِتَابُ"
    assert "َ" not in normalize_search(raw)
    assert normalize_light(raw).startswith("ال")


def test_alef_variants():
    assert normalize_search("أحمد") == normalize_search("احمد")
    assert normalize_search("إبراهيم") == normalize_search("ابراهيم")


def test_ya_and_alef_maqsura():
    assert normalize_search("علي") == normalize_search("على")


def test_ta_marbuta():
    assert normalize_search("مكتبة") == normalize_search("مكتبه")


def test_tatweel_and_space():
    assert normalize_search("الـــكتاب  العربي") == normalize_search("الكتاب العربي")


def test_digits():
    assert normalize_search("١٢٣") == "123"


def test_persian_letters():
    assert normalize_search("کتاب") == normalize_search("كتاب")


def test_slug():
    s = slugify_ar("كليلة ودمنة")
    assert "كليلة" in s
    assert " " not in s


def test_tokens():
    toks = tokenize_search("كتابُ الأدَبِ")
    assert "كتاب" in toks
    assert "الادب" in toks or "الأدب" in "".join(toks)
