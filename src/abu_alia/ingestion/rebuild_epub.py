from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from abu_alia.config import get_settings
from abu_alia.connectors.openiti import OpenITIConnector, candidate_urls, death_year_from_uri
from abu_alia.connectors.base import RemoteFile
from abu_alia.db.models import Edition, FileAsset, SourceItem, Work, WorkContributor
from abu_alia.storage.backend import key_for_hash, sha256_file, storage_from_settings
from abu_alia.storage.validate import validate_book_file

log = logging.getLogger("abu_alia.rebuild_epub")

CHAPTER_CAP = 80
PARA_CAP = 4000


def inspect_epub(path: Path) -> Dict:
    info: Dict = {
        "path": str(path),
        "size": path.stat().st_size if path.is_file() else 0,
        "exists": path.is_file(),
        "zip_ok": False,
        "chapters": 0,
        "max_paragraphs": 0,
        "capped_chapters": False,
        "capped_paragraphs": False,
        "error": None,
    }
    if not path.is_file():
        info["error"] = "missing"
        return info
    try:
        with zipfile.ZipFile(path, "r") as zf:
            broken = zf.testzip()
            if broken is not None:
                info["error"] = f"bad_member:{broken}"
                return info
            info["zip_ok"] = True
            chaps = [n for n in zf.namelist() if "chap_" in n]
            info["chapters"] = len(chaps)
            # The old builder dropped everything after 80 chapters. After the
            # rebuild, exactly 80 chapters can be the genuine source structure.
            info["eighty_chapters"] = len(chaps) == CHAPTER_CAP
            info["capped_chapters"] = False
            max_p = 0
            for name in chaps:
                n = zf.read(name).count(b"<p>")
                if n > max_p:
                    max_p = n
            info["max_paragraphs"] = max_p
            info["capped_paragraphs"] = max_p >= PARA_CAP
    except zipfile.BadZipFile as exc:
        info["error"] = f"bad_zip:{exc}"
    return info


def is_build_capped(info: Dict) -> bool:
    return bool(info.get("capped_chapters") or info.get("capped_paragraphs"))


def audit_epubs(session: Session, storage_root: Path, limit: Optional[int] = None) -> Dict:
    rows = session.execute(
        select(FileAsset, Work)
        .join(Edition, Edition.id == FileAsset.edition_id)
        .join(Work, Work.id == Edition.work_id)
        .where(FileAsset.format == "epub", FileAsset.withdrawn.is_(False), Work.publication_status == "published")
    ).all()
    summary = {
        "checked": 0,
        "healthy": 0,
        "capped_chapters": 0,
        "eighty_chapters": 0,
        "capped_paragraphs": 0,
        "bad_zip": 0,
        "missing": 0,
        "size_mismatch": 0,
        "affected_ids": [],
    }
    for fa, work in rows:
        if limit and summary["checked"] >= limit:
            break
        path = Path(storage_root) / fa.storage_key
        summary["checked"] += 1
        if path.is_file() and path.stat().st_size != fa.size_bytes:
            summary["size_mismatch"] += 1
        info = inspect_epub(path)
        if not info["exists"]:
            summary["missing"] += 1
            summary["affected_ids"].append(work.id)
            continue
        if info["error"]:
            summary["bad_zip"] += 1
            summary["affected_ids"].append(work.id)
            continue
        if info.get("eighty_chapters"):
            summary["eighty_chapters"] += 1
        if info["capped_chapters"]:
            summary["capped_chapters"] += 1
        if info["capped_paragraphs"]:
            summary["capped_paragraphs"] += 1
        if is_build_capped(info):
            summary["affected_ids"].append(work.id)
        else:
            summary["healthy"] += 1
    return summary


def _replace_epub(session: Session, work: Work, fa: FileAsset, new_path: Path) -> str:
    validated = validate_book_file(new_path, expected="epub")
    digest = sha256_file(new_path)
    storage = storage_from_settings()
    key = key_for_hash(digest, "epub")
    if digest != fa.sha256:
        existing = session.execute(select(FileAsset).where(FileAsset.sha256 == digest)).scalar_one_or_none()
        if existing and existing.id != fa.id:
            return "hash_collision"
        storage.put(key, new_path)
        fa.sha256 = digest
        fa.storage_key = key
        fa.size_bytes = validated.size_bytes
        fa.mime = validated.mime
        fa.validation_status = "validated"
        session.flush()
        return "replaced"
    return "unchanged"


def rebuild_openiti_epub(
    session: Session, work: Work, dest: Path, conn: Optional[OpenITIConnector] = None
) -> str:
    item = session.execute(select(SourceItem).where(SourceItem.work_id == work.id)).scalar_one_or_none()
    extra = work.extra or {}
    if extra.get("source") not in (None, "openiti"):
        return "skip_not_openiti"
    raw = item.raw_metadata if item and isinstance(item.raw_metadata, dict) else {}
    if not raw.get("local_path"):
        return "skip_no_path"
    death = death_year_from_uri(raw.get("version_uri") or extra.get("external_id") or "") or 1
    urls = candidate_urls(raw.get("local_path") or "", death)
    author = "OpenITI"
    if work.contributors and work.contributors[0].author:
        author = work.contributors[0].author.canonical_name
    remote = RemoteFile(
        url=urls[0],
        fmt="epub",
        filename=f"{extra.get('external_id') or work.slug}.epub",
        extra={"urls": urls, "source": "openiti-text", "author": author, "title": work.title},
    )
    conn = conn or OpenITIConnector()
    conn.throttle()
    conn.download(remote, dest)
    fa = None
    for ed in work.editions:
        for f in ed.files:
            if f.format == "epub" and not f.withdrawn:
                fa = f
                break
    if fa is None:
        return "skip_no_file"
    return _replace_epub(session, work, fa, dest)


def rebuild_capped_epubs(session: Session, *, limit: Optional[int] = None, force_ids: Optional[List[int]] = None) -> Dict[str, int]:
    settings = get_settings()
    storage_root = Path(settings.storage_root)
    tmp = Path(settings.tmp_root) / "rebuild-epub"
    tmp.mkdir(parents=True, exist_ok=True)
    stats = {"seen": 0, "rebuilt": 0, "unchanged": 0, "failed": 0, "skipped": 0}
    conn = OpenITIConnector()
    conn._attempts = 3
    conn._client.timeout = __import__("httpx").Timeout(connect=15.0, read=45.0, write=30.0, pool=20.0)

    q = (
        select(Work)
        .where(Work.publication_status == "published")
        .options(
            selectinload(Work.editions).selectinload(Edition.files),
            selectinload(Work.contributors).selectinload(WorkContributor.author),
        )
    )
    if force_ids:
        q = q.where(Work.id.in_(force_ids))
    works = session.execute(q).scalars().unique().all()

    for work in works:
        extra = work.extra or {}
        if extra.get("source") and extra.get("source") != "openiti":
            continue
        fa = None
        for ed in work.editions:
            for f in ed.files:
                if f.format == "epub" and not f.withdrawn:
                    fa = f
                    break
        if fa is None:
            continue
        info = inspect_epub(storage_root / fa.storage_key)
        if not force_ids and not is_build_capped(info) and not info.get("error"):
            continue
        stats["seen"] += 1
        if limit and stats["seen"] > limit:
            break
        dest = tmp / f"{work.id}.epub"
        try:
            result = rebuild_openiti_epub(session, work, dest, conn=conn)
            if result == "replaced":
                stats["rebuilt"] += 1
                log.info("rebuilt work_id=%s slug=%s", work.id, work.slug)
            elif result == "unchanged":
                stats["unchanged"] += 1
            else:
                stats["skipped"] += 1
                log.warning("skip work_id=%s result=%s", work.id, result)
        except Exception:
            stats["failed"] += 1
            log.exception("rebuild failed work_id=%s slug=%s", work.id, work.slug)
        finally:
            if dest.exists():
                dest.unlink(missing_ok=True)
        if stats["seen"] % 10 == 0:
            session.commit()
            log.info("progress %s", stats)
    session.commit()
    return stats
