from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from abu_alia.config import get_settings

SKIP_PREFIXES = ("/static", "/api/", "/ملفات", "/أغلفة", "/favicon")
BOT_MARKERS = ("bot", "spider", "crawler", "preview", "slurp", "curl/", "python-requests", "httpx")


def _path() -> Path:
    root = Path(get_settings().data_root)
    root.mkdir(parents=True, exist_ok=True)
    return root / "visitor_count.json"


def read_count() -> int:
    try:
        raw = _path().read_text(encoding="utf-8")
        data = json.loads(raw)
        return max(0, int(data.get("count", 0)))
    except Exception:
        return 0


def increment() -> Optional[int]:
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text('{"count": 0}', encoding="utf-8")
        with path.open("r+", encoding="utf-8") as fh:
            try:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            except Exception:
                pass
            try:
                fh.seek(0)
                raw = fh.read() or "{}"
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = {}
                n = max(0, int(data.get("count", 0))) + 1
                fh.seek(0)
                fh.truncate()
                json.dump({"count": n}, fh)
                fh.flush()
                os.fsync(fh.fileno())
                return n
            finally:
                try:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
    except Exception:
        return None


def is_page_view(request, response) -> bool:
    try:
        if request.method != "GET":
            return False
        if getattr(response, "status_code", 0) != 200:
            return False
        path = request.url.path or ""
        if any(path.startswith(p) for p in SKIP_PREFIXES):
            return False
        ct = (response.headers.get("content-type") or "").lower()
        if "text/html" not in ct:
            return False
        ua = (request.headers.get("user-agent") or "").lower()
        if any(m in ua for m in BOT_MARKERS):
            return False
        return True
    except Exception:
        return False
