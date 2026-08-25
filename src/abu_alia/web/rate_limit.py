from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request


_buckets: Dict[str, Deque[float]] = defaultdict(deque)


def limit(request: Request, key: str, max_events: int, window: float = 60.0) -> None:
    ip = request.client.host if request.client else "unknown"
    bucket_key = f"{key}:{ip}"
    now = time.monotonic()
    q = _buckets[bucket_key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= max_events:
        raise HTTPException(status_code=429, detail="محاولات كثيرة، حاول لاحقاً")
    q.append(now)
