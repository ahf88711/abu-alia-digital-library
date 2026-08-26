def _csrf(client) -> str:
    r = client.get("/دخول")
    assert r.status_code == 200
    token = client.cookies.get("abu_alia_csrf")
    assert token
    return token


def test_home(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "مكتبة أبو علياء الرقمية" in r.text
    assert r.text.count("مكتبة أبو علياء الرقمية") >= 2
    assert "<em>الرقمية</em>" not in r.text
    assert "<h1>مكتبة أبو علياء الرقمية</h1>" in r.text
    assert 'dir="rtl"' in r.text
    assert "الزيارات:" in r.text
    assert "family=Amiri" in r.text or "Amiri" in r.text
    assert "book-card" not in r.text
    assert "jacket tone-" not in r.text
    assert r.text.count('type="search"') == 1
    assert "تواصل معنا" not in r.text
    assert "الحقوق والتراخيص" not in r.text
    assert 'href="/تواصل"' not in r.text
    assert 'href="/الحقوق"' not in r.text
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert "Permissions-Policy" in r.headers or r.headers.get("permissions-policy")


def test_empty_categories_hidden(client):
    r = client.get("/تصنيفات")
    assert r.status_code == 200
    assert "الفيزياء" not in r.text
    assert "الكيمياء" not in r.text


def test_health(client):
    r = client.get("/api/health")
    assert r.json()["ok"] is True
    r2 = client.get("/api/stats")
    assert r2.status_code == 200
    assert "published" in r2.json()


def test_static_pages(client):
    for path in (
        "/كتب",
        "/تصنيفات",
        "/مؤلفون",
        "/بحث",
        "/بحث-متقدم",
        "/مجموعات",
        "/مكتبتي",
        "/عن-المكتبة",
        "/الخصوصية",
        "/الشروط",
        "/دخول",
    ):
        r = client.get(path)
        assert r.status_code == 200, path
        assert 'dir="rtl"' in r.text


def test_admin_requires_auth(client):
    r = client.get("/إدارة")
    assert r.status_code in (401, 403)


def test_admin_login(client):
    token = _csrf(client)
    r = client.post(
        "/دخول",
        data={"البريد": "admin@test.local", "كلمة_السر": "test-admin-pass", "csrf_token": token},
        follow_redirects=False,
    )
    assert r.status_code == 303
    r2 = client.get("/إدارة")
    assert r2.status_code == 200
    assert "لوحة الإدارة" in r2.text


def test_login_csrf_required(client):
    r = client.post(
        "/دخول",
        data={"البريد": "admin@test.local", "كلمة_السر": "test-admin-pass"},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_sitemap(client):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    assert "urlset" in r.text or "sitemapindex" in r.text


def test_mobile_dock_present(client):
    r = client.get("/")
    assert 'class="dock"' in r.text
    assert "مكتبتي" in r.text


def test_retired_public_pages(client):
    from urllib.parse import unquote

    for path in ("/تواصل", "/الحقوق"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code in (301, 302, 303, 307, 308), path
        assert "عن-المكتبة" in unquote(r.headers.get("location") or "")


def test_layout_css_is_mobile_first(client):
    r = client.get("/static/css/library.css")
    assert r.status_code == 200
    css = r.text
    assert "repeat(2, minmax(0, 1fr))" in css
    assert "overflow-x: clip" in css
    assert ".jacket" in css
    assert "prefers-reduced-motion" in css
    assert "#722f28" not in css
    assert "#efe3ce" not in css
    assert "--hero:" in css
    assert '--display: "Amiri", "Noto Naskh Arabic", serif' in css
    assert '--body: "Noto Naskh Arabic", "Amiri", serif' in css
    assert '--kicker: "Aref Ruqaa", "Amiri", serif' in css
    assert "clamp(1.7rem, 6vw, 2.55rem)" in css
    assert "clamp(1.2rem, 3vw, 1.55rem)" in css
