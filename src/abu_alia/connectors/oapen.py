from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterator, List, Optional
from urllib.parse import urlencode

from abu_alia.connectors.base import DiscoveredItem, HttpMixin, RemoteFile, SourceMetadata
from abu_alia.rights.eligibility import classify_license

API = "https://library.oapen.org/rest"
SEARCH = API + "/search"


def _meta_map(item: dict) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for row in item.get("metadata") or []:
        key = row.get("key")
        val = row.get("value")
        if key and val:
            out.setdefault(key, []).append(str(val))
    return out


def _first(meta: Dict[str, List[str]], *keys: str) -> Optional[str]:
    for key in keys:
        vals = meta.get(key) or []
        if vals:
            return vals[0]
    return None


def is_arabic(meta: Dict[str, List[str]]) -> bool:
    langs = " ".join((meta.get("dc.language") or []) + (meta.get("dc.language.iso") or [])).lower()
    return any(tok in langs for tok in ("arabic", "ara", "ar"))


def license_url_of(meta: Dict[str, List[str]]) -> Optional[str]:
    for key in ("dc.rights.uri", "oapen.licence.identifier", "dc.rights"):
        for val in meta.get(key) or []:
            if "creativecommons.org" in val.lower() or "publicdomain" in val.lower():
                return val
    return None


class OapenConnector(HttpMixin):
    source_code = "oapen"

    def __init__(self) -> None:
        super().__init__()
        self._min_interval = 1.0

    def discover(self, cursor: Optional[str] = None) -> Iterator[DiscoveredItem]:
        offset = int(cursor or 0)
        while True:
            params = urlencode(
                {
                    "query": "dc.language:Arabic",
                    "expand": "metadata",
                    "limit": "50",
                    "offset": str(offset),
                }
            )
            resp = self.http_get(f"{SEARCH}?{params}")
            resp.raise_for_status()
            rows = resp.json()
            if not rows:
                break
            yielded = 0
            for item in rows:
                meta = _meta_map(item)
                if not is_arabic(meta):
                    continue
                license_url = license_url_of(meta)
                match = classify_license(license_url)
                if not match or not match.allows_redistribution:
                    continue
                uuid = item.get("uuid")
                if not uuid:
                    continue
                title = _first(meta, "dc.title") or item.get("name") or uuid
                yield DiscoveredItem(
                    external_id=str(uuid),
                    url=_first(meta, "dc.identifier.uri") or f"https://library.oapen.org/handle/{item.get('handle')}",
                    title=title,
                    raw={"uuid": uuid, "handle": item.get("handle"), "metadata": meta, "license_url": license_url},
                )
                yielded += 1
            if len(rows) < 50:
                break
            offset += len(rows)

    def fetch_metadata(self, item: DiscoveredItem) -> SourceMetadata:
        meta = (item.raw or {}).get("metadata") or {}
        authors = meta.get("dc.contributor.author") or meta.get("dc.creator") or ["OAPEN"]
        return SourceMetadata(
            title=item.title or _first(meta, "dc.title") or item.external_id,
            authors=list(authors),
            description=_first(meta, "dc.description.abstract", "oapen.abstract.otherlanguage"),
            language="ar",
            publisher=_first(meta, "publisher.name", "dc.publisher"),
            license_url=(item.raw or {}).get("license_url") or license_url_of(meta),
        )

    def discover_files(self, item: DiscoveredItem, meta: SourceMetadata) -> List[RemoteFile]:
        uuid = item.external_id
        resp = self.http_get(f"{API}/items/{uuid}?expand=bitstreams")
        resp.raise_for_status()
        payload = resp.json()
        files: List[RemoteFile] = []
        for bit in payload.get("bitstreams") or []:
            mime = (bit.get("mimeType") or "").lower()
            name = bit.get("name") or ""
            link = bit.get("retrieveLink")
            if not link:
                continue
            url = "https://library.oapen.org" + link
            if mime == "application/pdf" or name.lower().endswith(".pdf"):
                files.append(RemoteFile(url=url, fmt="pdf", filename=name or f"{uuid}.pdf"))
            elif mime in ("application/epub+zip", "application/epub") or name.lower().endswith(".epub"):
                files.append(RemoteFile(url=url, fmt="epub", filename=name or f"{uuid}.epub"))
        return files

    def download(self, remote: RemoteFile, dest: Path) -> Path:
        resp = self.http_get(remote.url)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        return dest
