from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from abu_alia.arabic.normalize import normalize_search, slugify_ar
from abu_alia.auth.passwords import hash_password
from abu_alia.config import get_settings
from abu_alia.db.models import Category, License, Source, User
from abu_alia.taxonomy.data import TAXONOMY


LICENSES = [
    ("public-domain", "ملك عام", None, True, True, False, False, False),
    ("cc0-1.0", "CC0", "https://creativecommons.org/publicdomain/zero/1.0/", True, True, False, False, False),
    ("cc-by-4.0", "CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/", True, True, True, False, False),
    ("cc-by-sa-4.0", "CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/", True, True, True, True, False),
    ("cc-by-sa-3.0", "CC BY-SA 3.0", "https://creativecommons.org/licenses/by-sa/3.0/", True, True, True, True, False),
    ("cc-by-nc-4.0", "CC BY-NC 4.0", "https://creativecommons.org/licenses/by-nc/4.0/", True, False, True, False, True),
    ("cc-by-nc-sa-4.0", "CC BY-NC-SA 4.0", "https://creativecommons.org/licenses/by-nc-sa/4.0/", True, False, True, True, True),
]


SOURCES = [
    dict(
        code="openiti",
        name="OpenITI",
        homepage="https://openiti.org/",
        source_type="scholarly_corpus",
        language="ar",
        useful_size="أكثر من 6 آلاف عمل عربي تراثي",
        formats="text→EPUB",
        has_pdf=False,
        has_epub=True,
        has_api=True,
        has_direct_download=True,
        crawling_method="metadata TSV + GitHub raw",
        pagination_method="ملف واحد",
        rate_limits="مهذب تجاه GitHub",
        robots_notes="مستودع GitHub عام",
        license_information="CC BY-NC-SA 4.0 — يُحذف الجهاز التحريري الحديث",
        redistribution_status="verified_open_license",
        connector_status="active",
        enabled=True,
        reliability="high",
        notes="المصدر الأساسي للكتب التراثية العربية المشروعة.",
    ),
    dict(
        code="gutenberg",
        name="Project Gutenberg",
        homepage="https://www.gutenberg.org/",
        source_type="public_domain_repository",
        language="multi",
        useful_size="كتاب عربي واحد في الفهرس الرسمي (2026)",
        formats="EPUB,PDF",
        has_pdf=True,
        has_epub=True,
        has_api=True,
        has_direct_download=True,
        crawling_method="pg_catalog.csv — ممنوع كشط HTML",
        pagination_method="فهرس كامل",
        rate_limits="ثانيتان بين الطلبات",
        robots_notes="استخدم الفهرس الرسمي لا الصفحات",
        license_information="ملك عام أمريكي؛ إعادة التوزيع مسموحة",
        redistribution_status="verified_public_domain",
        connector_status="active",
        enabled=True,
        reliability="high",
        notes="مجموعة عربية ضئيلة جداً.",
    ),
    dict(
        code="internet_archive",
        name="Internet Archive",
        homepage="https://archive.org/",
        source_type="digital_library",
        language="ar",
        useful_size="آلاف الملفات بعلامات PD/CC مع ضوضاء عالية",
        formats="PDF,EPUB",
        has_pdf=True,
        has_epub=True,
        has_api=True,
        has_direct_download=True,
        crawling_method="advancedsearch + metadata API",
        pagination_method="صفحات JSON / scrape API",
        rate_limits="حوالي طلب/ثانية",
        robots_notes="API عامة؛ تجنّب inlibrary",
        license_information="علامات المستخدم غير موثوقة — مجموعات موثوقة فقط للنشر التلقائي",
        redistribution_status="uncertain",
        connector_status="active",
        enabled=True,
        reliability="medium",
        notes="الحجر الصحي افتراضي خارج المجموعات الموثوقة.",
    ),
    dict(
        code="oapen",
        name="OAPEN Library",
        homepage="https://www.oapen.org/",
        source_type="open_access_books",
        language="multi",
        useful_size="كتب أكاديمية مفتوحة",
        formats="PDF",
        has_pdf=True,
        has_epub=False,
        has_api=True,
        has_direct_download=True,
        crawling_method="REST search + bitstreams",
        pagination_method="offset/limit",
        rate_limits="طلب واحد في الثانية",
        robots_notes="REST عامة؛ يُستورد فقط ما له URI رخصة واضحة",
        license_information="رخص ناشرين مفتوحة (CC) عند وجود URI",
        redistribution_status="verified_open_license",
        connector_status="active",
        enabled=False,
        reliability="medium",
        notes="موصل جاهز ومتوقف أثناء حصاد OpenITI. لا يُنشر إلا بترخيص CC/PD صريح.",
    ),
    dict(
        code="safahat",
        name="صفحات / مؤسسة هنداوي",
        homepage="https://www.safahat.org/",
        source_type="publisher_free",
        language="ar",
        useful_size="آلاف العناوين العربية",
        formats="PDF,EPUB",
        has_pdf=True,
        has_epub=True,
        has_api=False,
        has_direct_download=True,
        crawling_method="غير مفعّل",
        pagination_method="موقع",
        rate_limits="غير معروف",
        robots_notes="الوصول المجاني ≠ إعادة الاستضافة",
        license_information="غير مؤكد لإعادة الاستضافة",
        redistribution_status="uncertain",
        connector_status="registered",
        enabled=False,
        reliability="unknown",
        notes="لا يُستورد تلقائياً حتى تتضح الرخصة.",
    ),
    dict(
        code="wikisource_ar",
        name="ويكي مصدر العربية",
        homepage="https://ar.wikisource.org/",
        source_type="wiki",
        language="ar",
        useful_size="صفحات مكتملة فقط (لا فهارس أو قوائم)",
        formats="text→EPUB",
        has_pdf=False,
        has_epub=True,
        has_api=True,
        has_direct_download=True,
        crawling_method="MediaWiki API",
        pagination_method="gcmcontinue",
        rate_limits="طلب واحد في الثانية",
        robots_notes="CC BY-SA 3.0 — استخدم API لا الكشط",
        license_information="CC BY-SA 3.0",
        redistribution_status="verified_open_license",
        connector_status="active",
        enabled=False,
        reliability="medium",
        notes="موصل جاهز؛ يبقى متوقفاً أثناء حصاد OpenITI لتفادي قفل SQLite. لا يُستورد إلا الصفحات الطويلة المكتملة.",
    ),
    dict(
        code="fixture",
        name="مواد اختبار داخلية",
        homepage=None,
        source_type="fixture",
        language="ar",
        useful_size="2",
        formats="PDF,EPUB",
        has_pdf=True,
        has_epub=True,
        has_api=False,
        has_direct_download=True,
        crawling_method="محلي",
        pagination_method="ثابت",
        rate_limits="لا",
        robots_notes="داخلي",
        license_information="CC0 للاختبار",
        redistribution_status="explicitly_authorized",
        connector_status="active",
        enabled=True,
        reliability="high",
        notes="لا يُستخدم في الإنتاج.",
    ),
]


def seed_all(session: Session) -> None:
    _seed_licenses(session)
    _seed_sources(session)
    _seed_taxonomy(session)
    _seed_admin(session)


def _seed_licenses(session: Session) -> None:
    for code, name, url, redist, comm, attr, sa, nc in LICENSES:
        row = session.execute(select(License).where(License.code == code)).scalar_one_or_none()
        if row:
            continue
        session.add(
            License(
                code=code,
                name_ar=name,
                url=url,
                allows_redistribution=redist,
                allows_commercial=comm,
                requires_attribution=attr,
                requires_share_alike=sa,
                non_commercial_only=nc,
            )
        )


def _seed_sources(session: Session) -> None:
    settings = get_settings()
    for data in SOURCES:
        row = session.execute(select(Source).where(Source.code == data["code"])).scalar_one_or_none()
        if row:
            if data["code"] in ("wikisource_ar", "oapen") and row.connector_status == "planned":
                row.connector_status = data["connector_status"]
                row.has_epub = data["has_epub"]
                row.formats = data["formats"]
                row.notes = data["notes"]
                row.enabled = False
            continue
        if data["code"] == "fixture" and settings.is_production:
            data = dict(data)
            data["enabled"] = False
        session.add(Source(**data))


def _seed_taxonomy(session: Session) -> None:
    def walk(nodes: List[Dict[str, Any]], parent: Optional[Category], prefix: str) -> None:
        for i, node in enumerate(nodes):
            slug = node["slug"]
            path = f"{prefix}/{slug}" if prefix else slug
            existing = session.execute(select(Category).where(Category.slug == slug)).scalar_one_or_none()
            if existing is None:
                existing = Category(
                    parent_id=parent.id if parent else None,
                    slug=slug,
                    name_ar=node["name"],
                    name_normalized=normalize_search(node["name"]),
                    description=node.get("description"),
                    path=path,
                    sort_order=i,
                    triggers=node.get("triggers") or [node["name"]],
                )
                session.add(existing)
                session.flush()
            else:
                existing.triggers = node.get("triggers") or [node["name"]]
                existing.path = path
                existing.name_ar = node["name"]
                existing.name_normalized = normalize_search(node["name"])
                if node.get("description"):
                    existing.description = node["description"]
                if parent is not None and existing.parent_id is None:
                    existing.parent_id = parent.id
            walk(node.get("children") or [], existing, path)

    walk(TAXONOMY, None, "")


def _seed_admin(session: Session) -> None:
    settings = get_settings()
    row = session.execute(select(User).where(User.email == settings.admin_email)).scalar_one_or_none()
    if row:
        return
    session.add(
        User(
            email=settings.admin_email,
            password_hash=hash_password(settings.admin_password),
            display_name="أمين المكتبة",
            is_admin=True,
        )
    )
