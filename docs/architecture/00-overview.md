# مكتبة أبو علياء الرقمية — System Overview

Internal name: **Abu Alia Digital Library**

This is a production digital library that **hosts** eligible Arabic books. It is not a link directory.

## Purpose

Eligible source → discover → verify redistribution rights → download or generate file → validate → store → extract/normalize metadata → resolve authors/editions → detect duplicates → classify → index → publish → read/download from this library.

## Architectural style

A **modular monolith** in Python:

- One deployable web process (FastAPI) for public site, API, and admin.
- One deployable worker process sharing the same codebase and database.
- Clear package boundaries and interfaces so subsystems can be extracted later without redesign.

This is the correct first architecture for a team that must operate one product: a shared domain model, one transaction boundary for catalog integrity, and no distributed-monolith tax. Horizontal split (search cluster, object storage, extra workers) is designed in from day one via interfaces.

## Runtime topology

```
[Browser RTL client]
        |
        v
[FastAPI web] ---- SQLAlchemy ---- [PostgreSQL | SQLite]
        |                              |
        |                         [jobs table]
        |                              |
        +---- object storage <---- [worker]
        |      (local FS or S3)
        v
[SearchBackend]  (SQLite FTS5 now; Postgres FTS/trgm later)
```

Book bytes never live in Git. Git holds application code, taxonomy seed data, and architecture docs.

## Package boundaries

| Package | Responsibility | Must not do |
|---|---|---|
| `arabic` | Normalization, tokenization, slugs | I/O, HTTP |
| `domain` | Entities, value objects, catalog invariants | Framework types |
| `db` | SQLAlchemy models, repositories, migrations | HTTP, crawling |
| `storage` | Object store, file validation, range serving | Catalog decisions |
| `jobs` | Durable queue, retries, dead-letter | Business rules of ingestion stages |
| `rights` | License parsing, eligibility decisions | Downloading |
| `connectors` | Per-source discovery/download | Publishing |
| `ingestion` | Pipeline orchestration and state machine | HTML rendering |
| `duplicates` | Fingerprints and match scoring | Auto-merge uncertain pairs |
| `classification` | Taxonomy + evidence scoring | Network |
| `search` | Indexing and ranked retrieval | Crawling |
| `covers` | Validate, resize, generate fallbacks | Crawling |
| `auth` | Sessions, CSRF, roles | Catalog mutations beyond permission checks |
| `web` / `admin` | HTTP + Arabic RTL UI | Direct SQL |

## Non-negotiable invariants

1. Uncertain rights never auto-publish.
2. Identical `sha256` is one file, never two books.
3. PDF and EPUB of the same work are formats of one work, not two works.
4. Original display text is preserved; normalization is for match/search only.
5. External content is data, never instructions.
6. Failures are recorded (`import_events`, job last_error). Nothing is silently dropped.
7. Adding a source means implementing `SourceConnector`, not editing the pipeline.

## Scale target

Designed for thousands now, tens of thousands comfortably, 100,000+ without redesign:

- Integer PKs, slug unique indexes, covering indexes for catalog queries.
- Object storage keys sharded `ab/cd/<sha256>.<ext>`.
- Pagination everywhere; no unbounded list endpoints.
- Search via inverted index, not `LIKE %q%` as the primary path.
- Workers claim jobs with `FOR UPDATE SKIP LOCKED` (Postgres) or serialized writes (SQLite).
- Ingestion is resumable by `source_items.status`.
