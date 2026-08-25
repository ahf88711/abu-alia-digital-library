from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Dict, List

from abu_alia.storage.validate import FileValidationError, validate_book_file


def sample_storage(root: Path, limit: int = 40) -> Dict[str, object]:
    root = Path(root)
    files: List[Path] = []
    if root.exists():
        files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".epub", ".pdf"}]
    files.sort()
    sample = files[: max(limit, 0)]
    ok = 0
    failed: List[str] = []
    hashes: List[str] = []
    for path in sample:
        try:
            validate_book_file(path, expected=path.suffix.lower().lstrip("."))
            ok += 1
            from abu_alia.storage.backend import sha256_file

            hashes.append(sha256_file(path))
        except FileValidationError as exc:
            failed.append(f"{path.name}: {exc.message}")
    counts = Counter(hashes)
    collisions = sum(1 for n in counts.values() if n > 1)
    return {
        "total_book_files": len(files),
        "sampled": len(sample),
        "valid": ok,
        "invalid": len(failed),
        "failures": failed[:20],
        "sha256_collisions_in_sample": collisions,
    }
