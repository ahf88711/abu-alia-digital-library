# مكتبة أبو علياء الرقمية

مكتبة عربية رقمية تستضيف بنفسها ملفات الكتب المؤهلة (PDF و EPUB) وتتيح قراءتها وتنزيلها مباشرة.

This repository contains **application code only**. Book files live in object storage (`data/storage/` locally), never in Git.

## Architecture

See [`docs/architecture/00-overview.md`](docs/architecture/00-overview.md).

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python -m abu_alia init
PYTHONPATH=src .venv/bin/python -m abu_alia ingest fixture --limit 10
PYTHONPATH=src .venv/bin/python -m abu_alia serve --host 127.0.0.1 --port 8080
```

In another terminal:

```bash
PYTHONPATH=src .venv/bin/python -m abu_alia worker
```

Default admin (change in production):

- Email: `admin@localhost`
- Password: `change-me-now`

Environment is prefixed `ABU_ALIA_`. Important variables: `DATABASE_URL`, `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `STORAGE_ROOT`, `ENV=production`.

## Tests

```bash
PYTHONPATH=src .venv/bin/python -m pytest
```

## Ingestion sources

Eligible connectors:

- **OpenITI** (CC BY-NC-SA 4.0, premodern works) — primary Arabic corpus
- **Project Gutenberg** (US public domain catalog)
- **Internet Archive** (trusted collections + explicit licenses only; otherwise quarantine)

See `docs/sources/` and the in-app source registry.

## Production

`render.yaml` describes a web process and a worker. Attach PostgreSQL and a persistent disk (or S3-compatible storage) before large-scale ingestion. Never commit book binaries or secrets.
