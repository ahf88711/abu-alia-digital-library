"""HTTP helpers with retry, timeout, and backoff. Network errors are data-plane failures, not silent drops."""
from __future__ import annotations

import random
import time
from typing import Iterable, Optional, Sequence

import httpx

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}
RETRY_EXC = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
    httpx.ReadError,
    ConnectionResetError,
    ConnectionError,
    TimeoutError,
)


class RetryableHTTPError(Exception):
    """Raised after retries are exhausted for a transient failure."""


class PermanentHTTPError(Exception):
    """Raised when every fallback URL is gone (404/410). Do not retry."""


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, PermanentHTTPError):
        return False
    if isinstance(exc, RetryableHTTPError):
        return True
    return isinstance(exc, RETRY_EXC)


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    attempts: int = 6,
    retry_statuses: Optional[Iterable[int]] = None,
    timeout: Optional[httpx.Timeout] = None,
    **kwargs,
) -> httpx.Response:
    statuses = set(retry_statuses or RETRY_STATUS)
    last_exc: Optional[BaseException] = None
    last_resp: Optional[httpx.Response] = None
    for i in range(max(1, attempts)):
        try:
            resp = client.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code in statuses:
                last_resp = resp
                last_exc = RetryableHTTPError(f"HTTP {resp.status_code} for {url}")
            else:
                return resp
        except RETRY_EXC as exc:
            last_exc = exc
        if i + 1 >= attempts:
            break
        delay = min(60.0, (2 ** i) + random.uniform(0, 0.4 * (2 ** i)))
        time.sleep(delay)
    if last_resp is not None and last_resp.status_code not in statuses:
        return last_resp
    raise RetryableHTTPError(str(last_exc) if last_exc else f"failed {method} {url}") from last_exc


def get_with_fallback(
    client: httpx.Client,
    urls: Sequence[str],
    *,
    attempts: int = 4,
    timeout: Optional[httpx.Timeout] = None,
) -> httpx.Response:
    last: Optional[BaseException] = None
    saw_transient = False
    for url in urls:
        try:
            resp = request_with_retry(client, "GET", url, attempts=attempts, timeout=timeout)
            if resp.status_code in (404, 410):
                last = PermanentHTTPError(f"{resp.status_code} {url}")
                continue
            resp.raise_for_status()
            return resp
        except RetryableHTTPError as exc:
            saw_transient = True
            last = exc
            continue
        except httpx.HTTPError as exc:
            last = exc
            continue
    if not saw_transient:
        raise PermanentHTTPError(f"permanent: all URLs missing: {list(urls)}") from last
    raise RetryableHTTPError(f"all URLs failed: {urls}") from last
