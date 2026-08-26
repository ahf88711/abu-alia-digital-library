# PROJECT_STATUS

- **current phase:** harvest-target-reached
- **updated:** 2026-08-25T23:42:02Z
- **published unique works:** 4024
- **PDF files:** 2
- **EPUB files:** 4024
- **failed imports:** 3 (OpenITI TSV entries whose files are missing on GitHub/jsDelivr; not invented)
- **quarantined:** 0
- **discovered source items:** 4027
- **queued/retrying jobs:** 0
- **harvest target:** 4000 (target, not to be fabricated)
- **note:** OpenITI harvest stopped after reaching 4024 published unique works. Do not invent more books.
- **file sample:** 80/80 valid EPUB/PDF; 0 sha256 collisions in sample
- **architecture:** modular FastAPI monolith; OpenITI CC BY-NC-SA; IA untrusted PD marks quarantined
- **GitHub:** https://github.com/ahf88711/abu-alia-digital-library
- **public site:** https://abu-alia-digital-library.onrender.com
- **production catalog:** 4024 published (verified `/api/stats`, homepage, `/كتب` pager 1/168, EPUB 206)
- **deployment note:** empty Render disk was the cause; `restore-catalog` copies the existing snapshot (GitHub Release `catalog-4024`) when the data dir is empty. Harvest was not restarted.
- **next:** keep the catalog; do not duplicate or invent books
