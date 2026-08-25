# Key decisions

## 1. Modular Python monolith, not a microservices mesh

**Choice:** FastAPI app + worker, shared domain.

**Why:** Ingestion, catalog integrity, and publishing are one transactional story. Splitting “crawler service / catalog service / search service” now would create consistency bugs (published book without file, file without index) before the product has operational staff.

**Rejected:** Next.js + separate Nest API. Node is available, but PDF/EPUB parsing, Arabic processing, and connectors are stronger and simpler in one Python tree. SSR Arabic SEO is native with Jinja2.

**Evolution:** Extract `connectors` and `search` to separate processes behind the existing interfaces when a single worker cannot keep up.

## 2. SQLite by default, PostgreSQL in production

**Choice:** SQLAlchemy 2 dialect-neutral models. SQLite for dev/test; Postgres URL for production.

**Why:** The current environment has SQLite and no local Postgres. Tests must run without Docker. The schema avoids Postgres-only types except through portable SQLAlchemy.

**FTS:** SQLite FTS5 on pre-normalized Arabic. Postgres will use `to_tsvector` + `pg_trgm` behind `SearchBackend`.

## 3. Database-backed job queue (no Redis required)

**Choice:** `jobs` table. Claim with `SKIP LOCKED` or SQLite write serialization.

**Why:** Redis is another SPOF and is not present in this environment. Durability and observability of ingestion jobs belong next to `source_items`.

**Rejected:** Celery/RQ as a hard dependency. Optional later.

## 4. Host files; never redirect readers away for eligible books

Eligible PDF/EPUB is stored in library object storage and served with range requests (PDF.js). External URLs are provenance, not the reading path.

## 5. Rights are a first-class state, not a boolean “downloaded”

Eligibility: `verified_public_domain` | `verified_open_license` | `explicitly_authorized` | `uncertain` | `prohibited`.

Only the first three auto-publish. `uncertain` goes to quarantine.

**Internet Archive warning:** User-applied Public Domain marks are frequently wrong. IA items are auto-published only when the collection is trusted *and* licenseurl is a known-good SPDX/CC/PD URI *and* author death/year heuristics pass. Otherwise quarantine.

## 6. OpenITI is the primary large legitimate Arabic corpus

Researched 2026-08-25:

| Source | Redistribution | Arabic volume | Connector |
|---|---|---|---|
| OpenITI (Zenodo/GitHub) | CC BY-NC-SA 4.0; modern editorial matter stripped | ~6,200+ distinct works | `openiti` — generate EPUB |
| Internet Archive texts | Mixed; PD/CC marks often user-asserted | Tens of thousands of files, high noise | `internet_archive` — strict filters |
| Project Gutenberg | US PD; redistribution allowed; do not scrape HTML (use catalog CSV) | 1 Arabic title in official catalog | `gutenberg` |
| OAPEN | OA books with explicit licenses | API unstable at research time | `oapen` (registered, optional) |
| Safahat / Hindawi | Free to read; re-host not clearly licensed | Large | registered, **no auto-ingest** |
| Shamela, Waqfeya, PDF aggregators | Not a redistribution grant | Large | **prohibited** |

OpenITI license is explicitly CC BY-NC-SA 4.0. This library is non-commercial. ShareAlike applies to our generated EPUBs of those texts. Attribution is stored on the edition and shown on the book page.

Author death year is encoded in the OpenITI URI. Auto-publish only when Hijri death year ≤ 1300 (~1882 CE). Later authors go to review.

## 7. Domain: Work → Edition → File

A user-facing “كتاب” is a **Work**. An edition may have PDF and EPUB. Files have hashes, mime, size, storage key.

## 8. Arabic search is normalized FTS, not SQL LIKE

Display text stays original. Search/dedup uses `normalize_search`. FTS5 index stores normalized title, subtitle, authors, publisher, identifiers, category names, and a short extracted text sample — not the full book body in v1 (full-text-of-books can be added as a separate index later).

## 9. Classification is evidence-scored, not title-keyword-only

Rules consume title, author subjects, source genre (e.g. OpenITI `GAL@hadith`), description, tags. Low confidence → review queue. Books may have multiple categories.

## 10. Server-rendered Arabic RTL UI

Native `dir="rtl" lang="ar"`. Mobile-first CSS. Bottom navigation on small screens; header nav on large screens. pdf.js and epub.js for in-library reading.

## 11. Storage interface: local now, S3-compatible later

`StorageBackend.put/get/delete/url`. Local filesystem for this environment. S3/R2 when credentials exist. Keys never come from user filenames.
