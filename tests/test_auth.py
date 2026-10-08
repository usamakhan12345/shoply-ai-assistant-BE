from tests.conftest import CUSTOMER, login


def reg(client, **kw):
    body = {"email": "new@example.com", "password": "Password123", "full_name": "New User", "role": "customer", **kw}
    return client.post("/api/auth/register", json=body)


def test_register_customer(client):
    r = reg(client)
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "customer" and "access_token" in r.json()
    assert "password" not in r.text


def test_register_seller_requires_store_name(client):
    assert reg(client, role="seller").status_code == 422
    r = reg(client, role="seller", store_name="My Shop")
    assert r.status_code == 201 and r.json()["user"]["role"] == "seller"


def test_duplicate_email_rejected(client):
    assert reg(client).status_code == 201
    r = reg(client)
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"


def test_short_password_rejected(client):
    r = reg(client, password="short")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_login_ok_and_me(client):
    h = login(client, CUSTOMER)
    me = client.get("/api/auth/me", headers=h)
    assert me.status_code == 200 and me.json()["email"] == CUSTOMER[0]


def test_invalid_credentials(client):
    bad_pw = client.post("/api/auth/login", json={"email": CUSTOMER[0], "password": "nope-nope"})
    no_user = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "whatever1"})
    assert bad_pw.status_code == no_user.status_code == 401
    assert bad_pw.json() == no_user.json()  # no account enumeration


def test_protected_routes_need_token(client):
    for method, url in [("get", "/api/cart"), ("get", "/api/orders"), ("get", "/api/seller/orders"), ("get", "/api/auth/me")]:
        r = getattr(client, method)(url)
        assert r.status_code == 401, url
    assert client.get("/api/cart", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_customer_cannot_use_seller_api(client, customer):
    for method, url in [("get", "/api/seller/orders"), ("get", "/api/seller/products"), ("get", "/api/seller/stats")]:
        assert getattr(client, method)(url, headers=customer).status_code == 403, url
    assert client.post("/api/products", json={}, headers=customer).status_code == 403


def test_seller_cannot_use_customer_cart(client, seller):
    assert client.get("/api/cart", headers=seller).status_code == 403
    assert client.get("/api/orders", headers=seller).status_code == 403
