from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[2]


def detect_data_root() -> Path:
    env = os.environ.get("ABU_ALIA_DATA_ROOT")
    if env:
        return Path(env)
    render_disk = Path("/var/data")
    if render_disk.is_dir() and os.access(render_disk, os.W_OK):
        return render_disk
    return ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ABU_ALIA_",
        env_file=str(ROOT / ".env"),
        extra="ignore",
    )

    env: str = "development"
    secret_key: str = "dev-only-change-in-production"
    data_root: Path = detect_data_root()
    database_url: str = ""
    storage_root: Path = Path()
    tmp_root: Path = Path()
    cache_root: Path = Path()
    public_base_url: str = "http://127.0.0.1:8080"
    catalog_snapshot_db: Optional[str] = (
        "https://github.com/ahf88711/abu-alia-digital-library/releases/download/catalog-4024/library.db.gz"
    )
    catalog_snapshot_storage: Optional[str] = (
        "https://github.com/ahf88711/abu-alia-digital-library/releases/download/catalog-4024/storage.tar"
    )
    restore_on_boot: bool = False
    restore_storage: bool = True
    admin_email: str = "admin@localhost"
    admin_password: str = "change-me-now"
    session_days: int = 14
    max_file_bytes: int = 40 * 1024 * 1024
    max_epub_uncompressed_bytes: int = 120 * 1024 * 1024
    max_epub_files: int = 4000
    worker_id: str = "worker-1"
    worker_concurrency: int = 1
    job_poll_seconds: float = 1.5
    job_max_attempts: int = 5
    request_timeout_seconds: float = 90.0
    http_attempts: int = 6
    harvest_target: int = 4000
    harvest_batch: int = 40
    openiti_max_tokens: int = 900000
    user_agent: str = (
        "AbuAliaDigitalLibrary/1.0 (+https://github.com/ahf88711/abu-alia-digital-library)"
    )
    live_network: bool = False
    ingestion_batch_limit: int = 50
    openiti_max_death_ah: int = 1300
    trusted_ia_collections: str = (
        "gutenberg,gutenbergbooks,americana,library_of_congress,"
        "bostonpubliclibrary,university_maryland_cp,opensource_media"
    )
    bind_host: str = "127.0.0.1"
    bind_port: int = 8080
    rate_limit_search_per_minute: int = 90
    rate_limit_login_per_minute: int = 12
    rate_limit_download_per_minute: int = 60
    default_locale: str = "ar"
    s3_bucket: Optional[str] = None
    s3_endpoint: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_region: str = "auto"
    font_dir: Path = ROOT / "static" / "fonts"

    @model_validator(mode="after")
    def _fill_paths(self) -> "Settings":
        root = Path(self.data_root)
        root.mkdir(parents=True, exist_ok=True)
        if not self.database_url:
            db = (root / "library.db").resolve()
            self.database_url = "sqlite:///" + str(db)
        if not str(self.storage_root) or str(self.storage_root) == ".":
            self.storage_root = root / "storage"
        if not str(self.tmp_root) or str(self.tmp_root) == ".":
            self.tmp_root = root / "tmp"
        if not str(self.cache_root) or str(self.cache_root) == ".":
            self.cache_root = root / "cache"
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.tmp_root.mkdir(parents=True, exist_ok=True)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def trusted_ia_set(self):
        return {p.strip() for p in self.trusted_ia_collections.split(",") if p.strip()}


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings(settings: Optional[Settings] = None) -> Settings:
    global _settings
    _settings = settings if settings is not None else Settings()
    return _settings
