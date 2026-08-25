from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from abu_alia.storage.serve import file_response_with_range
from abu_alia.web.sanitize import plain_text


def test_range_206(tmp_path):
    path = Path(tmp_path) / "book.bin"
    path.write_bytes(b"ABCDEFGHIJ")
    app = FastAPI()

    @app.get("/f")
    def serve(request: Request):
        return file_response_with_range(path, request, media_type="application/octet-stream")

    client = TestClient(app)
    full = client.get("/f")
    assert full.status_code == 200
    assert full.headers.get("accept-ranges") == "bytes"
    part = client.get("/f", headers={"Range": "bytes=2-5"})
    assert part.status_code == 206
    assert part.content == b"CDEF"
    assert part.headers["content-range"] == "bytes 2-5/10"


def test_plain_strips_tags():
    assert "<" not in plain_text('<script>alert(1)</script>عنوان')
    assert "عنوان" in plain_text('<b>عنوان</b>')
