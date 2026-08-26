from __future__ import annotations

import gzip
import logging
import os
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Optional

import httpx
from sqlalchemy.engine import make_url

from abu_alia.config import get_settings

log = logging.getLogger("abu_alia.restore")

DEFAULT_DB_SNAPSHOT = (
    "https://github.com/ahf88711/abu-alia-digital-library/releases/download/"
    "catalog-4024/library.db.gz"
)
DEFAULT_STORAGE_SNAPSHOT = (
    "https://github.com/ahf88711/abu-alia-digital-library/releases/download/"
    "catalog-4024/storage.tar"
)


def sqlite_file_path(database_url: str) -> Optional[Path]:
    url = make_url(database_url)
    if not str(url.drivername).startswith("sqlite"):
        return None
    if not url.database:
        return None
    return Path(url.database)


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    log.info("downloading catalog snapshot %s -> %s", url, dest)
    timeout = httpx.Timeout(connect=30.0, read=600.0, write=60.0, pool=30.0)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with tmp.open("wb") as fh:
                for chunk in resp.iter_bytes(1024 * 1024):
                    fh.write(chunk)
    tmp.replace(dest)
    return dest


def _db_looks_populated(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 1_000_000:
        return False
    try:
        import sqlite3

        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT COUNT(*) FROM works WHERE publication_status='published'"
            ).fetchone()
            return bool(row and int(row[0]) > 0)
        finally:
            con.close()
    except Exception:
        return path.stat().st_size > 5_000_000


def _storage_looks_populated(root: Path) -> bool:
    if not root.is_dir():
        return False
    n = 0
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".epub", ".pdf"}:
            n += 1
            if n >= 50:
                return True
    return False


def snapshot_marker_path(data_root: Path) -> Path:
    return Path(data_root) / ".catalog_snapshot_id"


def snapshot_is_stale(data_root: Path, expected: str) -> bool:
    if not expected:
        return False
    marker = snapshot_marker_path(data_root)
    current = marker.read_text(encoding="utf-8").strip() if marker.is_file() else ""
    return current != expected


def write_snapshot_marker(data_root: Path, snapshot_id: str) -> None:
    if not snapshot_id:
        return
    path = snapshot_marker_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snapshot_id, encoding="utf-8")


def restore_catalog(*, force: bool = False) -> dict:
    """Copy the existing harvested catalog into an empty production data dir.

    Never re-downloads books from OpenITI. Skips when a populated catalog
    is already present so existing works are not duplicated or replaced.
    """
    settings = get_settings()
    db_url = settings.database_url
    db_path = sqlite_file_path(db_url)
    storage_root = Path(settings.storage_root)
    db_url_snapshot = settings.catalog_snapshot_db or DEFAULT_DB_SNAPSHOT
    storage_snapshot = settings.catalog_snapshot_storage or DEFAULT_STORAGE_SNAPSHOT
    snapshot_id = (settings.catalog_snapshot_id or "").strip()
    result = {
        "db": "skipped",
        "storage": "skipped",
        "db_path": str(db_path),
        "storage_root": str(storage_root),
        "snapshot_id": snapshot_id,
    }

    if db_path is None:
        log.info("non-sqlite database; snapshot restore skipped")
        return result

    db_path.parent.mkdir(parents=True, exist_ok=True)
    storage_root.mkdir(parents=True, exist_ok=True)

    stale = snapshot_is_stale(settings.data_root, snapshot_id)
    if stale and (force or settings.restore_on_boot or settings.is_production):
        log.info("catalog snapshot id changed (%s); replacing populated catalog", snapshot_id)
        force = True
    result["stale"] = stale

    if not force and _db_looks_populated(db_path):
        log.info("catalog already populated at %s; not replacing", db_path)
        result["db"] = "present"
    elif db_url_snapshot:
        tmpdir = Path(tempfile.mkdtemp(prefix="abu-alia-restore-"))
        try:
            gz = tmpdir / "library.db.gz"
            _download(db_url_snapshot, gz)
            with gzip.open(gz, "rb") as src, db_path.open("wb") as dest:
                shutil.copyfileobj(src, dest)
            result["db"] = "restored"
            log.info("restored sqlite catalog to %s (%s bytes)", db_path, db_path.stat().st_size)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    if not settings.restore_storage:
        result["storage"] = "disabled"
    elif not force and _storage_looks_populated(storage_root):
        log.info("object storage already populated at %s; not replacing", storage_root)
        result["storage"] = "present"
    elif storage_snapshot:
        tmpdir = Path(tempfile.mkdtemp(prefix="abu-alia-storage-"))
        try:
            tar_path = tmpdir / "storage.tar"
            _download(storage_snapshot, tar_path)
            with tarfile.open(tar_path, "r") as tf:
                tf.extractall(path=storage_root.parent)
            result["storage"] = "restored"
            log.info("restored object storage under %s", storage_root)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    replaced = result["db"] == "restored" or result["storage"] == "restored"
    if snapshot_id and (replaced or not stale):
        write_snapshot_marker(settings.data_root, snapshot_id)
        result["marker"] = snapshot_id

    os.environ.setdefault("ABU_ALIA_RESTORED", "1")
    return result
