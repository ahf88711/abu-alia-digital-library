from __future__ import annotations

import bleach


def plain_text(value: object) -> str:
    if value is None:
        return ""
    return bleach.clean(str(value), tags=[], attributes={}, strip=True)
