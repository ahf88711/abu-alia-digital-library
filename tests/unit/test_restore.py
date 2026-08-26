from pathlib import Path

from abu_alia.deploy.restore import _db_looks_populated, sqlite_file_path


def test_sqlite_path_absolute():
    p = sqlite_file_path("sqlite:////var/data/library.db")
    assert p == Path("/var/data/library.db")


def test_populated_db_threshold(tmp_path):
    tiny = tmp_path / "tiny.db"
    tiny.write_bytes(b"x" * 100)
    assert _db_looks_populated(tiny) is False
