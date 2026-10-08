from tests.conftest import find_product


def new_product(client, headers, **kw):
    cats = client.get("/api/categories").json()
    elec = next(c for c in cats if c["slug"] == "electronics")
    body = {"title": "Test Gadget", "description": "d", "category_id": elec["id"], "subcategory_id": elec["children"][0]["id"], "price": 100, "original_price": 150, "stock": 5, **kw}
    return client.post("/api/products", json=body, headers=headers)


def test_listing_pagination(client):
    r = client.get("/api/products", params={"page_size": 5}).json()
    assert len(r["items"]) == 5 and r["total"] >= 30 and r["pages"] >= 6
    p2 = client.get("/api/products", params={"page_size": 5, "page": 2}).json()
    assert {i["id"] for i in r["items"]}.isdisjoint({i["id"] for i in p2["items"]})


def test_search(client):
    r = client.get("/api/products", params={"q": "kettle"}).json()
    assert r["total"] == 1 and "Kettle" in r["items"][0]["title"]


def test_filter_category_includes_subcategories(client):
    top = client.get("/api/products", params={"category": "electronics", "page_size": 60}).json()
    sub = client.get("/api/products", params={"category": "laptops"}).json()
    assert 0 < sub["total"] < top["total"]
    assert all(i["category"]["slug"] == "electronics" for i in top["items"])


def test_filter_price_and_sort(client):
    r = client.get("/api/products", params={"min_price": 5000, "max_price": 10000, "sort": "price_asc", "page_size": 60}).json()
    prices = [i["price"] for i in r["items"]]
    assert prices and all(5000 <= p <= 10000 for p in prices) and prices == sorted(prices)


def test_sort_by_rating(client):
    r = client.get("/api/products", params={"sort": "rating", "page_size": 10}).json()
    ratings = [i["rating"] for i in r["items"]]
    assert ratings == sorted(ratings, reverse=True)


def test_product_detail_and_404(client):
    p = find_product(client, "Aurora")
    d = client.get(f"/api/products/{p['id']}").json()
    assert d["colors"] == ["Black", "Blue"] and d["specs"] and d["seller"]["store_name"] == "TechNest"
    assert d["discount"] == 13
    assert client.get("/api/products/999999").status_code == 404


def test_seller_creates_product(client, seller):
    r = new_product(client, seller, colors=["Red"], specs=[{"name": "Power", "value": "10W"}])
    assert r.status_code == 201
    d = r.json()
    assert d["seller"]["store_name"] == "TechNest" and d["discount"] == 33 and d["rating"] == 0 and d["colors"] == ["Red"]


def test_client_cannot_set_seller_or_rating(client, seller):
    r = new_product(client, seller, seller_id=999, rating=5, sales_count=500)
    assert r.status_code == 201  # unknown fields are ignored...
    d = r.json()
    assert d["seller"]["id"] != 999 and d["rating"] == 0 and d["sales_count"] == 0  # ...and never applied


def test_invalid_product_payloads(client, seller):
    assert new_product(client, seller, price=-5).status_code == 422
    assert new_product(client, seller, price=100, original_price=50).status_code == 422
    assert new_product(client, seller, category_id=9999).status_code == 400


def test_seller_updates_own_product(client, seller):
    pid = new_product(client, seller).json()["id"]
    r = client.put(f"/api/products/{pid}", json={"price": 90, "stock": 9, "colors": ["Blue", "Green"]}, headers=seller)
    assert r.status_code == 200 and r.json()["price"] == 90 and r.json()["stock"] == 9 and r.json()["colors"] == ["Blue", "Green"]


def test_ownership_enforced_on_update_and_delete(client, seller, seller2):
    pid = new_product(client, seller).json()["id"]
    assert client.put(f"/api/products/{pid}", json={"price": 1}, headers=seller2).status_code == 403
    assert client.delete(f"/api/products/{pid}", headers=seller2).status_code == 403
    assert client.get(f"/api/products/{pid}").json()["price"] == 100  # untouched
    assert client.delete(f"/api/products/{pid}", headers=seller).status_code == 204
    assert client.get(f"/api/products/{pid}").status_code == 404


def test_seller_products_list_only_own(client, seller):
    r = client.get("/api/seller/products", params={"page_size": 100}, headers=seller).json()
    assert r["total"] > 0
    ids = {i["id"] for i in r["items"]}
    other = find_product(client, "VoltBrew")  # belongs to seller3
    assert other["id"] not in ids


def test_image_upload(client, seller, customer):
    files = {"file": ("x.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20, "image/png")}
    r = client.post("/api/seller/uploads", files=files, headers=seller)
    assert r.status_code == 201 and r.json()["url"].startswith("/uploads/")
    assert client.get(r.json()["url"]).status_code == 200
    bad = client.post("/api/seller/uploads", files={"file": ("x.exe", b"MZ", "application/octet-stream")}, headers=seller)
    assert bad.status_code == 400
    assert client.post("/api/seller/uploads", files=files, headers=customer).status_code == 403
