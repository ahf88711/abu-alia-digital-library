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


def test_wikisource_keeps_all_chapters(tmp_path, tmp_env, monkeypatch):
    from abu_alia.connectors import wikisource as ws
    from abu_alia.connectors.base import RemoteFile

    headings = "\n".join(
        f"== باب {i} ==\n" + ("نص عربي كافٍ للمتن المستخرج من المصدر. " * 8) for i in range(1, 91)
    )
    payload = {
        "query": {
            "pages": {
                "1": {
                    "revisions": [
                        {"slots": {"main": {"*": headings}}}
                    ]
                }
            }
        }
    }
    captured = {}

    def fake_api(self, params):
        return payload

    def fake_build(dest, **kwargs):
        captured["n"] = len(list(kwargs["chapters"]))
        dest.write_bytes(b"PK\x03\x04placeholder")
        return dest

    monkeypatch.setattr(ws.WikisourceArConnector, "_api", fake_api)
    monkeypatch.setattr(ws, "build_epub", fake_build)
    monkeypatch.setattr(ws, "extracted_length", lambda chapters: 5000)
    monkeypatch.setattr("abu_alia.storage.validate.validate_book_file", lambda *a, **k: None)
    conn = ws.WikisourceArConnector()
    dest = tmp_path / "w.epub"
    conn.download(RemoteFile(url="https://example.test", fmt="epub", filename="w.epub", extra={"title": "كتاب"}), dest)
    assert captured["n"] == 90


def test_wikisource_cc_by_sa():
    d = decide_eligibility(
        source_code="wikisource_ar",
        license_url="https://creativecommons.org/licenses/by-sa/3.0/",
    )
    assert d["eligibility"] == Eligibility.VERIFIED_OPEN_LICENSE
    assert d["license"].code == "cc-by-sa-3.0"
