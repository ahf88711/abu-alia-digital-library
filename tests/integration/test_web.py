def test_home(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "مكتبة أبو علياء" in r.text
    assert 'dir="rtl"' in r.text
    assert "التصنيفات" in r.text


def test_health(client):
    r = client.get("/api/health")
    assert r.json()["ok"] is True


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
        "/تواصل",
        "/الحقوق",
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
    r = client.post(
        "/دخول",
        data={"البريد": "admin@test.local", "كلمة_السر": "test-admin-pass"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    r2 = client.get("/إدارة")
    assert r2.status_code == 200
    assert "لوحة الإدارة" in r2.text


def test_bottom_nav_present(client):
    r = client.get("/")
    assert "bottom-nav" in r.text
    assert "مكتبتي" in r.text
