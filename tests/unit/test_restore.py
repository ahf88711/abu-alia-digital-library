from pathlib import Path

from abu_alia.deploy.restore import (
    _db_looks_populated,
    snapshot_is_stale,
    sqlite_file_path,
    write_snapshot_marker,
)


def test_sqlite_path_absolute():
    p = sqlite_file_path("sqlite:////var/data/library.db")
    assert p == Path("/var/data/library.db")


def test_populated_db_threshold(tmp_path):
    tiny = tmp_path / "tiny.db"
    tiny.write_bytes(b"x" * 100)
    assert _db_looks_populated(tiny) is False


def test_snapshot_marker_detects_stale(tmp_path):
    assert snapshot_is_stale(tmp_path, "1.4.0-epub-complete") is True
    write_snapshot_marker(tmp_path, "1.3.0")
    assert snapshot_is_stale(tmp_path, "1.4.0-epub-complete") is True
    write_snapshot_marker(tmp_path, "1.4.0-epub-complete")
    assert snapshot_is_stale(tmp_path, "1.4.0-epub-complete") is False
    assert snapshot_is_stale(tmp_path, "") is False
