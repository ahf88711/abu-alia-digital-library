from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from abu_alia import __version__
from abu_alia.auth.csrf import csrf_protect, set_csrf_cookie, token_for_request
from abu_alia.auth.passwords import hash_password, verify_password
from abu_alia.auth.sessions import clear_session, set_session, user_id_from_request
from abu_alia.config import ROOT, get_settings
from abu_alia.db.models import (
    AuditLog,
    Author,
    Category,
    Collection,
    CollectionWork,
    DuplicateCandidate,
    Edition,
    Favorite,
    FileAsset,
    Job,
    ReviewItem,
    Source,
    SourceItem,
    User,
    Work,
    WorkCategory,
    WorkContributor,
)
from abu_alia.db.session import init_db, session_scope
from abu_alia.ingestion.pipeline import catalog_stats, enqueue_discovery
from abu_alia.jobs.queue import enqueue
from abu_alia.search.backend import search_works
from abu_alia.seed import seed_all
from abu_alia.storage.backend import storage_from_settings
from abu_alia.web.deps import get_current_user, get_db, require_admin, require_user
from abu_alia.web.helpers import (
    cover_of,
    formats_of,
    load_works_ordered,
    page_ids,
    paginate,
    primary_author,
    primary_category,
    work_query,
)
from abu_alia.storage.serve import file_response_with_range
from abu_alia.web.rate_limit import limit
from abu_alia.web.sanitize import plain_text

TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"

app = FastAPI(title="مكتبة أبو علياء الرقمية", version=__version__)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["plain"] = plain_text


def _ctx(request: Request, **kwargs):
    data = {
        "request": request,
        "user": getattr(request.state, "user", None),
        "app_name": "مكتبة أبو علياء الرقمية",
        "nav": request.url.path,
        "csrf_token": token_for_request(request),
    }
    data.update(kwargs)
    return data


@app.middleware("http")
async def attach_user(request: Request, call_next):
    factory = None
    try:
        from abu_alia.db.session import get_session_factory

        factory = get_session_factory()
        db = factory()
        uid = user_id_from_request(request)
        request.state.user = db.get(User, uid) if uid else None
        db.close()
    except Exception:
        request.state.user = None
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        settings = get_settings()
        if settings.is_production:
            origin = request.headers.get("origin")
            host = request.headers.get("host")
            if origin and host:
                from urllib.parse import urlparse

                if urlparse(origin).netloc != host:
                    return Response("رفض الطلب", status_code=403)
    token_for_request(request)
    response = await call_next(request)
    csrf_token = getattr(request.state, "csrf_token", None)
    if csrf_token:
        set_csrf_cookie(response, csrf_token)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "worker-src 'self' blob: https://cdnjs.cloudflare.com; "
        "frame-src 'self' blob:;"
    )
    if get_settings().is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.on_event("startup")
def _startup() -> None:
    settings = get_settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.tmp_root.mkdir(parents=True, exist_ok=True)
    settings.data_root.mkdir(parents=True, exist_ok=True)
    if settings.restore_on_boot:
        from abu_alia.deploy.restore import restore_catalog
        from abu_alia.db.session import reset_engine

        restore_catalog()
        reset_engine()
    init_db(settings)
    with session_scope() as session:
        seed_all(session)


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__}


@app.get("/api/stats")
def public_stats(db: Session = Depends(get_db)):
    stats = catalog_stats(db)
    return {
        "published": stats["published"],
        "pdf": stats["pdf"],
        "epub": stats["epub"],
        "version": __version__,
    }


@app.get("/robots.txt")
def robots():
    settings = get_settings()
    body = "User-agent: *\nAllow: /\nDisallow: /إدارة\nSitemap: " + settings.public_base_url.rstrip("/") + "/sitemap.xml\n"
    return Response(body, media_type="text/plain; charset=utf-8")


SITEMAP_PAGE_SIZE = 2000
SITEMAP_STATIC = (
    "/",
    "/كتب",
    "/تصنيفات",
    "/مؤلفون",
    "/بحث",
    "/عن-المكتبة",
    "/الحقوق",
    "/الخصوصية",
    "/الشروط",
)


def _urlset(locs: Sequence[str]) -> Response:
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc in locs:
        xml.append(f"<url><loc>{loc}</loc></url>")
    xml.append("</urlset>")
    return Response("\n".join(xml), media_type="application/xml")


@app.get("/sitemap.xml")
def sitemap(db: Session = Depends(get_db)):
    settings = get_settings()
    base = settings.public_base_url.rstrip("/")
    total = db.execute(select(func.count()).select_from(Work).where(Work.publication_status == "published")).scalar() or 0
    pages = max(1, (int(total) + SITEMAP_PAGE_SIZE - 1) // SITEMAP_PAGE_SIZE)
    if pages == 1:
        return sitemap_page(1, db)
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for i in range(1, pages + 1):
        xml.append(f"<sitemap><loc>{base}/sitemap-{i}.xml</loc></sitemap>")
    xml.append("</sitemapindex>")
    return Response("\n".join(xml), media_type="application/xml")


@app.get("/sitemap-{page}.xml")
def sitemap_page(page: int, db: Session = Depends(get_db)):
    settings = get_settings()
    base = settings.public_base_url.rstrip("/")
    total = db.execute(select(func.count()).select_from(Work).where(Work.publication_status == "published")).scalar() or 0
    pages = max(1, (int(total) + SITEMAP_PAGE_SIZE - 1) // SITEMAP_PAGE_SIZE)
    if page < 1 or page > pages:
        raise HTTPException(404)
    locs: List[str] = []
    if page == 1:
        locs.extend(base + path for path in SITEMAP_STATIC)
    offset = (page - 1) * SITEMAP_PAGE_SIZE
    slugs = db.execute(
        select(Work.slug)
        .where(Work.publication_status == "published")
        .order_by(Work.id)
        .offset(offset)
        .limit(SITEMAP_PAGE_SIZE)
    ).scalars().all()
    locs.extend(f"{base}/كتب/{slug}" for slug in slugs)
    return _urlset(locs)


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    latest = db.execute(work_query(db).order_by(Work.published_at.desc(), Work.id.desc()).limit(12)).scalars().unique().all()
    popular = db.execute(work_query(db).order_by(Work.download_count.desc(), Work.view_count.desc()).limit(8)).scalars().unique().all()
    viewed = db.execute(work_query(db).order_by(Work.view_count.desc()).limit(8)).scalars().unique().all()
    featured = db.execute(work_query(db).where(Work.featured.is_(True)).limit(8)).scalars().unique().all()
    cats = db.execute(select(Category).where(Category.parent_id.is_(None)).order_by(Category.sort_order)).scalars().all()
    authors = db.execute(select(Author).order_by(Author.id.desc()).limit(8)).scalars().all()
    book_count = db.execute(select(func.count()).select_from(Work).where(Work.publication_status == "published")).scalar() or 0
    author_count = db.execute(select(func.count()).select_from(Author)).scalar() or 0
    return templates.TemplateResponse(
        "public/home.html",
        _ctx(
            request,
            latest=latest,
            popular=popular,
            viewed=viewed,
            featured=featured or latest[:4],
            categories=cats,
            authors=authors,
            book_count=book_count,
            author_count=author_count,
            primary_author=primary_author,
            primary_category=primary_category,
            formats_of=formats_of,
            cover_of=cover_of,
        ),
    )


def _list_books(db, sort="newest"):
    q = work_query(db)
    if sort == "downloads":
        q = q.order_by(Work.download_count.desc())
    elif sort == "views":
        q = q.order_by(Work.view_count.desc())
    else:
        q = q.order_by(Work.published_at.desc(), Work.id.desc())
    return q


@app.get("/كتب", response_class=HTMLResponse)
def books_index(
    request: Request,
    db: Session = Depends(get_db),
    صفحة: int = Query(1, alias="page"),
    ترتيب: str = Query("newest", alias="sort"),
    صيغة: Optional[str] = Query(None, alias="fmt"),
):
    id_stmt = select(Work.id).where(Work.publication_status == "published")
    if صيغة:
        id_stmt = (
            id_stmt.join(Edition, Edition.work_id == Work.id)
            .join(FileAsset, FileAsset.edition_id == Edition.id)
            .where(FileAsset.format == صيغة, FileAsset.withdrawn.is_(False))
            .distinct()
        )
    if ترتيب == "downloads":
        id_stmt = id_stmt.order_by(Work.download_count.desc(), Work.id.desc())
    elif ترتيب == "views":
        id_stmt = id_stmt.order_by(Work.view_count.desc(), Work.id.desc())
    else:
        id_stmt = id_stmt.order_by(Work.published_at.desc(), Work.id.desc())
    ids, page, pages, _total = page_ids(db, id_stmt, صفحة, 24)
    slice_ = load_works_ordered(db, ids)
    return templates.TemplateResponse(
        "public/books.html",
        _ctx(
            request,
            title="جميع الكتب",
            works=slice_,
            page=page,
            pages=pages,
            sort=ترتيب,
            fmt=صيغة,
            primary_author=primary_author,
            primary_category=primary_category,
            formats_of=formats_of,
            cover_of=cover_of,
        ),
    )


@app.get("/كتب-جديدة", response_class=HTMLResponse)
def books_new(request: Request, db: Session = Depends(get_db), صفحة: int = Query(1, alias="page")):
    return books_index(request, db, صفحة, "newest", None)


@app.get("/الأكثر-تحميلا", response_class=HTMLResponse)
def books_dl(request: Request, db: Session = Depends(get_db), صفحة: int = Query(1, alias="page")):
    return books_index(request, db, صفحة, "downloads", None)


@app.get("/الأكثر-مشاهدة", response_class=HTMLResponse)
def books_viewed(request: Request, db: Session = Depends(get_db), صفحة: int = Query(1, alias="page")):
    return books_index(request, db, صفحة, "views", None)


@app.get("/كتب/{slug}", response_class=HTMLResponse)
def book_detail(slug: str, request: Request, db: Session = Depends(get_db)):
    work = db.execute(work_query(db).where(Work.slug == slug)).scalars().unique().first()
    if work is None:
        raise HTTPException(404, "الكتاب غير موجود")
    work.view_count += 1
    related = []
    cat = primary_category(work)
    if cat:
        related = (
            db.execute(
                work_query(db)
                .join(WorkCategory)
                .where(WorkCategory.category_id == cat.id, Work.id != work.id)
                .limit(6)
            )
            .scalars()
            .unique()
            .all()
        )
    same_author = []
    if work.contributors:
        aid = work.contributors[0].author_id
        same_author = (
            db.execute(
                work_query(db)
                .join(WorkContributor)
                .where(WorkContributor.author_id == aid, Work.id != work.id)
                .limit(6)
            )
            .scalars()
            .unique()
            .all()
        )
    fav = False
    user = getattr(request.state, "user", None)
    if user:
        fav = (
            db.execute(select(Favorite).where(Favorite.user_id == user.id, Favorite.work_id == work.id)).scalar_one_or_none()
            is not None
        )
    return templates.TemplateResponse(
        "public/book.html",
        _ctx(
            request,
            work=work,
            related=related,
            same_author=same_author,
            fav=fav,
            primary_author=primary_author,
            primary_category=primary_category,
            formats_of=formats_of,
            cover_of=cover_of,
        ),
    )


@app.get("/تصنيفات", response_class=HTMLResponse)
def categories_index(request: Request, db: Session = Depends(get_db)):
    roots = db.execute(select(Category).where(Category.parent_id.is_(None)).order_by(Category.sort_order)).scalars().all()
    children = db.execute(select(Category).where(Category.parent_id.is_not(None))).scalars().all()
    by_parent = {}
    for c in children:
        by_parent.setdefault(c.parent_id, []).append(c)
    counts = dict(
        db.execute(
            select(WorkCategory.category_id, func.count())
            .join(Work, Work.id == WorkCategory.work_id)
            .where(Work.publication_status == "published")
            .group_by(WorkCategory.category_id)
        ).all()
    )
    return templates.TemplateResponse(
        "public/categories.html",
        _ctx(request, roots=roots, by_parent=by_parent, counts=counts),
    )


@app.get("/تصنيفات/{path:path}", response_class=HTMLResponse)
def category_page(path: str, request: Request, db: Session = Depends(get_db), صفحة: int = Query(1, alias="page")):
    cat = db.execute(select(Category).where(or_(Category.slug == path, Category.path == path))).scalar_one_or_none()
    if cat is None:
        raise HTTPException(404, "التصنيف غير موجود")
    children = db.execute(select(Category).where(Category.parent_id == cat.id).order_by(Category.sort_order)).scalars().all()
    id_stmt = (
        select(Work.id)
        .where(Work.publication_status == "published")
        .join(WorkCategory, WorkCategory.work_id == Work.id)
        .join(Category, Category.id == WorkCategory.category_id)
        .where(or_(Category.id == cat.id, Category.path.startswith(cat.path + "/")))
        .distinct()
        .order_by(Work.published_at.desc(), Work.id.desc())
    )
    ids, page, pages, _total = page_ids(db, id_stmt, صفحة, 24)
    works = load_works_ordered(db, ids)
    return templates.TemplateResponse(
        "public/category.html",
        _ctx(
            request,
            category=cat,
            children=children,
            works=works,
            page=page,
            pages=pages,
            primary_author=primary_author,
            primary_category=primary_category,
            formats_of=formats_of,
            cover_of=cover_of,
        ),
    )


@app.get("/مؤلفون", response_class=HTMLResponse)
def authors_index(request: Request, db: Session = Depends(get_db), صفحة: int = Query(1, alias="page"), ق: str = Query("", alias="q")):
    stmt = select(Author)
    if ق:
        from abu_alia.arabic.normalize import normalize_search

        n = f"%{normalize_search(ق)}%"
        stmt = stmt.where(Author.name_normalized.like(n))
    stmt = stmt.order_by(Author.canonical_name)
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    page, pages = paginate(int(total), صفحة, 36)
    authors = db.execute(stmt.offset((page - 1) * 36).limit(36)).scalars().all()
    return templates.TemplateResponse(
        "public/authors.html",
        _ctx(request, authors=authors, page=page, pages=pages, q=ق),
    )


@app.get("/مؤلفون/{slug}", response_class=HTMLResponse)
def author_page(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
    صفحة: int = Query(1, alias="page"),
):
    author = db.execute(select(Author).where(Author.slug == slug)).scalar_one_or_none()
    if author is None:
        raise HTTPException(404, "المؤلف غير موجود")
    id_stmt = (
        select(Work.id)
        .where(Work.publication_status == "published")
        .join(WorkContributor, WorkContributor.work_id == Work.id)
        .where(WorkContributor.author_id == author.id)
        .order_by(Work.year.desc(), Work.id.desc())
    )
    ids, page, pages, _total = page_ids(db, id_stmt, صفحة, 48)
    works = load_works_ordered(db, ids)
    return templates.TemplateResponse(
        "public/author.html",
        _ctx(
            request,
            author=author,
            works=works,
            page=page,
            pages=pages,
            primary_author=primary_author,
            primary_category=primary_category,
            formats_of=formats_of,
            cover_of=cover_of,
        ),
    )


@app.get("/بحث", response_class=HTMLResponse)
def search_page(
    request: Request,
    db: Session = Depends(get_db),
    ق: str = Query("", alias="q"),
    تصنيف: Optional[str] = Query(None, alias="cat"),
    صيغة: Optional[str] = Query(None, alias="fmt"),
    ترتيب: str = Query("relevance", alias="sort"),
    صفحة: int = Query(1, alias="page"),
):
    settings = get_settings()
    if ق:
        limit(request, "search", settings.rate_limit_search_per_minute)
    result = {"total": 0, "items": [], "query": ق}
    if ق.strip():
        result = search_works(
            db,
            ق,
            limit=24,
            offset=(max(صفحة, 1) - 1) * 24,
            category_path=تصنيف,
            format_filter=صيغة,
            sort=ترتيب,
        )
    pages = max(1, (result["total"] + 23) // 24)
    cats = db.execute(select(Category).where(Category.parent_id.is_(None)).order_by(Category.sort_order)).scalars().all()
    return templates.TemplateResponse(
        "public/search.html",
        _ctx(
            request,
            q=ق,
            result=result,
            page=صفحة,
            pages=pages,
            cat=تصنيف,
            fmt=صيغة,
            sort=ترتيب,
            categories=cats,
            primary_author=primary_author,
            primary_category=primary_category,
            formats_of=formats_of,
            cover_of=cover_of,
        ),
    )


@app.get("/بحث-متقدم", response_class=HTMLResponse)
def advanced_search(request: Request, db: Session = Depends(get_db)):
    cats = db.execute(select(Category).order_by(Category.path)).scalars().all()
    return templates.TemplateResponse("public/advanced_search.html", _ctx(request, categories=cats))


@app.get("/مجموعات", response_class=HTMLResponse)
def collections_index(request: Request, db: Session = Depends(get_db)):
    cols = db.execute(select(Collection).order_by(Collection.id.desc())).scalars().all()
    return templates.TemplateResponse("public/collections.html", _ctx(request, collections=cols))


@app.get("/مجموعات/{slug}", response_class=HTMLResponse)
def collection_page(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
    صفحة: int = Query(1, alias="page"),
):
    col = db.execute(select(Collection).where(Collection.slug == slug)).scalar_one_or_none()
    if col is None:
        raise HTTPException(404, "المجموعة غير موجودة")
    id_stmt = (
        select(CollectionWork.work_id)
        .where(CollectionWork.collection_id == col.id)
        .order_by(CollectionWork.id)
    )
    ids, page, pages, _total = page_ids(db, id_stmt, صفحة, 24)
    works = load_works_ordered(db, ids)
    return templates.TemplateResponse(
        "public/collection.html",
        _ctx(
            request,
            collection=col,
            works=works,
            page=page,
            pages=pages,
            primary_author=primary_author,
            primary_category=primary_category,
            formats_of=formats_of,
            cover_of=cover_of,
        ),
    )


@app.get("/مكتبتي", response_class=HTMLResponse)
def my_library(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, "user", None)
    works = []
    if user:
        ids = [r[0] for r in db.execute(select(Favorite.work_id).where(Favorite.user_id == user.id)).all()]
        if ids:
            works = db.execute(work_query(db).where(Work.id.in_(ids))).scalars().unique().all()
    return templates.TemplateResponse(
        "public/my_library.html",
        _ctx(
            request,
            works=works,
            primary_author=primary_author,
            primary_category=primary_category,
            formats_of=formats_of,
            cover_of=cover_of,
        ),
    )


@app.post("/مكتبتي/{slug}")
def toggle_favorite(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    _: None = Depends(csrf_protect),
):
    work = db.execute(select(Work).where(Work.slug == slug)).scalar_one_or_none()
    if not work:
        raise HTTPException(404)
    fav = db.execute(select(Favorite).where(Favorite.user_id == user.id, Favorite.work_id == work.id)).scalar_one_or_none()
    if fav:
        db.delete(fav)
    else:
        db.add(Favorite(user_id=user.id, work_id=work.id))
    return RedirectResponse(f"/كتب/{slug}", status_code=303)


@app.get("/عن-المكتبة", response_class=HTMLResponse)
def about(request: Request):
    return templates.TemplateResponse("public/about.html", _ctx(request))


@app.get("/تواصل", response_class=HTMLResponse)
def contact_get(request: Request):
    return templates.TemplateResponse("public/contact.html", _ctx(request, sent=False))


@app.post("/تواصل", response_class=HTMLResponse)
def contact_post(
    request: Request,
    db: Session = Depends(get_db),
    الاسم: str = Form(...),
    البريد: str = Form(""),
    الرسالة: str = Form(...),
    _: None = Depends(csrf_protect),
):
    db.add(
        AuditLog(
            action="contact",
            entity_type="message",
            payload={"name": الاسم[:200], "email": البريد[:200], "message": الرسالة[:4000]},
            ip=request.client.host if request.client else None,
        )
    )
    return templates.TemplateResponse("public/contact.html", _ctx(request, sent=True))


@app.get("/الحقوق", response_class=HTMLResponse)
def licenses_page(request: Request):
    return templates.TemplateResponse("public/licenses.html", _ctx(request))


@app.get("/الخصوصية", response_class=HTMLResponse)
def privacy(request: Request):
    return templates.TemplateResponse("public/privacy.html", _ctx(request))


@app.get("/الشروط", response_class=HTMLResponse)
def terms(request: Request):
    return templates.TemplateResponse("public/terms.html", _ctx(request))


@app.get("/دخول", response_class=HTMLResponse)
def login_get(request: Request):
    return templates.TemplateResponse("public/login.html", _ctx(request, error=None, mode="login"))


@app.post("/دخول")
def login_post(
    request: Request,
    db: Session = Depends(get_db),
    البريد: str = Form(...),
    كلمة_السر: str = Form(...),
    _: None = Depends(csrf_protect),
):
    settings = get_settings()
    limit(request, "login", settings.rate_limit_login_per_minute)
    user = db.execute(select(User).where(User.email == البريد.strip().lower())).scalar_one_or_none()
    if user is None or not verify_password(كلمة_السر, user.password_hash):
        return templates.TemplateResponse(
            "public/login.html",
            _ctx(request, error="بيانات الدخول غير صحيحة", mode="login"),
            status_code=401,
        )
    resp = RedirectResponse("/", status_code=303)
    set_session(resp, user.id)
    return resp


@app.get("/تسجيل", response_class=HTMLResponse)
def register_get(request: Request):
    return templates.TemplateResponse("public/login.html", _ctx(request, error=None, mode="register"))


@app.post("/تسجيل")
def register_post(
    request: Request,
    db: Session = Depends(get_db),
    الاسم: str = Form(...),
    البريد: str = Form(...),
    كلمة_السر: str = Form(...),
    _: None = Depends(csrf_protect),
):
    settings = get_settings()
    limit(request, "register", settings.rate_limit_login_per_minute)
    email = البريد.strip().lower()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        return templates.TemplateResponse(
            "public/login.html",
            _ctx(request, error="البريد مستخدم مسبقاً", mode="register"),
        )
    user = User(email=email, password_hash=hash_password(كلمة_السر), display_name=الاسم.strip()[:80])
    db.add(user)
    db.flush()
    resp = RedirectResponse("/", status_code=303)
    set_session(resp, user.id)
    return resp


@app.post("/خروج")
def logout(_: None = Depends(csrf_protect)):
    resp = RedirectResponse("/", status_code=303)
    clear_session(resp)
    return resp


def _file_for(db: Session, slug: str, fmt: str) -> FileAsset:
    work = db.execute(work_query(db).where(Work.slug == slug)).scalars().unique().first()
    if not work:
        raise HTTPException(404)
    for ed in work.editions:
        for f in ed.files:
            if f.format == fmt and not f.withdrawn and f.validation_status == "validated":
                return f
    raise HTTPException(404, "الملف غير متوفر")


@app.get("/قراءة/{slug}/pdf", response_class=HTMLResponse)
def read_pdf(slug: str, request: Request, db: Session = Depends(get_db)):
    work = db.execute(work_query(db).where(Work.slug == slug)).scalars().unique().first()
    if not work:
        raise HTTPException(404)
    return templates.TemplateResponse("reader/pdf.html", _ctx(request, work=work, fmt="pdf", primary_author=primary_author))


@app.get("/قراءة/{slug}/epub", response_class=HTMLResponse)
def read_epub(slug: str, request: Request, db: Session = Depends(get_db)):
    work = db.execute(work_query(db).where(Work.slug == slug)).scalars().unique().first()
    if not work:
        raise HTTPException(404)
    return templates.TemplateResponse("reader/epub.html", _ctx(request, work=work, fmt="epub", primary_author=primary_author))


@app.get("/ملفات/{slug}/{fmt}")
def stream_file(slug: str, fmt: str, request: Request, db: Session = Depends(get_db), تنزيل: int = Query(0, alias="dl")):
    if fmt not in ("pdf", "epub"):
        raise HTTPException(400)
    settings = get_settings()
    limit(request, "download", settings.rate_limit_download_per_minute)
    fa = _file_for(db, slug, fmt)
    if تنزيل:
        work = fa.edition.work
        work.download_count += 1
    storage = storage_from_settings()
    path = storage.path_for(fa.storage_key)
    if not path.exists():
        raise HTTPException(404)
    filename = f"{slug}.{fmt}" if تنزيل else None
    return file_response_with_range(path, request, media_type=fa.mime, download_name=filename)


@app.get("/أغلفة/{work_id}")
def cover_file(work_id: int, db: Session = Depends(get_db)):
    work = db.get(Work, work_id)
    if not work or not work.covers:
        raise HTTPException(404)
    storage = storage_from_settings()
    path = storage.path_for(work.covers[0].storage_key)
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg")


# ----- admin -----


@app.get("/إدارة", response_class=HTMLResponse)
def admin_home(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    stats = {
        "works": db.execute(select(func.count()).select_from(Work)).scalar() or 0,
        "published": db.execute(select(func.count()).select_from(Work).where(Work.publication_status == "published")).scalar()
        or 0,
        "pdf": db.execute(select(func.count()).select_from(FileAsset).where(FileAsset.format == "pdf")).scalar() or 0,
        "epub": db.execute(select(func.count()).select_from(FileAsset).where(FileAsset.format == "epub")).scalar() or 0,
        "queued": db.execute(select(func.count()).select_from(Job).where(Job.status.in_(("queued", "retrying")))).scalar() or 0,
        "running": db.execute(select(func.count()).select_from(Job).where(Job.status == "running")).scalar() or 0,
        "dead": db.execute(select(func.count()).select_from(Job).where(Job.status == "dead")).scalar() or 0,
        "review": db.execute(select(func.count()).select_from(ReviewItem).where(ReviewItem.status == "open")).scalar() or 0,
        "quarantine": db.execute(select(func.count()).select_from(SourceItem).where(SourceItem.status == "quarantined")).scalar()
        or 0,
        "failed": db.execute(select(func.count()).select_from(SourceItem).where(SourceItem.status == "failed")).scalar() or 0,
    }
    sources = db.execute(select(Source).order_by(Source.id)).scalars().all()
    jobs = db.execute(select(Job).order_by(Job.id.desc()).limit(20)).scalars().all()
    return templates.TemplateResponse("admin/dashboard.html", _ctx(request, stats=stats, sources=sources, jobs=jobs))


@app.get("/إدارة/كتب", response_class=HTMLResponse)
def admin_books(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    صفحة: int = Query(1, alias="page"),
):
    total = db.execute(select(func.count()).select_from(Work)).scalar() or 0
    page, pages = paginate(int(total), صفحة, 50)
    works = db.execute(select(Work).order_by(Work.id.desc()).offset((page - 1) * 50).limit(50)).scalars().all()
    return templates.TemplateResponse("admin/books.html", _ctx(request, works=works, page=page, pages=pages))


@app.post("/إدارة/كتب/{work_id}/نشر")
def admin_publish(
    work_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    _: None = Depends(csrf_protect),
):
    work = db.get(Work, work_id)
    if not work:
        raise HTTPException(404)
    work.publication_status = "published"
    from abu_alia.db.models import utcnow
    from abu_alia.search.backend import index_work

    work.published_at = utcnow()
    db.flush()
    w = db.execute(work_query(db).where(Work.id == work.id)).scalars().unique().first()
    if w:
        index_work(db, w)
    return RedirectResponse("/إدارة/كتب", status_code=303)


@app.post("/إدارة/كتب/{work_id}/إخفاء")
def admin_hide(
    work_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    _: None = Depends(csrf_protect),
):
    work = db.get(Work, work_id)
    if work:
        work.publication_status = "hidden"
    return RedirectResponse("/إدارة/كتب", status_code=303)


@app.get("/إدارة/مصادر", response_class=HTMLResponse)
def admin_sources(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    sources = db.execute(select(Source).order_by(Source.id)).scalars().all()
    return templates.TemplateResponse("admin/sources.html", _ctx(request, sources=sources))


@app.post("/إدارة/مصادر/{code}/اكتشاف")
def admin_discover(
    code: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    _: None = Depends(csrf_protect),
):
    enqueue_discovery(db, code)
    return RedirectResponse("/إدارة/مصادر", status_code=303)


@app.get("/إدارة/مراجعة", response_class=HTMLResponse)
def admin_review(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    items = db.execute(select(ReviewItem).where(ReviewItem.status == "open").order_by(ReviewItem.id.desc()).limit(100)).scalars().all()
    quarantine = db.execute(select(SourceItem).where(SourceItem.status == "quarantined").limit(100)).scalars().all()
    dups = db.execute(select(DuplicateCandidate).where(DuplicateCandidate.decision == "pending").limit(50)).scalars().all()
    return templates.TemplateResponse("admin/review.html", _ctx(request, items=items, quarantine=quarantine, dups=dups))


@app.post("/إدارة/مراجعة/{item_id}/حل")
def admin_resolve_review(
    item_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    القرار: str = Form("resolved"),
    _: None = Depends(csrf_protect),
):
    item = db.get(ReviewItem, item_id)
    if item:
        item.status = "closed"
        item.resolution = القرار
        item.resolved_by_id = admin.id
    return RedirectResponse("/إدارة/مراجعة", status_code=303)


@app.get("/إدارة/وظائف", response_class=HTMLResponse)
def admin_jobs(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    jobs = db.execute(select(Job).order_by(Job.id.desc()).limit(100)).scalars().all()
    failed = db.execute(select(SourceItem).where(SourceItem.status == "failed").order_by(SourceItem.id.desc()).limit(50)).scalars().all()
    return templates.TemplateResponse("admin/jobs.html", _ctx(request, jobs=jobs, failed=failed))


@app.get("/إدارة/مؤلفون", response_class=HTMLResponse)
def admin_authors(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    authors = db.execute(select(Author).order_by(Author.id.desc()).limit(200)).scalars().all()
    return templates.TemplateResponse("admin/authors.html", _ctx(request, authors=authors))


@app.get("/إدارة/إعدادات", response_class=HTMLResponse)
def admin_settings(request: Request, admin: User = Depends(require_admin)):
    settings = get_settings()
    storage = storage_from_settings()
    return templates.TemplateResponse(
        "admin/settings.html",
        _ctx(request, settings=settings, storage_bytes=storage.usage_bytes()),
    )


def create_app() -> FastAPI:
    return app
