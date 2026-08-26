from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple
from urllib.parse import quote, urlencode

from abu_alia.connectors.base import DiscoveredItem, HttpMixin, RemoteFile, SourceMetadata
from abu_alia.ingestion.epub_build import build_epub

API = "https://ar.wikisource.org/w/api.php"
SITE = "https://ar.wikisource.org/wiki/"
LICENSE = "https://creativecommons.org/licenses/by-sa/3.0/"
CATEGORIES = (
    "تصنيف:كتب",
    "تصنيف:دواوين",
    "تصنيف:مؤلفات",
)
MIN_WIKITEXT_BYTES = 4000
SKIP_TITLE = re.compile(r"قائمة|بوابة|مؤلف:|نقاش|ويكي مصدر|^تصنيف:|ملحق")
HEADING_RE = re.compile(r"^={2,4}\s*(.+?)\s*={2,4}\s*$", re.M)
TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}", re.S)
WIKILINK_RE = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]")
FILE_RE = re.compile(r"\[\[(?:ملف|File|Image):[^\]]+\]\]", re.I)
REF_RE = re.compile(r"<ref[^>]*>.*?</ref>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")


def wikitext_to_chapters(text: str) -> List[Tuple[str, str]]:
    raw = (text or "").strip()
    if not raw:
        return []
    if raw.startswith("#تحويل") or raw.lower().startswith("#redirect"):
        return []
    cleaned = raw
    for _ in range(10):
        nxt = TEMPLATE_RE.sub("", cleaned)
        if nxt == cleaned:
            break
        cleaned = nxt
    cleaned = FILE_RE.sub("", cleaned)
    cleaned = REF_RE.sub("", cleaned)
    cleaned = WIKILINK_RE.sub(r"\1", cleaned)
    cleaned = TAG_RE.sub("", cleaned)
    cleaned = html.unescape(cleaned)
    parts = HEADING_RE.split(cleaned)
    chapters: List[Tuple[str, str]] = []
    if parts and parts[0].strip():
        chapters.append(("المتن", parts[0]))
    for i in range(1, len(parts), 2):
        title = parts[i].strip() or "فصل"
        body = parts[i + 1] if i + 1 < len(parts) else ""
        chapters.append((title, body))
    html_chapters: List[Tuple[str, str]] = []
    for title, body in chapters:
        paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        if not paras:
            continue
        html_chapters.append(
            (title[:180], "".join(f"<p>{html.escape(p)}</p>" for p in paras))
        )
    return html_chapters


def extracted_length(chapters: List[Tuple[str, str]]) -> int:
    return sum(len(html.unescape(TAG_RE.sub("", body))) for _, body in chapters)


class WikisourceArConnector(HttpMixin):
    source_code = "wikisource_ar"

    def __init__(self) -> None:
        super().__init__()
        self._min_interval = 1.0

    def _api(self, params: Dict[str, str]) -> dict:
        query = urlencode(params)
        resp = self.http_get(f"{API}?{query}")
        resp.raise_for_status()
        return resp.json()

    def discover(self, cursor: Optional[str] = None) -> Iterator[DiscoveredItem]:
        seen = set()
        for category in CATEGORIES:
            cont: Optional[str] = None
            while True:
                params = {
                    "action": "query",
                    "format": "json",
                    "generator": "categorymembers",
                    "gcmtitle": category,
                    "gcmnamespace": "0",
                    "gcmlimit": "50",
                    "prop": "info",
                }
                if cont:
                    params["gcmcontinue"] = cont
                data = self._api(params)
                pages = (data.get("query") or {}).get("pages") or {}
                for page in pages.values():
                    title = (page.get("title") or "").strip()
                    if not title or title in seen:
                        continue
                    if SKIP_TITLE.search(title):
                        continue
                    if int(page.get("length") or 0) < MIN_WIKITEXT_BYTES:
                        continue
                    seen.add(title)
                    yield DiscoveredItem(
                        external_id=title,
                        url=SITE + quote(title.replace(" ", "_")),
                        title=title,
                        raw={"title": title, "pageid": page.get("pageid"), "length": page.get("length")},
                    )
                cont = (data.get("continue") or {}).get("gcmcontinue")
                if not cont:
                    break

    def fetch_metadata(self, item: DiscoveredItem) -> SourceMetadata:
        title = item.title or item.external_id
        return SourceMetadata(
            title=title,
            authors=["ويكي مصدر"],
            language="ar",
            license_url=LICENSE,
            extra={"pageid": (item.raw or {}).get("pageid")},
        )

    def discover_files(self, item: DiscoveredItem, meta: SourceMetadata) -> List[RemoteFile]:
        title = item.external_id
        params = urlencode(
            {
                "action": "query",
                "format": "json",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "titles": title,
            }
        )
        return [
            RemoteFile(
                url=f"{API}?{params}",
                fmt="epub",
                filename=f"wikisource-{abs(hash(title))}.epub",
                extra={"title": title},
            )
        ]

    def download(self, remote: RemoteFile, dest: Path) -> Path:
        title = remote.extra.get("title") or dest.stem
        data = self._api(
            {
                "action": "query",
                "format": "json",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "titles": title,
            }
        )
        pages = (data.get("query") or {}).get("pages") or {}
        wikitext = ""
        for page in pages.values():
            revisions = page.get("revisions") or []
            if revisions:
                wikitext = ((revisions[0].get("slots") or {}).get("main") or {}).get("*") or ""
        chapters = wikitext_to_chapters(wikitext)
        if extracted_length(chapters) < 2500:
            raise ValueError("wikisource page too short for a complete book")
        build_epub(
            dest,
            title=title,
            author="ويكي مصدر",
            identifier="wikisource-ar:" + title,
            chapters=chapters,
            attribution=(
                "النص من ويكي مصدر العربية، مرخّص برخصة المشاع الإبداعي "
                "نسب المصنف — الترخيص بالمثل 3.0."
            ),
        )
        from abu_alia.storage.validate import validate_book_file

        validate_book_file(dest, expected="epub")
        return dest
