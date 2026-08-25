from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from abu_alia.config import ROOT, get_settings

CHECKPOINT = ROOT / "data" / "harvest_checkpoint.json"
STATUS = ROOT / "PROJECT_STATUS.md"


def write_checkpoint(stats: Dict[str, Any], *, phase: str, note: str = "") -> None:
    settings = get_settings()
    settings.cache_root.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "phase": phase,
        "note": note,
        **stats,
    }
    CHECKPOINT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    STATUS.write_text(
        "\n".join(
            [
                "# PROJECT_STATUS",
                "",
                f"- **current phase:** {phase}",
                f"- **updated:** {payload['updated_at']}",
                f"- **published unique works:** {stats.get('published', 0)}",
                f"- **PDF files:** {stats.get('pdf', 0)}",
                f"- **EPUB files:** {stats.get('epub', 0)}",
                f"- **failed imports:** {stats.get('failed', 0)}",
                f"- **quarantined:** {stats.get('quarantined', 0)}",
                f"- **discovered source items:** {stats.get('discovered', 0)}",
                f"- **queued/retrying jobs:** {stats.get('queued_jobs', 0)}",
                f"- **harvest target:** {settings.harvest_target} (target, not to be fabricated)",
                f"- **note:** {note}",
                "- **architecture:** modular FastAPI monolith; OpenITI CC BY-NC-SA; IA untrusted PD marks quarantined",
                "- **GitHub:** https://github.com/ahf88711/abu-alia-digital-library",
                "- **deployment:** production public URL not claimed without hosting credentials",
                "- **next:** continue harvest; retry transient GitHub failures; do not duplicate or invent books",
                "",
            ]
        ),
        encoding="utf-8",
    )
