from tests.conftest import ADDRESS, find_product


def add(client, h, pid, qty=1):
    return client.post("/api/cart/items", json={"product_id": pid, "quantity": qty}, headers=h)


# ---------------------------------------------------------------- cart
def test_cart_add_update_remove(client, customer):
    p = find_product(client, "VoltBrew")
    r = add(client, customer, p["id"], 2)
    assert r.status_code == 201 and r.json()["item_count"] == 2
    assert add(client, customer, p["id"], 1).json()["items"][0]["quantity"] == 3  # merges, no duplicate line
    item_id = r.json()["items"][0]["id"]
    up = client.put(f"/api/cart/items/{item_id}", json={"quantity": 1}, headers=customer).json()
    assert up["items"][0]["quantity"] == 1 and up["subtotal"] == p["price"]
    gone = client.delete(f"/api/cart/items/{item_id}", headers=customer).json()
    assert gone["items"] == [] and gone["total"] == 0


def test_cart_stock_validation(client, customer):
    p = find_product(client, "Pixel-Pro")  # stock 12
    r = add(client, customer, p["id"], 13)
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_stock"
    assert add(client, customer, p["id"], 12).status_code == 201
    assert add(client, customer, p["id"], 1).status_code == 409  # 12 + 1 > stock
    item_id = client.get("/api/cart", headers=customer).json()["items"][0]["id"]
    assert client.put(f"/api/cart/items/{item_id}", json={"quantity": 50}, headers=customer).status_code == 409


def test_cart_unknown_product_and_bad_quantity(client, customer):
    assert add(client, customer, 999999).status_code == 404
    assert client.post("/api/cart/items", json={"product_id": 1, "quantity": 0}, headers=customer).status_code == 422


def test_cannot_touch_other_users_cart_item(client, customer):
    from tests.conftest import login

    other = client.post("/api/auth/register", json={"email": "o@example.com", "password": "Password123", "full_name": "O"}).json()
    oh = {"Authorization": f"Bearer {other['access_token']}"}
    p = find_product(client, "VoltBrew")
    item_id = add(client, customer, p["id"]).json()["items"][0]["id"]
    assert client.put(f"/api/cart/items/{item_id}", json={"quantity": 2}, headers=oh).status_code == 404
    assert client.delete(f"/api/cart/items/{item_id}", headers=oh).status_code == 404


# ---------------------------------------------------------------- checkout
def test_checkout_creates_order_and_updates_inventory(client, customer):
    p = find_product(client, "VoltBrew")  # 5999, stock 80, free shipping threshold is 5000 -> free
    stock = client.get(f"/api/products/{p['id']}").json()["stock"]
    add(client, customer, p["id"], 2)
    r = client.post("/api/orders", json={"address": ADDRESS}, headers=customer)
    assert r.status_code == 201
    o = r.json()[0]
    assert o["status"] == "Pending" and o["total"] == p["price"] * 2 and o["items"][0]["quantity"] == 2
    assert o["shipping_city"] == "Lahore" and o["history"][0]["status"] == "Pending"
    after = client.get(f"/api/products/{p['id']}").json()
    assert after["stock"] == stock - 2 and after["sales_count"] >= 2
    assert client.get("/api/cart", headers=customer).json()["items"] == []  # cart emptied


def test_checkout_ignores_client_prices(client, customer):
    p = find_product(client, "VoltBrew")
    add(client, customer, p["id"], 1)
    r = client.post("/api/orders", json={"address": ADDRESS, "total": 1, "items": [{"price": 1}]}, headers=customer)
    assert r.json()[0]["total"] == p["price"]


def test_checkout_empty_cart(client, customer):
    r = client.post("/api/orders", json={"address": ADDRESS}, headers=customer)
    assert r.status_code == 400 and r.json()["error"]["code"] == "empty_cart"


def test_checkout_splits_by_seller(client, customer):
    a, b = find_product(client, "Aurora"), find_product(client, "VoltBrew")  # different sellers
    add(client, customer, a["id"]), add(client, customer, b["id"])
    orders = client.post("/api/orders", json={"address": ADDRESS}, headers=customer).json()
    assert len(orders) == 2 and len({o["checkout_ref"] for o in orders}) == 1
    assert len({o["seller_store"] for o in orders}) == 2


def test_checkout_fails_atomically_when_stock_vanishes(client, customer, db):
    from app.models import Product

    a, b = find_product(client, "VoltBrew"), find_product(client, "Aurora")
    add(client, customer, a["id"], 2), add(client, customer, b["id"], 2)
    db.get(Product, b["id"]).stock = 1  # someone else bought it meanwhile
    db.commit()
    r = client.post("/api/orders", json={"address": ADDRESS}, headers=customer)
    assert r.status_code == 409
    assert client.get(f"/api/products/{a['id']}").json()["stock"] == a["stock"]  # first item's stock NOT lost
    assert len(client.get("/api/cart", headers=customer).json()["items"]) == 2  # cart kept


def test_customer_orders_visibility(client, customer):
    orders = client.get("/api/orders", headers=customer).json()
    assert len(orders) >= 4  # seeded demo orders
    one = client.get(f"/api/orders/{orders[0]['id']}", headers=customer)
    assert one.status_code == 200
    other = client.post("/api/auth/register", json={"email": "o2@example.com", "password": "Password123", "full_name": "O"}).json()
    oh = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get(f"/api/orders/{orders[0]['id']}", headers=oh).status_code == 404
    assert client.get("/api/orders", headers=oh).json() == []


# ---------------------------------------------------------------- seller order management
def place_one(client, customer, title="VoltBrew"):
    add(client, customer, find_product(client, title)["id"])
    return client.post("/api/orders", json={"address": ADDRESS}, headers=customer).json()[0]


def set_status(client, h, oid, status):
    return client.patch(f"/api/seller/orders/{oid}/status", json={"status": status}, headers=h)


def test_seller_sees_only_own_orders(client, seller, seller2):
    mine = client.get("/api/seller/orders", headers=seller).json()
    theirs = client.get("/api/seller/orders", headers=seller2).json()
    assert mine and {o["id"] for o in mine}.isdisjoint({o["id"] for o in theirs})
    assert client.get(f"/api/seller/orders/{theirs[0]['id']}", headers=seller).status_code == 403


def test_full_status_lifecycle_visible_to_customer(client, customer, seller3):
    o = place_one(client, customer)
    h = seller3
    for st in ["Processing", "Shipped", "Out for Delivery", "Delivered"]:
        r = set_status(client, h, o["id"], st)
        assert r.status_code == 200 and r.json()["status"] == st
    mine = client.get(f"/api/orders/{o['id']}", headers=customer).json()
    assert mine["status"] == "Delivered" and [e["status"] for e in mine["history"]] == ["Pending", "Processing", "Shipped", "Out for Delivery", "Delivered"]


def test_invalid_status_transitions(client, customer, seller3):
    o = place_one(client, customer)
    r = set_status(client, seller3, o["id"], "Delivered")  # skipping steps
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_status_transition"
    set_status(client, seller3, o["id"], "Processing")
    assert set_status(client, seller3, o["id"], "Pending").status_code == 409  # no going backwards


def test_cancel_restores_stock_and_is_final(client, customer, seller3):
    p = find_product(client, "VoltBrew")
    o = place_one(client, customer)
    assert client.get(f"/api/products/{p['id']}").json()["stock"] == p["stock"] - 1
    assert set_status(client, seller3, o["id"], "Cancelled").status_code == 200
    assert client.get(f"/api/products/{p['id']}").json()["stock"] == p["stock"]
    assert set_status(client, seller3, o["id"], "Processing").status_code == 409


def test_seller_cannot_update_other_sellers_order(client, customer, seller):
    o = place_one(client, customer)  # belongs to seller3
    assert set_status(client, seller, o["id"], "Processing").status_code == 403


def test_customer_cannot_change_status(client, customer):
    o = place_one(client, customer)
    assert set_status(client, customer, o["id"], "Delivered").status_code == 403


def test_review_only_after_delivery(client, customer):
    p = find_product(client, "Studio Pods")  # seeded delivered order for this product
    r = client.post(f"/api/products/{p['id']}/reviews", json={"rating": 5, "comment": "ok"}, headers=customer)
    assert r.status_code == 201
    assert client.post(f"/api/products/{p['id']}/reviews", json={"rating": 5}, headers=customer).status_code == 409
    other = find_product(client, "ZenBook")  # only Processing
    assert client.post(f"/api/products/{other['id']}/reviews", json={"rating": 5}, headers=customer).status_code == 403
