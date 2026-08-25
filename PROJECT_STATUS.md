# PROJECT_STATUS

- **current phase:** harvesting
- **updated:** 2026-08-25T21:39:00Z
- **published unique works:** 1640
- **PDF files:** 2
- **EPUB files:** 1640
- **failed imports:** 0
- **quarantined:** 0
- **discovered source items:** 1640
- **queued/retrying jobs:** 0
- **harvest target:** 4000 (target, not to be fabricated)
- **note:** OpenITI harvest still running; file sample 40/40 valid; 0 sha256 collisions in sample
- **architecture:** modular FastAPI monolith; OpenITI CC BY-NC-SA; IA untrusted PD marks quarantined
- **GitHub:** https://github.com/ahf88711/abu-alia-digital-library
- **deployment:** production public URL not claimed without hosting credentials
- **blockers:** public hosting/S3 credentials (Render/Fly/Railway) — continue every other task
- **engineering this checkpoint:** CSRF on POST; byte-range file serving; paginated sitemaps; HSTS/Permissions-Policy; Wikisource connector implemented but disabled during OpenITI harvest; EPUB reader font/theme/progress; 42 tests passing
- **next:** continue OpenITI harvest toward 4000; do not invent books; enable Wikisource only if still short after OpenITI; do not start a second SQLite writer
