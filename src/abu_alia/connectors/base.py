from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Protocol
import time

import httpx

from abu_alia.config import get_settings


@dataclass
class DiscoveredItem:
    external_id: str
    url: Optional[str] = None
    title: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RemoteFile:
    url: Optional[str]
    fmt: str
    filename: str
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceMetadata:
    title: str
    subtitle: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    description: Optional[str] = None
    year: Optional[int] = None
    publisher: Optional[str] = None
    language: str = "ar"
    isbn13: Optional[str] = None
    isbn10: Optional[str] = None
    page_count: Optional[int] = None
    license_url: Optional[str] = None
    cover_url: Optional[str] = None
    genres: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    death_year_ah: Optional[int] = None
    collections: List[str] = field(default_factory=list)
    in_library_lending: bool = False
    copyright_flag: Optional[bool] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class SourceConnector(Protocol):
    source_code: str

    def discover(self, cursor: Optional[str] = None) -> Iterator[DiscoveredItem]: ...
    def fetch_metadata(self, item: DiscoveredItem) -> SourceMetadata: ...
    def discover_files(self, item: DiscoveredItem, meta: SourceMetadata) -> List[RemoteFile]: ...
    def download(self, remote: RemoteFile, dest: Path) -> Path: ...
    def throttle(self) -> None: ...


class HttpMixin:
    source_code = "base"

    def __init__(self) -> None:
        settings = get_settings()
        self._client = httpx.Client(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        )
        self._min_interval = 1.0
        self._last = 0.0

    def throttle(self) -> None:
        now = time.monotonic()
        wait = self._min_interval - (now - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def close(self) -> None:
        self._client.close()
