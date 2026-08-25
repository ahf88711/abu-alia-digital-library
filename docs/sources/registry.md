# Source registry (research snapshot, 2026-08-25)

| Source | Type | Arabic volume | Formats | API | Redistribution | Connector |
|---|---|---|---|---|---|---|
| OpenITI | scholarly corpus | ~6,200 unique works | text → generated EPUB | GitHub/Zenodo TSV | **CC BY-NC-SA 4.0**; modern apparatus stripped | `openiti` active |
| Project Gutenberg | PD library | 1 Arabic title in official CSV | EPUB/PDF | catalog CSV (do not scrape HTML) | US PD, redistribution allowed | `gutenberg` active |
| Internet Archive texts | mixed library | tens of thousands of files; high noise | PDF/EPUB | advancedsearch + metadata | PD/CC marks often **user-asserted** | `internet_archive` active, strict |
| OAPEN | OA academic | small Arabic subset with explicit CC | PDF | REST | per-book CC URI required | `oapen` implemented, **disabled** during OpenITI harvest |
| Safahat / Hindawi | publisher free-to-read | thousands | PDF/EPUB | none official | **uncertain** re-host | registered, disabled |
| Arabic Wikisource | wiki | complete long pages only | text → generated EPUB | MediaWiki API | CC BY-SA 3.0 | `wikisource_ar` implemented, **disabled** during OpenITI harvest |
| Qatar Digital Library | heritage | manuscripts/archives | images/PDF | mixed | PD/CC labelled; ToS requires local determination | researched, not connected |
| King Fahd National Library | national | unknown bulk export | mixed | none found | no redistribution grant found | researched only |
| al-Maktaba al-Shamela / Waqfeya / pirate aggregators | mixed/pirate | large | PDF/text | scrape | **prohibited** | not connected |

## Policy

“Available to download” is not “allowed to re-host.” Auto-publish only `verified_public_domain`, `verified_open_license`, `explicitly_authorized`.
