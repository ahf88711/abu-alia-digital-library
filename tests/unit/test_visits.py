from abu_alia.web.visits import increment, is_page_view, read_count


class _Req:
    def __init__(self, method="GET", path="/", ua="Mozilla/5.0"):
        self.method = method
        self.url = type("U", (), {"path": path})()
        self.headers = {"user-agent": ua}


class _Resp:
    def __init__(self, status=200, content_type="text/html; charset=utf-8"):
        self.status_code = status
        self.headers = {"content-type": content_type}


def test_page_view_html_only():
    assert is_page_view(_Req(), _Resp()) is True
    assert is_page_view(_Req(path="/static/css/library.css"), _Resp(content_type="text/css")) is False
    assert is_page_view(_Req(path="/api/health"), _Resp(content_type="application/json")) is False
    assert is_page_view(_Req(path="/ملفات/x/epub"), _Resp()) is False
    assert is_page_view(_Req(ua="Googlebot"), _Resp()) is False
    assert is_page_view(_Req(method="POST"), _Resp()) is False


def test_increment_file(tmp_env):
    a = increment()
    b = increment()
    assert a == 1
    assert b == 2
    assert read_count() == 2
