from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence

from abu_alia.config import get_settings
from abu_alia.connectors.base import DiscoveredItem, HttpMixin, RemoteFile, SourceMetadata
from abu_alia.ingestion.epub_build import build_epub, mARkdown_to_chapters
from abu_alia.net.http import RetryableHTTPError, get_with_fallback

METADATA_PATH = "metadata/OpenITI_metadata_2025-1-9.tsv"
METADATA_URLS = (
    "https://raw.githubusercontent.com/OpenITI/RELEASE/master/" + METADATA_PATH,
    "https://cdn.jsdelivr.net/gh/OpenITI/RELEASE@master/" + METADATA_PATH,
)


def death_year_from_uri(uri: str) -> Optional[int]:
    if not uri:
        return None
    prefix = uri.split(".", 1)[0][:4]
    if prefix.isdigit():
        return int(prefix)
    return None


def century_repo(death_ah: int) -> str:
    bucket = ((max(death_ah, 1) - 1) // 25 + 1) * 25
    return f"{bucket:04d}AH"


def _normalize_local_path(local_path: str) -> str:
    path = (local_path or "").lstrip("/")
    if not path.startswith("data/"):
        path = "data/" + path
    return path


def candidate_urls(local_path: str, death_ah: int) -> List[str]:
    repo = century_repo(death_ah or 1)
    rest = _normalize_local_path(local_path)
    bases = [
        f"https://raw.githubusercontent.com/OpenITI/{repo}/master/{rest}",
        f"https://cdn.jsdelivr.net/gh/OpenITI/{repo}@master/{rest}",
    ]
    urls: List[str] = []
    for base in bases:
        urls.append(base)
        for ext in (".completed", ".mARkdown"):
            urls.append(base + ext)
    return urls


class OpenITIConnector(HttpMixin):
    source_code = "openiti"

    def __init__(self) -> None:
        super().__init__()
        self._min_interval = 0.35
        self._by_id: Dict[str, Dict[str, str]] = {}

    def _load_rows(self) -> List[Dict[str, str]]:
        settings = get_settings()
        settings.cache_root.mkdir(parents=True, exist_ok=True)
        cache = settings.cache_root / "openiti_metadata_2025-1-9.tsv"
        text = None
        if cache.exists() and cache.stat().st_size > 500_000:
            text = cache.read_text(encoding="utf-8", errors="replace")
        else:
            resp = get_with_fallback(self._client, METADATA_URLS, attempts=settings.http_attempts)
            text = resp.text
            cache.write_text(text, encoding="utf-8")
        reader = csv.DictReader(io.StringIO(text), delimiter="\t")
        return list(reader)

    def discover(self, cursor: Optional[str] = None) -> Iterator[DiscoveredItem]:
        settings = get_settings()
        rows = self._load_rows()
        best: Dict[str, Dict[str, str]] = {}
        for row in rows:
            lang = (row.get("language") or "").lower()
            if lang not in ("ara", "ar", "arabic"):
                continue
            if str(row.get("uncorrected_OCR") or "").lower() in ("true", "1", "yes"):
                continue
            book = row.get("book") or row.get("version_uri", "").rsplit(".", 1)[0]
            if not book:
                continue
            death = death_year_from_uri(row.get("version_uri") or book)
            if death and death > settings.openiti_max_death_ah:
                continue
            try:
                toks = int(float(row.get("tok_length") or 0))
            except (TypeError, ValueError):
                toks = 0
            if toks > settings.openiti_max_tokens:
                continue
            status = (row.get("status") or "").lower()
            local = row.get("local_path") or ""
            score = 0
            if "completed" in local:
                score += 3
            if "markdown" in local.lower() or "mARkdown" in local:
                score += 2
            if status in ("pri", "primary"):
                score += 1
            prev = best.get(book)
            prev_score = int(prev.get("_score", 0)) if prev else -1
            if score >= prev_score:
                row = dict(row)
                row["_score"] = str(score)
                best[book] = row
        for book, row in best.items():
            self._by_id[book] = row
            death = death_year_from_uri(row.get("version_uri") or book) or 1
            yield DiscoveredItem(
                external_id=book,
                url=candidate_urls(row.get("local_path") or "", death)[0],
                title=row.get("title_ar") or book,
                raw=row,
            )

    def fetch_metadata(self, item: DiscoveredItem) -> SourceMetadata:
        row = item.raw or self._by_id.get(item.external_id) or {}
        death = death_year_from_uri(row.get("version_uri") or item.external_id)
        tags = [t.strip() for t in (row.get("tags") or "").split("::") if t.strip()]
        return SourceMetadata(
            title=(row.get("title_ar") or item.title or item.external_id).strip(),
            authors=[(row.get("author_ar") or "").strip() or "مؤلف غير معروف"],
            description=None,
            language="ar",
            license_url="https://creativecommons.org/licenses/by-nc-sa/4.0/",
            genres=tags,
            tags=tags,
            death_year_ah=death,
            extra={
                "version_uri": row.get("version_uri"),
                "local_path": row.get("local_path"),
                "tok_length": row.get("tok_length"),
            },
        )

    def discover_files(self, item: DiscoveredItem, meta: SourceMetadata) -> List[RemoteFile]:
        row = item.raw or {}
        urls = candidate_urls(row.get("local_path") or "", meta.death_year_ah or 1)
        return [
            RemoteFile(
                url=urls[0],
                fmt="epub",
                filename=f"{item.external_id}.epub",
                extra={"source": "openiti-text", "urls": urls},
            )
        ]

    def download(self, remote: RemoteFile, dest: Path) -> Path:
        urls: Sequence[str] = remote.extra.get("urls") or ([remote.url] if remote.url else [])
        if not urls:
            raise RuntimeError("missing openiti url")
        resp = get_with_fallback(self._client, list(urls), attempts=self._attempts)
        text = resp.text
        if len(text.strip()) < 80:
            raise RetryableHTTPError("openiti text too short")
        guessed_title, chapters = mARkdown_to_chapters(text)
        author = (remote.extra or {}).get("author") or "OpenITI"
        title = (remote.extra or {}).get("title") or guessed_title or dest.stem
        build_epub(
            dest,
            title=title,
            author=author,
            identifier="openiti:" + dest.stem,
            chapters=chapters,
            attribution=(
                "النص من مدونة OpenITI المرخّصة برخصة المشاع الإبداعي "
                "نسب المصنف — غير تجاري — الترخيص بالمثل 4.0."
            ),
        )
        from abu_alia.storage.validate import validate_book_file

        validate_book_file(dest, expected="epub")
        return dest
