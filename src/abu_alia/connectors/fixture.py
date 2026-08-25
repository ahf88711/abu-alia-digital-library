from __future__ import annotations

from pathlib import Path
from typing import Iterator, List, Optional

from abu_alia.connectors.base import DiscoveredItem, RemoteFile, SourceConnector, SourceMetadata
from abu_alia.ingestion.epub_build import build_epub
from abu_alia.ingestion.pdf_build import build_minimal_pdf


class FixtureConnector:
    source_code = "fixture"

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root

    def discover(self, cursor: Optional[str] = None) -> Iterator[DiscoveredItem]:
        yield DiscoveredItem(
            external_id="fixture-kalila",
            url="fixture://kalila",
            title="كليلة ودمنة",
            raw={"author": "ابن المقفع", "year": 750},
        )
        yield DiscoveredItem(
            external_id="fixture-bukhala",
            url="fixture://bukhala",
            title="البخلاء",
            raw={"author": "الجاحظ", "year": 868},
        )

    def fetch_metadata(self, item: DiscoveredItem) -> SourceMetadata:
        author = item.raw.get("author") or "مؤلف مجهول"
        return SourceMetadata(
            title=item.title or "كتاب تجريبي",
            authors=[author],
            description="نص تجريبي مرخّص للاختبار داخل مكتبة أبو علياء الرقمية.",
            year=item.raw.get("year"),
            language="ar",
            license_url="https://creativecommons.org/publicdomain/zero/1.0/",
            genres=["أدب"],
            extra={"fixture": True},
        )

    def discover_files(self, item: DiscoveredItem, meta: SourceMetadata) -> List[RemoteFile]:
        return [
            RemoteFile(url=None, fmt="epub", filename=f"{item.external_id}.epub", extra={"kind": "epub"}),
            RemoteFile(url=None, fmt="pdf", filename=f"{item.external_id}.pdf", extra={"kind": "pdf"}),
        ]

    def download(self, remote: RemoteFile, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        title = dest.stem
        if remote.fmt == "epub":
            build_epub(
                dest,
                title=title,
                author="مؤلف تجريبي",
                identifier=dest.stem,
                chapters=[("الفصل الأول", "<p>هذا نص عربي تجريبي للقراءة داخل المكتبة.</p><p>يُستخدم للتحقق من مسار EPUB.</p>")],
                attribution="مادة تجريبية داخلية.",
            )
        else:
            build_minimal_pdf(dest, title=title, body="هذا نص عربي تجريبي في ملف PDF للتحقق من القارئ.")
        return dest

    def throttle(self) -> None:
        return
