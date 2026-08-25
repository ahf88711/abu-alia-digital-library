from __future__ import annotations

from typing import Dict, Type

from abu_alia.connectors.base import SourceConnector
from abu_alia.connectors.fixture import FixtureConnector
from abu_alia.connectors.gutenberg import GutenbergConnector
from abu_alia.connectors.internet_archive import InternetArchiveConnector
from abu_alia.connectors.oapen import OapenConnector
from abu_alia.connectors.openiti import OpenITIConnector
from abu_alia.connectors.wikisource import WikisourceArConnector

CONNECTORS: Dict[str, Type] = {
    "fixture": FixtureConnector,
    "openiti": OpenITIConnector,
    "gutenberg": GutenbergConnector,
    "internet_archive": InternetArchiveConnector,
    "wikisource_ar": WikisourceArConnector,
    "oapen": OapenConnector,
}


def get_connector(code: str) -> SourceConnector:
    try:
        cls = CONNECTORS[code]
    except KeyError as exc:
        raise KeyError(f"unknown connector: {code}") from exc
    return cls()
