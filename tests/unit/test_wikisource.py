from abu_alia.connectors.registry import get_connector
from abu_alia.connectors.wikisource import extracted_length, wikitext_to_chapters
from abu_alia.rights.eligibility import Eligibility, decide_eligibility


def test_wikitext_splits_headings_and_strips_templates():
    text = """
{{رأس}}
مقدمة الكتاب في العلم.

== الباب الأول ==

هذا فصل طويل بما يكفي للمتن العربي المستخرج من ويكي مصدر.

== الباب الثاني ==

فصل آخر [[رابط|ظاهر]] بعد إزالة القوالب.
"""
    chapters = wikitext_to_chapters(text)
    titles = [c[0] for c in chapters]
    assert "الباب الأول" in titles
    assert "الباب الثاني" in titles
    joined = "".join(c[1] for c in chapters)
    assert "ظاهر" in joined
    assert "رأس" not in joined
    assert extracted_length(chapters) > 20


def test_redirects_are_empty():
    assert wikitext_to_chapters("#تحويل [[كتاب]]") == []


def test_wikisource_connector_registered():
    assert get_connector("wikisource_ar").source_code == "wikisource_ar"


def test_wikisource_cc_by_sa():
    d = decide_eligibility(
        source_code="wikisource_ar",
        license_url="https://creativecommons.org/licenses/by-sa/3.0/",
    )
    assert d["eligibility"] == Eligibility.VERIFIED_OPEN_LICENSE
    assert d["license"].code == "cc-by-sa-3.0"
