from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def file_response_with_range(
    path: Path,
    request: Request,
    *,
    media_type: str,
    download_name: Optional[str] = None,
) -> Response:
    if not path.is_file():
        raise HTTPException(404)
    size = path.stat().st_size
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=3600",
    }
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(
            path,
            media_type=media_type,
            filename=download_name,
            headers=headers,
        )
    match = _RANGE.match(range_header.strip())
    if not match:
        raise HTTPException(416, headers={"Content-Range": f"bytes */{size}"})
    start_s, end_s = match.group(1), match.group(2)
    if start_s == "" and end_s == "":
        raise HTTPException(416, headers={"Content-Range": f"bytes */{size}"})
    if start_s == "":
        length = int(end_s)
        start = max(size - length, 0)
        end = size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s else size - 1
    if start >= size or start < 0 or end < start:
        raise HTTPException(416, headers={"Content-Range": f"bytes */{size}"})
    end = min(end, size - 1)
    length = end - start + 1
    with path.open("rb") as fh:
        fh.seek(start)
        chunk = fh.read(length)
    headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(length)
    if download_name:
        headers["Content-Disposition"] = f'attachment; filename="{download_name}"'
    return Response(content=chunk, status_code=206, media_type=media_type, headers=headers)
