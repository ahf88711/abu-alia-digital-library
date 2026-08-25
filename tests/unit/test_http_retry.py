import httpx

from abu_alia.net.http import RetryableHTTPError, request_with_retry


def test_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("abu_alia.net.http.time.sleep", lambda _s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    resp = request_with_retry(client, "GET", "https://example.test/x", attempts=5)
    assert resp.status_code == 200
    assert calls["n"] == 3


def test_exhausts_retries(monkeypatch):
    monkeypatch.setattr("abu_alia.net.http.time.sleep", lambda _s: None)
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        request_with_retry(client, "GET", "https://example.test/x", attempts=3)
        assert False, "should have raised"
    except RetryableHTTPError:
        pass
