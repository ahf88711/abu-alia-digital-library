from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterator, List, Optional

from abu_alia.connectors.base import DiscoveredItem, HttpMixin, RemoteFile, SourceMetadata

CATALOG = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv"


class GutenbergConnector(HttpMixin):
    source_code = "gutenberg"

    def __init__(self) -> None:
        super().__init__()
        self._min_interval = 2.0

    def discover(self, cursor: Optional[str] = None) -> Iterator[DiscoveredItem]:
        resp = self.http_get(CATALOG)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        for row in reader:
            langs = [p.strip() for p in (row.get("Language") or "").split(";")]
            if "ar" not in langs and "ara" not in langs:
                continue
            gid = row.get("Text#") or row.get("Text")
            if not gid:
                continue
            yield DiscoveredItem(
                external_id=str(gid),
                url=f"https://www.gutenberg.org/ebooks/{gid}",
                title=row.get("Title"),
                raw=row,
            )

    def fetch_metadata(self, item: DiscoveredItem) -> SourceMetadata:
        row = item.raw or {}
        authors = [a.strip() for a in (row.get("Authors") or "").split(";") if a.strip()]
        copyrighted = None
        return SourceMetadata(
            title=row.get("Title") or f"Gutenberg {item.external_id}",
            authors=authors or ["Unknown"],
            language="ar",
            license_url="https://creativecommons.org/publicdomain/mark/1.0/",
            copyright_flag=False,
            extra={"subjects": row.get("Subjects"), "locc": row.get("LoCC")},
        )

    def discover_files(self, item: DiscoveredItem, meta: SourceMetadata) -> List[RemoteFile]:
        gid = item.external_id
        return [
            RemoteFile(
                url=f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}-images-3.epub",
                fmt="epub",
                filename=f"pg{gid}.epub",
            ),
            RemoteFile(
                url=f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}-images.epub",
                fmt="epub",
                filename=f"pg{gid}.epub",
            ),
            RemoteFile(
                url=f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.epub",
                fmt="epub",
                filename=f"pg{gid}.epub",
            ),
        ]

    def download(self, remote: RemoteFile, dest: Path) -> Path:
        last_exc = None
        # GutenbergConnector.discover_files returns fallbacks; download tries one URL.
        try:
            resp = self.http_get(remote.url)
            if resp.status_code == 404:
                raise FileNotFoundError(remote.url)
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            return dest
        except Exception as exc:
            last_exc = exc
            raise last_exc
