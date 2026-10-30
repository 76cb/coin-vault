from tests.conftest import PASSWORD, Api


def test_health_is_public(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_ready_needs_auth_and_reports_checks(client, api):
    anon = client.__class__(client.app)
    assert anon.get("/api/v1/health/ready").status_code == 401
    r = api.get("/api/v1/health/ready")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["checks"]["database"]["ok"] and body["checks"]["migrations"]["ok"] and body["checks"]["media"]["ok"]


def test_login_sets_httponly_cookie(client, make_user):
    make_user("admin")
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert r.json()["csrf_token"]


def test_wrong_password_and_unknown_user_same_error(client, make_user):
    make_user("admin")
    a = client.post("/api/v1/auth/login", json={"username": "admin", "password": "nope-nope-nope"})
    b = client.post("/api/v1/auth/login", json={"username": "ghost", "password": "nope-nope-nope"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_login_throttled_after_repeated_failures(client, make_user):
    make_user("admin")
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong-wrong"})
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 429


def test_unauthenticated_requests_rejected(client):
    assert client.get("/api/v1/items").status_code == 401
    assert client.post("/api/v1/items", json={"item_type": "coin", "title": "x"}).status_code == 401


def test_csrf_required_for_session_writes(api):
    r = api.c.post("/api/v1/items", json={"item_type": "coin", "title": "No CSRF"})
    assert r.status_code == 403
    r = api.c.post("/api/v1/items", json={"item_type": "coin", "title": "Bad"}, headers={"X-CSRF-Token": "forged"})
    assert r.status_code == 403
    assert api.post("/api/v1/items", json={"item_type": "coin", "title": "OK"}).status_code == 201


def test_me_and_logout(api):
    me = api.get("/api/v1/auth/me").json()
    assert me["user"]["username"] == "admin" and me["auth"] == "session"
    assert api.post("/api/v1/auth/logout").status_code == 204
    assert api.get("/api/v1/auth/me").status_code == 401


def test_password_change_signs_out_other_sessions(app, api):
    from fastapi.testclient import TestClient

    with TestClient(app) as other_client:
        other = Api(other_client)
        assert other.login().status_code == 200
        r = api.post("/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "a-brand-new-pass"})
        assert r.status_code == 204
        assert other.get("/api/v1/auth/me").status_code == 401
    assert api.get("/api/v1/auth/me").status_code == 200
    assert api.post("/api/v1/auth/password", json={"current_password": "wrong", "new_password": "another-long-one"}).status_code == 400
    assert api.post("/api/v1/auth/password", json={"current_password": "a-brand-new-pass", "new_password": "short"}).status_code == 422


def test_scoped_api_token(api, client):
    r = api.post("/api/v1/auth/tokens", json={"name": "reader", "scopes": ["items:read"]})
    assert r.status_code == 201
    token = r.json()["token"]
    assert token.startswith("cv_")
    listed = api.get("/api/v1/auth/tokens").json()
    assert listed[0]["prefix"] == r.json()["prefix"] and "token" not in listed[0]

    bearer = {"Authorization": f"Bearer {token}"}
    fresh = client.__class__(client.app)
    assert fresh.get("/api/v1/items", headers=bearer).status_code == 200
    # Token lacks items:write; no CSRF needed for bearer auth, so a 403 here is about scope.
    w = fresh.post("/api/v1/items", json={"item_type": "coin", "title": "x"}, headers=bearer)
    assert w.status_code == 403 and "scope" in w.json()["detail"]
    # Tokens cannot manage tokens.
    assert fresh.get("/api/v1/auth/tokens", headers=bearer).status_code == 403

    api.delete(f"/api/v1/auth/tokens/{r.json()['id']}")
    assert fresh.get("/api/v1/items", headers=bearer).status_code == 401
    assert fresh.get("/api/v1/items", headers={"Authorization": "Bearer cv_garbage"}).status_code == 401


def test_write_token_can_create_without_csrf(api, client):
    token = api.post("/api/v1/auth/tokens", json={"name": "w", "scopes": ["items:read", "items:write"]}).json()["token"]
    fresh = client.__class__(client.app)
    r = fresh.post("/api/v1/items", json={"item_type": "bar", "title": "Bar"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    audit = api.get(f"/api/v1/items/{r.json()['id']}/audit").json()
    assert audit and all(e["actor_type"] == "token" for e in audit)


def test_unknown_scope_rejected(api):
    assert api.post("/api/v1/auth/tokens", json={"name": "x", "scopes": ["admin:all"]}).status_code == 422
