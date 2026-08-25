from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import BinaryIO, Iterator, Optional, Protocol, Tuple

from abu_alia.config import Settings, get_settings


class StorageBackend(Protocol):
    def put(self, key: str, src: Path) -> None: ...
    def exists(self, key: str) -> bool: ...
    def path_for(self, key: str) -> Path: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...
    def size(self, key: str) -> int: ...


def key_for_hash(sha256: str, ext: str) -> str:
    ext = ext.lstrip(".").lower()
    return f"{sha256[:2]}/{sha256[2:4]}/{sha256}.{ext}"


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            buf = fh.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _abs(self, key: str) -> Path:
        if ".." in key.split("/") or key.startswith("/"):
            raise ValueError("invalid storage key")
        return self.root / key

    def put(self, key: str, src: Path) -> None:
        dest = self._abs(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        shutil.copyfile(src, tmp)
        tmp.replace(dest)

    def exists(self, key: str) -> bool:
        return self._abs(key).is_file()

    def path_for(self, key: str) -> Path:
        return self._abs(key)

    def open(self, key: str) -> BinaryIO:
        return self._abs(key).open("rb")

    def delete(self, key: str) -> None:
        p = self._abs(key)
        if p.exists():
            p.unlink()

    def size(self, key: str) -> int:
        return self._abs(key).stat().st_size

    def usage_bytes(self) -> int:
        total = 0
        for p in self.root.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
        return total


def storage_from_settings(settings: Optional[Settings] = None) -> LocalStorage:
    settings = settings or get_settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.tmp_root.mkdir(parents=True, exist_ok=True)
    return LocalStorage(settings.storage_root)
