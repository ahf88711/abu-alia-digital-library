from __future__ import annotations

from typing import Dict, Type

from abu_alia.connectors.base import SourceConnector
from abu_alia.connectors.fixture import FixtureConnector
from abu_alia.connectors.gutenberg import GutenbergConnector
from abu_alia.connectors.internet_archive import InternetArchiveConnector
from abu_alia.connectors.openiti import OpenITIConnector

CONNECTORS: Dict[str, Type] = {
    "fixture": FixtureConnector,
    "openiti": OpenITIConnector,
    "gutenberg": GutenbergConnector,
    "internet_archive": InternetArchiveConnector,
}


def get_connector(code: str) -> SourceConnector:
    try:
        cls = CONNECTORS[code]
    except KeyError as exc:
        raise KeyError(f"unknown connector: {code}") from exc
    return cls()
