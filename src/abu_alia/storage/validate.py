from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import filetype
from pypdf import PdfReader

from abu_alia.config import get_settings


class FileValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


PDF_MAGIC = b"%PDF-"
# EPUB is a zip containing mimetype "application/epub+zip"


@dataclass
class ValidatedFile:
    fmt: str
    mime: str
    size_bytes: int
    page_count: Optional[int]


def _read_head(path: Path, n: int = 16) -> bytes:
    with path.open("rb") as fh:
        return fh.read(n)


def validate_book_file(path: Path, expected: Optional[str] = None) -> ValidatedFile:
    settings = get_settings()
    if not path.is_file():
        raise FileValidationError("missing", "الملف غير موجود")
    size = path.stat().st_size
    if size <= 64:
        raise FileValidationError("too_small", "الملف صغير بشكل غير صالح")
    if size > settings.max_file_bytes:
        raise FileValidationError("too_large", "الملف أكبر من الحد المسموح")

    head = _read_head(path, 8)
    guessed = filetype.guess(str(path))
    mime = guessed.mime if guessed else "application/octet-stream"

    if head.startswith(PDF_MAGIC) or mime == "application/pdf":
        if expected and expected != "pdf":
            raise FileValidationError("type_mismatch", "الملف ليس من النوع المتوقع")
        return _validate_pdf(path, size)
    if zipfile.is_zipfile(path):
        return _validate_epub(path, size, expected)
    raise FileValidationError("unknown_type", "صيغة الملف غير مدعومة")


def _validate_pdf(path: Path, size: int) -> ValidatedFile:
    try:
        reader = PdfReader(str(path), strict=False)
        n = len(reader.pages)
        if n < 1:
            raise FileValidationError("corrupt", "ملف PDF بلا صفحات")
        if getattr(reader, "is_encrypted", False) and not reader.decrypt(""):
            raise FileValidationError("encrypted", "ملف PDF محمي بكلمة سر")
    except FileValidationError:
        raise
    except Exception as exc:
        raise FileValidationError("corrupt", "تعذر قراءة ملف PDF") from exc
    return ValidatedFile("pdf", "application/pdf", size, n)


def _validate_epub(path: Path, size: int, expected: Optional[str]) -> ValidatedFile:
    settings = get_settings()
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            if len(names) > settings.max_epub_files:
                raise FileValidationError("zip_bomb", "عدد ملفات EPUB مبالغ فيه")
            uncompressed = 0
            for info in zf.infolist():
                uncompressed += info.file_size
                if uncompressed > settings.max_epub_uncompressed_bytes:
                    raise FileValidationError("zip_bomb", "حجم EPUB غير المضغوط مبالغ فيه")
                if ".." in info.filename.replace("\\", "/").split("/"):
                    raise FileValidationError("unsafe_zip", "مسار غير آمن داخل EPUB")
            try:
                mt = zf.read("mimetype").decode("utf-8").strip()
            except KeyError as exc:
                raise FileValidationError("not_epub", "ليس ملف EPUB صالحاً") from exc
            if mt != "application/epub+zip":
                raise FileValidationError("not_epub", "نوع EPUB غير صحيح")
            if not any(n.endswith("content.opf") or n.endswith(".opf") for n in names):
                raise FileValidationError("not_epub", "ملف EPUB بلا توصيف OPF")
    except FileValidationError:
        raise
    except zipfile.BadZipFile as exc:
        raise FileValidationError("corrupt", "أرشيف تالف") from exc
    if expected and expected != "epub":
        raise FileValidationError("type_mismatch", "الملف ليس من النوع المتوقع")
    return ValidatedFile("epub", "application/epub+zip", size, None)
