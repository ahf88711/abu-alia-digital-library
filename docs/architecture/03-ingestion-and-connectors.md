# Ingestion, connectors, rights, duplicates, classification

## Connector interface

Each source implements:

```
class SourceConnector(Protocol):
    source_code: str
    def discover(self, cursor) -> Iterator[DiscoveredItem]
    def fetch_metadata(self, item) -> SourceMetadata
    def discover_files(self, item) -> List[RemoteFile]
    def download(self, remote_file, dest) -> Path
    def throttle(self) -> None
```

The pipeline never imports a site-specific parser.

## Pipeline stages (always explicit)

1. Source discovery (registry enabled sources)
2. Candidate discovery (`source_items`)
3. Eligibility check (`rights`)
4. Metadata fetch
5. File discovery
6. Download (or generate, e.g. OpenITI EPUB)
7. Integrity + magic-byte validation
8. Fingerprint (sha256, size, metadata fingerprint, optional extracted-text simhash)
9. Metadata extraction (PDF info, EPUB OPF)
10. Arabic normalization
11. Author resolution
12. Edition resolution
13. Duplicate detection
14. Classification
15. Cover processing
16. Storage persist
17. Database persist
18. Search index
19. Publication validation
20. Publish **or** quarantine/review

Retries: exponential backoff on the `jobs` row (`attempts`, `run_after`). After `max_attempts`, `dead`. The source_item is `failed` with last event. Other sources keep running.

## Rights

License URLs mapped to SPDX-like codes. Redistribution allowed only for:

- Public domain marks **from trusted issuers** (Gutenberg catalog; OpenITI death-year rule; institutional IA collections)
- CC BY, BY-SA, BY-NC, BY-NC-SA, CC0 (NC allowed because this product is non-commercial)
- Explicit written authorization stored as evidence JSON

Prohibited: in-copyright, controlled digital lending (`inlibrary`), unknown aggregators, “free download” without a license.

## Duplicate detection

Signals (weighted):

| Signal | Weight | Implies |
|---|---|---|
| identical sha256 | 1.00 | same file |
| ISBN-13 match | 0.95 | same edition |
| normalized title + author + year | 0.85 | same edition candidate |
| normalized title + author, different year | 0.70 | same work, maybe new edition |
| title similarity ≥ 0.92, different author | 0.40 | review (possible coincidence) |
| size+page_count close + title similar | 0.55 | review |

Auto-merge only: identical hash (attach format to existing edition/work) or ISBN-13 exact.

Uncertain matches create `duplicate_candidates` + review queue. Never auto-merge translations or volumes.

## Classification

Taxonomy seeded from `data/taxonomy.json` (hierarchical Arabic names + slugs + trigger terms + author-subject hints).

Scorer aggregates evidence:

- source genre (OpenITI `GAL@hadith` etc.)
- normalized title terms
- author known subjects
- description terms
- publisher hints

Primary category = highest score ≥ 0.45. Additional categories if score ≥ 0.55 and not ancestor/descendant of primary. Below 0.45 → `requires_review` but the work may still publish with `uncategorized` pending librarian action.

Evidence JSON is stored on `work_categories`.
