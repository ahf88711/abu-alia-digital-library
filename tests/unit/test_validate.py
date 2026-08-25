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


def test_reject_garbage(tmp_path, tmp_env):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello world this is not a book file!!")
    try:
        validate_book_file(p)
        assert False, "should reject"
    except FileValidationError:
        pass
