from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import quote

from abu_alia.config import get_settings
from abu_alia.connectors.base import DiscoveredItem, HttpMixin, RemoteFile, SourceMetadata

SEARCH = "https://archive.org/advancedsearch.php"
META = "https://archive.org/metadata/{ident}"
DOWNLOAD = "https://archive.org/download/{ident}/{name}"


class InternetArchiveConnector(HttpMixin):
    source_code = "internet_archive"

    def __init__(self) -> None:
        super().__init__()
        self._min_interval = 1.2

    def discover(self, cursor: Optional[str] = None) -> Iterator[DiscoveredItem]:
        settings = get_settings()
        trusted = " OR ".join(f"collection:{c}" for c in sorted(settings.trusted_ia_set))
        query = (
            "mediatype:texts AND (language:ara OR language:Arabic) "
            "AND (licenseurl:*publicdomain* OR licenseurl:*creativecommons*) "
            f"AND ({trusted}) AND (format:PDF OR format:EPUB) AND NOT collection:inlibrary"
        )
        page = int(cursor or 1)
        rows = 50
        while True:
            self.throttle()
            resp = self._client.get(
                SEARCH,
                params={
                    "q": query,
                    "fl[]": ["identifier", "title", "creator", "licenseurl", "collection"],
                    "rows": rows,
                    "page": page,
                    "output": "json",
                    "sort[]": "downloads desc",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            docs = data.get("response", {}).get("docs") or []
            if not docs:
                break
            for doc in docs:
                ident = doc.get("identifier")
                if not ident:
                    continue
                yield DiscoveredItem(
                    external_id=ident,
                    url=f"https://archive.org/details/{ident}",
                    title=doc.get("title"),
                    raw=doc,
                )
            if len(docs) < rows:
                break
            page += 1
            if page > 40:
                break

    def fetch_metadata(self, item: DiscoveredItem) -> SourceMetadata:
        self.throttle()
        resp = self._client.get(META.format(ident=item.external_id))
        resp.raise_for_status()
        payload = resp.json()
        md = payload.get("metadata") or {}
        collections = md.get("collection") or []
        if isinstance(collections, str):
            collections = [collections]
        creators = md.get("creator") or []
        if isinstance(creators, str):
            creators = [creators]
        licenseurl = md.get("licenseurl") or md.get("license")
        inlibrary = "inlibrary" in [str(c).lower() for c in collections]
        return SourceMetadata(
            title=md.get("title") or item.title or item.external_id,
            authors=[c for c in creators if c] or ["مؤلف غير معروف"],
            description=md.get("description") if isinstance(md.get("description"), str) else None,
            year=_year(md.get("year") or md.get("date")),
            language="ar",
            license_url=licenseurl,
            collections=list(collections),
            in_library_lending=inlibrary,
            extra={"ia": md, "files": payload.get("files")},
        )

    def discover_files(self, item: DiscoveredItem, meta: SourceMetadata) -> List[RemoteFile]:
        files = (meta.extra or {}).get("files") or []
        out: List[RemoteFile] = []
        settings = get_settings()
        for f in files:
            name = f.get("name") or ""
            fmt = (f.get("format") or "").lower()
            size = int(f.get("size") or 0)
            if size and size > settings.max_file_bytes:
                continue
            url = DOWNLOAD.format(ident=item.external_id, name=quote(name))
            if "epub" in fmt or name.lower().endswith(".epub"):
                out.append(RemoteFile(url=url, fmt="epub", filename=name, extra=f))
            elif fmt in ("text pdf", "pdf", "additional text pdf") or name.lower().endswith(".pdf"):
                if "abbyy" in name.lower() or name.lower().endswith("_text.pdf"):
                    continue
                out.append(RemoteFile(url=url, fmt="pdf", filename=name, extra=f))
        # prefer one epub and one reasonably sized pdf
        epubs = [x for x in out if x.fmt == "epub"]
        pdfs = sorted([x for x in out if x.fmt == "pdf"], key=lambda r: int(r.extra.get("size") or 0))
        chosen: List[RemoteFile] = []
        if epubs:
            chosen.append(epubs[0])
        if pdfs:
            chosen.append(pdfs[0])
        return chosen

    def download(self, remote: RemoteFile, dest: Path) -> Path:
        if not remote.url:
            raise RuntimeError("missing ia url")
        self.throttle()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._client.stream("GET", remote.url) as resp:
            resp.raise_for_status()
            with dest.open("wb") as fh:
                for chunk in resp.iter_bytes(1024 * 64):
                    fh.write(chunk)
        return dest


def _year(value: Any) -> Optional[int]:
    if value is None:
        return None
    s = str(value)
    for i, ch in enumerate(s):
        if ch.isdigit():
            chunk = s[i : i + 4]
            if chunk.isdigit():
                y = int(chunk)
                if 200 < y < 2100:
                    return y
            break
    return None
