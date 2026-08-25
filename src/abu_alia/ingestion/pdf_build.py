from __future__ import annotations

from pathlib import Path


def build_minimal_pdf(dest: Path, title: str, body: str) -> Path:
    """Tiny valid PDF. Arabic may not render in the payload (Type1), used for tests/fixtures."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    safe_title = title.encode("latin-1", "replace").decode("latin-1")
    stream = f"BT /F1 12 Tf 72 720 Td ({safe_title}) Tj ET".encode("latin-1", "replace")
    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objects.append(
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
    )
    objects.append(
        b"4 0 obj << /Length " + str(len(stream)).encode() + b" >> stream\n" + stream + b"\nendstream endobj\n"
    )
    objects.append(b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    body_bytes = b"".join(objects)
    offsets = []
    cursor = len(header)
    parts = [header]
    for obj in objects:
        offsets.append(cursor)
        parts.append(obj)
        cursor += len(obj)
    xref_pos = cursor
    xref = [b"xref\n0 6\n0000000000 65535 f \n"]
    for off in offsets:
        xref.append(f"{off:010d} 00000 n \n".encode("ascii"))
    trailer = (
        b"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n" + str(xref_pos).encode() + b"\n%%EOF\n"
    )
    dest.write_bytes(b"".join(parts) + b"".join(xref) + trailer)
    return dest
