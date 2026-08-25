from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from abu_alia.config import get_settings
from abu_alia.connectors.base import DiscoveredItem, HttpMixin, RemoteFile, SourceMetadata
from abu_alia.ingestion.epub_build import build_epub, mARkdown_to_chapters

METADATA_URL = (
    "https://raw.githubusercontent.com/OpenITI/RELEASE/master/metadata/"
    "OpenITI_metadata_2025-1-9.tsv"
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


def github_raw_url(local_path: str, death_ah: int) -> str:
    repo = century_repo(death_ah or 1)
    path = local_path.lstrip("/")
    if path.startswith("data/"):
        rest = path
    else:
        rest = "data/" + path
    return f"https://raw.githubusercontent.com/OpenITI/{repo}/master/{rest}"


class OpenITIConnector(HttpMixin):
    source_code = "openiti"

    def __init__(self) -> None:
        super().__init__()
        self._min_interval = 0.4
        self._by_id: Dict[str, Dict[str, str]] = {}

    def _load_rows(self) -> List[Dict[str, str]]:
        self.throttle()
        resp = self._client.get(METADATA_URL)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text), delimiter="\t")
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
            yield DiscoveredItem(
                external_id=book,
                url=github_raw_url(row.get("local_path") or "", death_year_from_uri(row.get("version_uri") or book) or 1),
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
        url = github_raw_url(row.get("local_path") or "", meta.death_year_ah or 1)
        return [RemoteFile(url=url, fmt="epub", filename=f"{item.external_id}.epub", extra={"source": "openiti-text"})]

    def download(self, remote: RemoteFile, dest: Path) -> Path:
        if not remote.url:
            raise RuntimeError("missing openiti url")
        self.throttle()
        resp = self._client.get(remote.url)
        if resp.status_code == 404:
            # try common extensions
            for ext in (".completed", ".mARkdown", ""):
                trial = remote.url if not ext else remote.url.rstrip("/") + ext
                self.throttle()
                resp = self._client.get(trial)
                if resp.status_code == 200:
                    break
        resp.raise_for_status()
        text = resp.text
        guessed_title, chapters = mARkdown_to_chapters(text)
        title = dest.stem
        build_epub(
            dest,
            title=guessed_title or title,
            author="OpenITI",
            identifier="openiti:" + dest.stem,
            chapters=chapters[:80],
            attribution=(
                "النص من مدونة OpenITI المرخّصة برخصة المشاع الإبداعي "
                "نسب المصنف — غير تجاري — الترخيص بالمثل 4.0."
            ),
        )
        return dest
