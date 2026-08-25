# Domain model and database

## Catalog graph

```
Author 1---* AuthorAlias
Author *---* Work          (via work_contributors, with role)
Work   1---* Edition
Edition 1---* File
Work   *---* Category      (via work_categories, with confidence)
Work   1---* Cover
Work   *---* Tag
Edition *--- License
File   *--- SourceItem     (provenance)
```

### Work
The intellectual work shown in the catalog. Fields: original title/subtitle/description (display), normalized counterparts (match), language, slug, publication status, counters.

### Edition
A published manifestation: year, publisher, ISBN-10/13, page count, volume, edition statement, license.

### File
One stored bitstream: format (`pdf`/`epub`/future), sha256 (unique), mime (detected, not trusted from extension), size, storage_key, validation_status, source pointers.

### Author
Canonical name + aliases. Contributors have roles: `author`, `editor`, `translator`, `investigator`, `illustrator`.

### Category
Adjacency list (`parent_id`) plus materialized `path` (`din/fiqh/usul`) for prefix queries. Arbitrary depth.

## Integrity

| Rule | Enforcement |
|---|---|
| slug unique per works/authors/categories/publishers | UNIQUE |
| sha256 unique | UNIQUE on files |
| ISBN-13 unique when present | UNIQUE filtered by non-null |
| source + external_id unique | UNIQUE(source_id, external_id) |
| edition belongs to work | FK ON DELETE RESTRICT |
| file belongs to edition | FK ON DELETE RESTRICT |
| cannot publish work without ≥1 validated file | application + `publication_status` check |
| favorites / progress belong to users | FK CASCADE |

Deletion: published works are **hidden** (`publication_status=hidden`), not deleted. Files are marked `status=withdrawn`. Physical delete of storage objects is an admin action with audit log.

## Jobs and provenance

- `sources` — registry (see docs/sources).
- `source_items` — one discovered candidate, with eligibility and pipeline status.
- `import_events` — append-only log of stage transitions and errors.
- `jobs` — durable queue rows.
- `review_queue` — rights, duplicates, low-confidence classification, metadata.
- `duplicate_candidates` — scored pairs awaiting human decision.
- `audit_logs` — admin mutations.

## Ingestion states (`source_items.status`)

`discovered` → `queued` → `processing` → `downloaded` → `validated` → `classified` → `published`

Side states: `retrying`, `duplicate`, `quarantined`, `requires_review`, `rejected`, `failed`.

A source_item may produce a work/edition/file only after validation + eligibility.

## Search documents

`search_documents` mirrors published works. SQLite FTS5 virtual table `search_fts` is kept in sync in the same transaction as publish/hide.
