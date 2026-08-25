# Frontend, security, operations

## Frontend

- `lang="ar" dir="rtl"` on `<html>`. Native RTL, not a mirrored LTR theme.
- Mobile-first. Bottom nav (الرئيسية، التصنيفات، البحث، مكتبتي) with `env(safe-area-inset-bottom)`. Hidden on `min-width: 900px` in favor of header nav.
- Design: ink, parchment, muted gold. Amiri for titles, IBM Plex Sans Arabic for UI. No glassmorphism, neon, or template-dashboard look.
- Server-rendered pages for SEO (`/كتب/...`, `/مؤلفون/...`, `/تصنيفات/...`).
- PDF reader: pdf.js, fit-width default on phones, range-request file endpoint.
- EPUB reader: epub.js, `dir=rtl` spine, font-size and theme controls, progress in `reading_progress`.

## Public pages (all implemented, none are stubs)

الرئيسية، جميع الكتب، دليل التصنيفات، التصنيف، التصنيف الفرعي، الكتاب، قارئ PDF، قارئ EPUB، المؤلف، دليل المؤلفين، البحث، البحث المتقدم، الكتب الجديدة، الأكثر تحميلًا، الأكثر مشاهدة، المجموعات، مكتبتي، عن المكتبة، تواصل معنا، الحقوق والتراخيص، الخصوصية، الشروط.

## Admin

Arabic admin, session cookie, `is_admin` gate. Dashboard, catalog, sources, jobs, quarantine, duplicates, classification review, users, settings, audit, storage/queue health.

## Security

- External HTML/PDF/EPUB is untrusted data. Bleach on any rendered description. No eval of scraped content.
- File magic bytes + size cap + zip-bomb guard for EPUB (uncompressed ratio/count).
- Path traversal: storage keys are generated from sha256, never from filenames.
- CSRF on cookie-authenticated POST.
- Argon2id passwords. HttpOnly session cookie. Secure in production.
- Rate limit login and search (in-process sliding window; interface ready for shared store).
- Security headers: CSP (pdf.js worker allowed), `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` (readers may need same-origin iframe).
- Secrets only via environment. Never in git.
- Audit log for admin writes.

## Observability

Structured log lines (`ts`, `level`, `event`, `job_id`, `source_item_id`). Admin pages for job health, failed imports, storage usage. `/api/health` for deploy probes.

## Deployment

| Piece | Dev | Production intent |
|---|---|---|
| App | `uvicorn abu_alia.web.app:app` | Render/Fly web process |
| Worker | `python -m abu_alia.worker` | Same image, worker process |
| DB | SQLite `data/library.db` | PostgreSQL |
| Files | `data/storage` | Persistent disk or S3 |
| Code | GitHub | GitHub |

`render.yaml` describes a web service + worker. Persistent disk is required for books if S3 is not configured.

## Backup

- Database: periodic dump (SQLite file copy / `pg_dump`).
- Object storage: filesystem rsync or S3 versioning.
- Restore: empty DB + migrations + import dump + storage tree. Jobs resume from `source_items`.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Crawler IP ban | Per-source throttle, robots respect, official catalogs/APIs first |
| IA false PD marks | Trusted-collection gate; else quarantine |
| Duplicate floods | Hash unique + review workflow |
| Worker crash mid-download | Temp dir + atomic rename; job retry |
| SQLite writer lock | Short transactions; one worker in SQLite mode |
| Storage fill | `MAX_FILE_BYTES`, skip huge IA items, disk alerts in admin |
| Classification error | Confidence threshold + librarian override |
| XSS via book titles | Jinja autoescape; CSP |
| Range-request abuse | Auth not required for published files; size and rate limits |
| Single web process | Stateless app; scale web replicas with shared DB+storage |

## Testing strategy

Unit: arabic, rights, duplicates, classification, file signatures, slugify.

Integration: pipeline with fixture connector (tiny PDF/EPUB), FTS search, authz, publish guards.

Connector tests: HTTP mocked; optional live tests behind `ABU_ALIA_LIVE_NETWORK=1`.
