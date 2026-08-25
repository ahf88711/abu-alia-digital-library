from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ABU_ALIA_",
        env_file=str(ROOT / ".env"),
        extra="ignore",
    )

    env: str = "development"
    secret_key: str = "dev-only-change-in-production"
    database_url: str = f"sqlite:///{ROOT / 'data' / 'library.db'}"
    storage_root: Path = ROOT / "data" / "storage"
    tmp_root: Path = ROOT / "data" / "tmp"
    cache_root: Path = ROOT / "data" / "cache"
    public_base_url: str = "http://127.0.0.1:8080"
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
    default_locale: str = "ar"
    s3_bucket: Optional[str] = None
    s3_endpoint: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_region: str = "auto"
    font_dir: Path = ROOT / "static" / "fonts"

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
