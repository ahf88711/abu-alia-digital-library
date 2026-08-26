from pathlib import Path

from abu_alia.ingestion.epub_build import build_epub
from abu_alia.ingestion.pdf_build import build_minimal_pdf
from abu_alia.storage.validate import FileValidationError, validate_book_file


def test_pdf_ok(tmp_path, tmp_env):
    p = tmp_path / "a.pdf"
    build_minimal_pdf(p, "t", "body")
    v = validate_book_file(p, expected="pdf")
    assert v.fmt == "pdf"
    assert v.page_count >= 1


def test_epub_ok(tmp_path, tmp_env):
    p = tmp_path / "a.epub"
    build_epub(p, title="كتاب", author="مؤلف", identifier="x", chapters=[("ف", "<p>نص</p>")])
    v = validate_book_file(p, expected="epub")
    assert v.fmt == "epub"


def test_sample_storage(tmp_path, tmp_env):
    from abu_alia.storage.audit import sample_storage

    root = tmp_path / "audit-storage"
    root.mkdir()
    p = root / "aa" / "bb"
    p.mkdir(parents=True)
    epub = p / "x.epub"
    build_epub(epub, title="كتاب", author="مؤلف", identifier="x", chapters=[("ف", "<p>نص</p>")])
    result = sample_storage(root, limit=10)
    assert result["sampled"] == 1
    assert result["valid"] == 1
    assert result["sha256_collisions_in_sample"] == 0


def test_epub_keeps_more_than_eighty_chapters(tmp_path, tmp_env):
    import zipfile

    from abu_alia.ingestion.epub_build import build_epub

    chaps = [(f"فصل {i}", f"<p>نص {i}</p>") for i in range(1, 91)]
    p = tmp_path / "many.epub"
    build_epub(p, title="كتاب", author="مؤلف", identifier="many", chapters=chaps)
    v = validate_book_file(p, expected="epub")
    assert v.fmt == "epub"
    with zipfile.ZipFile(p) as zf:
        names = [n for n in zf.namelist() if "chap_" in n]
        assert len(names) == 90
        assert zf.testzip() is None


def test_markdown_does_not_drop_paragraphs():
    from abu_alia.ingestion.epub_build import mARkdown_to_chapters

    lines = ["### | ديوان"] + [f"بيت رقم {i} في القصيدة" for i in range(5000)]
    _title, chapters = mARkdown_to_chapters("\n".join(lines))
    total = sum(body.count("<p>") for _t, body in chapters)
    assert total == 5000
    assert len(chapters) > 1


def test_reject_garbage(tmp_path, tmp_env):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello world this is not a book file!!")
    try:
        validate_book_file(p)
        assert False, "should reject"
    except FileValidationError:
        pass


def test_truncated_epub_is_rejected(tmp_path, tmp_env):
    p = tmp_path / "ok.epub"
    build_epub(p, title="كتاب", author="مؤلف", identifier="x", chapters=[("ف", "<p>نص طويل بما يكفي</p>" * 20)])
    data = p.read_bytes()
    assert len(data) > 400
    bad = tmp_path / "trunc.epub"
    bad.write_bytes(data[:-200])
    try:
        validate_book_file(bad, expected="epub")
        assert False, "truncated epub should fail"
    except FileValidationError as exc:
        assert exc.code in {"corrupt", "not_epub", "too_small", "unknown_type"}
