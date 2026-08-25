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


def test_reject_garbage(tmp_path, tmp_env):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello world this is not a book file!!")
    try:
        validate_book_file(p)
        assert False, "should reject"
    except FileValidationError:
        pass
