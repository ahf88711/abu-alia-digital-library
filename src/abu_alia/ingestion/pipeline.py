from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from abu_alia.arabic.normalize import normalize_search
from abu_alia.catalog.resolve import find_work_by_title_author, resolve_author, resolve_publisher, unique_slug
from abu_alia.classification.engine import score_categories, select_assignments
from abu_alia.config import get_settings
from abu_alia.connectors.registry import get_connector
from abu_alia.covers.generate import generate_cover
from abu_alia.db.models import (
    Category,
    Cover,
    Edition,
    FileAsset,
    ImportEvent,
    License,
    ReviewItem,
    Source,
    SourceItem,
    Work,
    WorkCategory,
    WorkContributor,
    utcnow,
)
from abu_alia.duplicates.score import score_duplicate
from abu_alia.jobs.queue import enqueue
from abu_alia.rights.eligibility import Eligibility, decide_eligibility
from abu_alia.search.backend import index_work
from abu_alia.net.http import PermanentHTTPError, RetryableHTTPError, is_retryable
from abu_alia.storage.backend import key_for_hash, sha256_file, storage_from_settings
from abu_alia.storage.validate import FileValidationError, validate_book_file


def log_event(session: Session, item: SourceItem, stage: str, status: str, message: str = "", payload=None) -> None:
    session.add(
        ImportEvent(
            source_item_id=item.id,
            stage=stage,
            status=status,
            message=message[:2000] if message else None,
            payload=payload,
        )
    )


def enqueue_discovery(session: Session, source_code: str, limit: Optional[int] = None) -> None:
    settings = get_settings()
    enqueue(
        session,
        "discover_source",
        {"source_code": source_code, "limit": limit or settings.ingestion_batch_limit},
        priority=10,
    )


def run_discovery(session: Session, source_code: str, limit: Optional[int] = None) -> int:
    source = session.execute(select(Source).where(Source.code == source_code)).scalar_one_or_none()
    if source is None or not source.enabled:
        raise RuntimeError(f"source disabled or missing: {source_code}")
    connector = get_connector(source_code)
    created = 0
    try:
        for discovered in connector.discover():
            if limit is not None and created >= limit:
                break
            existing = session.execute(
                select(SourceItem).where(
                    SourceItem.source_id == source.id,
                    SourceItem.external_id == discovered.external_id,
                )
            ).scalar_one_or_none()
            if existing:
                continue
            item = SourceItem(
                source_id=source.id,
                external_id=discovered.external_id,
                url=discovered.url,
                title=discovered.title,
                status="discovered",
                raw_metadata=discovered.raw,
            )
            session.add(item)
            session.flush()
            enqueue(session, "ingest_item", {"source_item_id": item.id}, priority=5)
            created += 1
            item.status = "queued"
        source.last_success_at = utcnow()
        session.flush()
        return created
    except Exception:
        source.last_failure_at = utcnow()
        raise
    finally:
        closer = getattr(connector, "close", None)
        if closer:
            closer()


def run_ingest_item(session: Session, source_item_id: int) -> str:
    item = session.execute(
        select(SourceItem).options(selectinload(SourceItem.source)).where(SourceItem.id == source_item_id)
    ).scalar_one_or_none()
    if item is None:
        raise RuntimeError("source item missing")
    item.status = "processing"
    item.attempts += 1
    log_event(session, item, "processing", "started")
    connector = get_connector(item.source.code)
    settings = get_settings()
    settings.tmp_root.mkdir(parents=True, exist_ok=True)
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    tmp_root = Path(tempfile.mkdtemp(prefix="abu-alia-", dir=str(settings.tmp_root)))
    try:
        from abu_alia.connectors.base import DiscoveredItem

        discovered = DiscoveredItem(
            external_id=item.external_id,
            url=item.url,
            title=item.title,
            raw=item.raw_metadata or {},
        )
        meta = connector.fetch_metadata(discovered)
        log_event(session, item, "metadata", "ok", meta.title)
        decision = decide_eligibility(
            source_code=item.source.code,
            license_url=meta.license_url,
            collections=meta.collections,
            author_death_year_ah=meta.death_year_ah,
            in_library_lending=meta.in_library_lending,
            trusted_ia_collections=settings.trusted_ia_set,
            max_death_ah=settings.openiti_max_death_ah,
            copyright_flag=meta.copyright_flag,
        )
        item.eligibility = decision["eligibility"]
        item.license_evidence = {
            "reason": decision["reason"],
            "evidence": decision.get("evidence"),
            "license_code": getattr(decision.get("license"), "code", None),
        }
        if item.eligibility == Eligibility.PROHIBITED:
            item.status = "rejected"
            log_event(session, item, "eligibility", "rejected", decision["reason"])
            return "rejected"

        files = connector.discover_files(discovered, meta)
        if not files:
            item.status = "failed"
            item.last_error = "no files"
            log_event(session, item, "files", "failed", "no files")
            return "failed"

        storage = storage_from_settings(settings)
        saved = []
        download_errors = []
        for remote in files:
            dest = tmp_root / remote.filename
            try:
                connector.download(remote, dest)
            except Exception as exc:
                log_event(session, item, "download", "failed", str(exc))
                download_errors.append(exc)
                if is_retryable(exc) or isinstance(exc, RetryableHTTPError):
                    item.status = "retrying"
                    item.last_error = str(exc)[:2000]
                    raise
                continue
            try:
                validated = validate_book_file(dest, expected=remote.fmt)
            except FileValidationError as exc:
                log_event(session, item, "validate", "failed", exc.message)
                continue
            digest = sha256_file(dest)
            saved.append((dest, validated, digest, remote))
        if not saved:
            item.status = "failed"
            if download_errors:
                msg = str(download_errors[-1])[:1960]
                if any(isinstance(e, PermanentHTTPError) for e in download_errors) or msg.startswith("permanent:"):
                    msg = "permanent: " + msg if not msg.startswith("permanent:") else msg
                item.last_error = msg
            else:
                item.last_error = "all files failed validation"
            return "failed"

        license_row = _ensure_license(session, decision)
        primary_author = resolve_author(
            session,
            meta.authors[0] if meta.authors else "مؤلف غير معروف",
            death_year_ah=meta.death_year_ah,
        )
        title_norm = normalize_search(meta.title)
        author_norm = primary_author.name_normalized
        existing_file = session.execute(
            select(FileAsset).where(FileAsset.sha256 == saved[0][2])
        ).scalar_one_or_none()
        if existing_file:
            work = existing_file.edition.work
            _attach_missing_formats(session, storage, work, saved, item)
            item.work_id = work.id
            item.status = "duplicate"
            log_event(session, item, "duplicate", "identical_file")
            return "duplicate"

        existing_work = find_work_by_title_author(session, title_norm, author_norm)
        if existing_work:
            other_author = ""
            if existing_work.contributors:
                other_author = existing_work.contributors[0].author.name_normalized
            dup = score_duplicate(
                left_title=title_norm,
                right_title=existing_work.title_normalized,
                left_author=author_norm,
                right_author=other_author,
                left_year=meta.year,
                right_year=existing_work.year,
            )
            if dup["auto_merge"] or dup["score"] >= 0.85:
                _attach_missing_formats(session, storage, existing_work, saved, item)
                item.work_id = existing_work.id
                item.status = "duplicate"
                log_event(session, item, "duplicate", dup["kind"], payload=dup)
                return "duplicate"
            if dup["score"] >= 0.55:
                session.add(
                    ReviewItem(
                        kind="duplicate",
                        reason=dup["kind"],
                        payload=dup,
                        source_item_id=item.id,
                        work_id=existing_work.id,
                    )
                )

        publisher = resolve_publisher(session, meta.publisher)
        work = Work(
            title=meta.title,
            title_normalized=title_norm,
            subtitle=meta.subtitle,
            description=meta.description,
            language=meta.language or "ar",
            slug=unique_slug(session, Work, meta.title),
            publication_status="draft",
            year=meta.year,
            extra={"source": item.source.code, "external_id": item.external_id},
        )
        session.add(work)
        session.flush()
        session.add(
            WorkContributor(work_id=work.id, author_id=primary_author.id, role="author", sort_order=0)
        )
        for extra_author in meta.authors[1:4]:
            a = resolve_author(session, extra_author)
            session.add(WorkContributor(work_id=work.id, author_id=a.id, role="author", sort_order=1))
        edition = Edition(
            work_id=work.id,
            publisher_id=publisher.id if publisher else None,
            license_id=license_row.id if license_row else None,
            year=meta.year,
            isbn13=meta.isbn13,
            isbn10=meta.isbn10,
            page_count=meta.page_count,
            language=meta.language or "ar",
            attribution=_attribution(item.source.code, meta),
        )
        session.add(edition)
        session.flush()
        for dest, validated, digest, remote in saved:
            ext = "pdf" if validated.fmt == "pdf" else "epub"
            key = key_for_hash(digest, ext)
            if not storage.exists(key):
                storage.put(key, dest)
            fa = session.execute(select(FileAsset).where(FileAsset.sha256 == digest)).scalar_one_or_none()
            if fa:
                continue
            session.add(
                FileAsset(
                    edition_id=edition.id,
                    source_item_id=item.id,
                    format=validated.fmt,
                    storage_key=key,
                    sha256=digest,
                    mime=validated.mime,
                    size_bytes=validated.size_bytes,
                    original_filename=remote.filename,
                    validation_status="validated",
                    page_count=validated.page_count,
                )
            )
        session.flush()
        cats = session.execute(select(Category)).scalars().all()
        scored = score_categories(
            categories=cats,
            title=meta.title,
            description=meta.description or "",
            source_genres=meta.genres,
            publisher=meta.publisher or "",
            tags=meta.tags,
        )
        chosen, needs_review = select_assignments(scored)
        for row in chosen:
            session.add(
                WorkCategory(
                    work_id=work.id,
                    category_id=row["category_id"],
                    confidence=row["score"],
                    is_primary=row["is_primary"],
                    evidence={"signals": row["evidence"]},
                )
            )
        if needs_review:
            session.add(
                ReviewItem(
                    kind="classification",
                    reason="low_confidence",
                    payload={"scored": scored[:5]},
                    source_item_id=item.id,
                    work_id=work.id,
                )
            )
        cat_name = chosen[0]["name_ar"] if chosen else ""
        cover_tmp = tmp_root / "cover.jpg"
        font = None
        font_dir = settings.font_dir
        for candidate in ("Amiri-Regular.ttf", "NotoNaskhArabic-Regular.ttf"):
            p = font_dir / candidate
            if p.exists():
                font = p
                break
        generate_cover(
            cover_tmp,
            title=meta.title,
            author=primary_author.canonical_name,
            category=cat_name,
            font_path=font,
            seed=work.id,
        )
        cover_key = key_for_hash(sha256_file(cover_tmp), "jpg")
        storage.put(cover_key, cover_tmp)
        session.add(
            Cover(
                work_id=work.id,
                kind="generated",
                storage_key=cover_key,
                width=480,
                height=720,
                mime="image/jpeg",
            )
        )
        item.work_id = work.id
        auto = item.eligibility in Eligibility.AUTO_PUBLISH
        if auto and not needs_review:
            work.publication_status = "published"
            work.published_at = utcnow()
            item.status = "published"
            session.flush()
            work = session.execute(
                select(Work)
                .options(
                    selectinload(Work.contributors).selectinload(WorkContributor.author),
                    selectinload(Work.editions).selectinload(Edition.publisher),
                    selectinload(Work.editions).selectinload(Edition.files),
                    selectinload(Work.categories).selectinload(WorkCategory.category),
                )
                .where(Work.id == work.id)
            ).scalar_one()
            index_work(session, work)
            log_event(session, item, "publish", "ok")
            return "published"
        if auto and needs_review:
            work.publication_status = "published"
            work.published_at = utcnow()
            item.status = "requires_review"
            session.flush()
            work = session.execute(
                select(Work)
                .options(
                    selectinload(Work.contributors).selectinload(WorkContributor.author),
                    selectinload(Work.editions).selectinload(Edition.publisher),
                    selectinload(Work.editions).selectinload(Edition.files),
                    selectinload(Work.categories).selectinload(WorkCategory.category),
                )
                .where(Work.id == work.id)
            ).scalar_one()
            index_work(session, work)
            log_event(session, item, "publish", "ok_with_review")
            return "requires_review"
        item.status = "quarantined"
        work.publication_status = "draft"
        session.add(
            ReviewItem(
                kind="rights",
                reason=decision["reason"],
                payload=item.license_evidence,
                source_item_id=item.id,
                work_id=work.id,
            )
        )
        log_event(session, item, "quarantine", "pending", decision["reason"])
        return "quarantined"
    except Exception as exc:
        item.status = "failed"
        item.last_error = str(exc)[:2000]
        log_event(session, item, "failed", "error", str(exc))
        raise
    finally:
        closer = getattr(connector, "close", None)
        if closer:
            closer()
        shutil.rmtree(tmp_root, ignore_errors=True)


def _attach_missing_formats(session, storage, work: Work, saved, item: SourceItem) -> None:
    edition = work.editions[0] if work.editions else None
    if edition is None:
        return
    have = {f.format for f in edition.files}
    for dest, validated, digest, remote in saved:
        if validated.fmt in have:
            continue
        existing = session.execute(select(FileAsset).where(FileAsset.sha256 == digest)).scalar_one_or_none()
        if existing:
            continue
        key = key_for_hash(digest, validated.fmt)
        if not storage.exists(key):
            storage.put(key, dest)
        session.add(
            FileAsset(
                edition_id=edition.id,
                source_item_id=item.id,
                format=validated.fmt,
                storage_key=key,
                sha256=digest,
                mime=validated.mime,
                size_bytes=validated.size_bytes,
                original_filename=remote.filename,
                validation_status="validated",
                page_count=validated.page_count,
            )
        )
        have.add(validated.fmt)


def _ensure_license(session: Session, decision) -> Optional[License]:
    match = decision.get("license")
    if not match:
        return None
    row = session.execute(select(License).where(License.code == match.code)).scalar_one_or_none()
    if row:
        return row
    row = License(
        code=match.code,
        name_ar=match.code,
        allows_redistribution=match.allows_redistribution,
        allows_commercial=match.allows_commercial,
        requires_attribution=match.requires_attribution,
        requires_share_alike=match.requires_share_alike,
        non_commercial_only=match.non_commercial_only,
    )
    session.add(row)
    session.flush()
    return row


def _attribution(source_code: str, meta) -> str:
    if source_code == "openiti":
        return (
            "النص من مدونة OpenITI (CC BY-NC-SA 4.0). "
            "يُنسب إلى مبادرة النصوص الإسلامية المفتوحة ومصادرها الأصلية."
        )
    if source_code == "gutenberg":
        return "هذا الكتاب من مشروع غوتنبرغ وهو في الملك العام في الولايات المتحدة."
    if source_code == "internet_archive":
        return "الملف من أرشيف الإنترنت وفق الرخصة المرفقة مع العنصر."
    return ""


def catalog_stats(session: Session) -> dict:
    from sqlalchemy import func

    from abu_alia.db.models import FileAsset, Job

    published = (
        session.execute(select(func.count()).select_from(Work).where(Work.publication_status == "published")).scalar()
        or 0
    )
    pdf = session.execute(select(func.count()).select_from(FileAsset).where(FileAsset.format == "pdf")).scalar() or 0
    epub = session.execute(select(func.count()).select_from(FileAsset).where(FileAsset.format == "epub")).scalar() or 0
    failed = session.execute(select(func.count()).select_from(SourceItem).where(SourceItem.status == "failed")).scalar() or 0
    quarantined = (
        session.execute(select(func.count()).select_from(SourceItem).where(SourceItem.status == "quarantined")).scalar()
        or 0
    )
    queued_jobs = (
        session.execute(select(func.count()).select_from(Job).where(Job.status.in_(("queued", "retrying", "running")))).scalar()
        or 0
    )
    discovered = session.execute(select(func.count()).select_from(SourceItem)).scalar() or 0
    return {
        "published": int(published),
        "pdf": int(pdf),
        "epub": int(epub),
        "failed": int(failed),
        "quarantined": int(quarantined),
        "queued_jobs": int(queued_jobs),
        "discovered": int(discovered),
    }


def requeue_failed(session: Session, *, limit: int = 50, source_code: Optional[str] = None) -> int:
    stmt = select(SourceItem).where(SourceItem.status.in_(("failed", "retrying"))).order_by(SourceItem.id)
    if source_code:
        stmt = stmt.join(Source).where(Source.code == source_code)
    items = session.execute(stmt.limit(limit)).scalars().all()
    n = 0
    for item in items:
        err = (item.last_error or "").lower()
        if err.startswith("permanent:") or "all urls missing" in err:
            continue
        item.status = "queued"
        item.last_error = None
        enqueue(session, "ingest_item", {"source_item_id": item.id}, priority=8)
        n += 1
    return n
