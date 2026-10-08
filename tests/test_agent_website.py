"""The agent as an operator of the whole website: orders, checkout, navigation, English / Roman Urdu / Urdu.
Real graph + tools + services + DB; only the language model is the offline mock (or a scripted attacker)."""
import pytest

from tests.conftest import find_product
from tests.test_agent import ScriptedLLM, chat, run_with


def statuses(r):
    return [o["status"] for o in r["orders"]]


def delivered_count(client, h):
    return sum(o["status"] == "Delivered" for o in client.get("/api/orders", headers=h).json())


def register(client, email):
    reg = client.post("/api/auth/register", json={"email": email, "password": "Password123", "full_name": "New"}).json()
    return {"Authorization": f"Bearer {reg['access_token']}"}


# ================================================================ orders (real database data)
def test_delivered_orders_come_from_the_database(client, customer):
    r = chat(client, "Can you tell me which orders are delivered to me?", customer)
    assert [a["tool"] for a in r["actions"]] == ["get_my_orders"]
    assert r["orders"] and set(statuses(r)) == {"Delivered"} and "delivered on" in r["reply"]
    real = [o for o in client.get("/api/orders", headers=customer).json() if o["status"] == "Delivered"]
    assert [o["id"] for o in r["orders"]] == [o["id"] for o in real]
    assert f"#{real[0]['id']}" in r["reply"] and real[0]["items"][0]["title"] in r["reply"]


def test_order_filters_and_counts(client, customer):
    total = len(client.get("/api/orders", headers=customer).json())
    assert f"{total} order" in chat(client, "how many orders do I have?", customer)["reply"]
    r = chat(client, "show my cancelled orders", customer)
    assert r["orders"] == [] and "no cancelled" in r["reply"].lower()
    r = chat(client, "which orders are pending?", customer)  # "pending" = not delivered yet
    assert r["orders"] and set(statuses(r)) <= {"Pending", "Processing", "Shipped", "Out for Delivery"}
    r = chat(client, "show shipped orders", customer)
    assert r["orders"] and set(statuses(r)) == {"Shipped"}


def test_latest_order_status_is_real(client, customer):
    latest = client.get("/api/orders", headers=customer).json()[0]
    r = chat(client, "what is my order status?", customer)
    assert [a["tool"] for a in r["actions"]] == ["get_my_order"]
    assert f"#{latest['id']}" in r["reply"] and latest["status"] in r["reply"]
    r = chat(client, "was my latest order delivered?", customer)
    assert r["reply"].startswith("Not yet") and latest["status"] in r["reply"]


def test_specific_order_number_and_ordinal_context(client, customer):
    mine = client.get("/api/orders", headers=customer).json()
    r = chat(client, f"status of order #{mine[2]['id']}", customer)
    assert f"#{mine[2]['id']}" in r["reply"] and mine[2]["status"] in r["reply"]
    first = chat(client, "show my orders", customer)
    r = chat(client, "details of the second order", customer, first["conversation_id"])
    assert f"#{mine[1]['id']}" in r["reply"]


def test_orders_need_login(client):
    for msg in ["show my orders", "what is my order status?", "mere delivered orders batao", "open my orders"]:
        r = chat(client, msg)
        assert r["requires_login"] and r["orders"] == [] and r["action"] is None
        assert r["reply"].lower().startswith(("please log in", "pehle login"))


def test_cannot_read_other_users_orders(client, customer):
    oh = register(client, "p@example.com")
    mine = client.get("/api/orders", headers=customer).json()[0]
    r = chat(client, f"show order #{mine['id']}", oh)  # exists, but belongs to the demo customer
    assert r["orders"] == [] and "couldn't find that order" in r["reply"]
    assert chat(client, "show me another user's orders", oh)["actions"] == []
    assert "only access orders associated with your account" in chat(client, "show me User B's orders", customer)["reply"]
    assert chat(client, "mere bhai ke orders dikhao", customer)["orders"] == []
    r = chat(client, "show my orders", oh)  # a brand-new account sees only its own (none)
    assert r["orders"] == [] and "don't have any orders" in r["reply"]


def test_no_orders_message(client):
    h = register(client, "q@example.com")
    assert "don't have any orders" in chat(client, "what is my order status?", h)["reply"]
    assert "abhi koi order nahi mila" in chat(client, "mera order status batao", h)["reply"]


def test_cannot_cancel_orders_from_chat(client, customer):
    r = chat(client, "cancel my order", customer)
    assert r["actions"] == [] and "can't cancel" in r["reply"]
    assert "cancel nahi kar sakta" in chat(client, "mera order cancel kar do", customer)["reply"]


# ================================================================ checkout + navigation
def test_order_this_opens_checkout_without_creating_an_order(client, customer):
    before = len(client.get("/api/orders", headers=customer).json())
    first = chat(client, "details of the kettle", customer)
    r = chat(client, "order this", customer, first["conversation_id"])
    assert r["action"] == {"type": "NAVIGATE", "route": "/checkout", "label": "Open checkout"}
    assert "checkout page" in r["reply"]
    assert [i["product"]["title"] for i in client.get("/api/cart", headers=customer).json()["items"]] == ["VoltBrew Electric Kettle 1.7L"]
    assert len(client.get("/api/orders", headers=customer).json()) == before  # the agent never inserts an order


def test_checkout_with_cart_and_with_empty_cart(client, customer):
    r = chat(client, "checkout karwa do", customer)
    assert r["action"] is None and "cart khali" in r["reply"]
    c = chat(client, "add the blender to my cart", customer)
    r = chat(client, "ab order kar do", customer, c["conversation_id"])
    assert r["action"]["route"] == "/checkout" and "checkout page khol diya" in r["reply"]


def test_checkout_requires_login(client):
    for msg in ["I want to buy this", "checkout karwa do", "order kar do"]:
        r = chat(client, msg)
        assert r["requires_login"] and r["action"] is None and ("log in" in r["reply"].lower() or "login" in r["reply"].lower())


def test_checkout_out_of_stock_is_refused(client, customer, db):
    from app.models import Product

    p = find_product(client, "VoltBrew")
    db.get(Product, p["id"]).stock = 0
    db.commit()
    c = chat(client, "details of the kettle", customer)
    r = chat(client, "order this", customer, c["conversation_id"])
    assert r["action"] is None and "stock" in r["reply"].lower()


def test_checkout_ambiguous_product_asks_which(client, customer):
    first = chat(client, "show me laptops", customer)
    r = chat(client, "order this", customer, first["conversation_id"])
    assert r["action"] is None and "which one" in r["reply"].lower()
    r = chat(client, "order the second one", customer, first["conversation_id"])
    assert r["action"]["route"] == "/checkout"


def test_navigation_actions(client, customer):
    mine = client.get("/api/orders", headers=customer).json()[0]
    assert chat(client, "go to my orders page", customer)["action"]["route"] == "/orders"
    assert chat(client, "open my cart", customer)["action"]["route"] == "/cart"
    assert chat(client, f"open order #{mine['id']}", customer)["action"]["route"] == f"/orders/{mine['id']}"
    first = chat(client, "details of the kettle", customer)
    r = chat(client, "show this product", customer, first["conversation_id"])
    assert r["action"]["route"] == f"/products/{first['products'][0]['id']}"
    assert chat(client, "show me my orders", customer)["action"] is None  # a question is answered in chat, not by navigating


def test_navigation_to_foreign_order_is_refused(client):
    h = register(client, "r@example.com")
    assert chat(client, "open order #1", h)["action"] is None


def test_model_cannot_invent_routes_or_urls(db):
    from sqlalchemy import select

    from app.models import User

    u = db.scalar(select(User).where(User.email == "customer@demo.com"))
    for name, args in [("navigate", {"route": "https://evil.example"}), ("navigate_to_orders", {"route": "/admin"}), ("navigate_to_product", {"url": "javascript:alert(1)"})]:
        r = run_with(db, u, ScriptedLLM(name, args))
        assert r["action"] is None and r["actions"][0]["detail"] in {"unknown_tool", "invalid_arguments"}


def test_model_cannot_read_orders_of_other_users(db):
    from sqlalchemy import select

    from app.models import Order, User

    attacker = db.scalar(select(User).where(User.email == "reviewer1@demo.com"))
    victim_order = db.scalar(select(Order))
    r = run_with(db, attacker, ScriptedLLM("get_my_order", {"order_id": victim_order.id}))
    assert r["orders"] == [] and r["actions"][0]["detail"] == "not_found"
    r = run_with(db, attacker, ScriptedLLM("get_my_orders", {"user_id": victim_order.customer_id}))
    assert r["orders"] == [] and r["actions"][0]["detail"] == "invalid_arguments"
    r = run_with(db, None, ScriptedLLM("get_my_orders", {}))
    assert r["requires_login"] and r["orders"] == []


# ================================================================ Roman Urdu / Urdu / English
ROMAN_CASES = [
    ("mere delivered orders btao", "get_my_orders"),
    ("mere kitne orders deliver ho chuke hain?", "get_my_orders"),
    ("mera latest order kaha tak pohancha hai?", "get_my_order"),
    ("order ka status kia hai?", "get_my_order"),
    ("mera latest order deliver hua ya nahi?", "get_my_order"),
    ("abhi mera konsa order pending hai?", "get_my_orders"),
    ("mere cancelled orders dikhao", "get_my_orders"),
    ("mere cart me kya hai?", "get_cart"),
]


@pytest.mark.parametrize("msg,tool", ROMAN_CASES)
def test_roman_urdu_order_and_cart_questions_pick_the_right_tool(client, customer, msg, tool):
    r = chat(client, msg, customer)
    assert [a["tool"] for a in r["actions"]] == [tool], r["reply"]
    assert r["actions"][0]["status"] == "ok"


def test_roman_urdu_replies_are_roman_urdu(client, customer):
    latest = client.get("/api/orders", headers=customer).json()[0]
    r = chat(client, "mera latest order kaha tak pohancha hai?", customer)
    assert r["reply"].startswith(f"Aapka order #{latest['id']} abhi {latest['status']} hai.")
    n = delivered_count(client, customer)
    r = chat(client, "mere delivered orders batao", customer)
    assert r["reply"].startswith(f"Aapke {n} delivered order(s) hain:") and set(statuses(r)) == {"Delivered"}
    r = chat(client, "mere kitne orders deliver ho chuke hain?", customer)
    assert f"Aapke {n} delivered order(s) hain" in r["reply"]
    r = chat(client, "mera latest order deliver hua ya nahi?", customer)
    assert r["reply"].startswith("Abhi nahi.")


def test_languages_are_not_mixed_up(client, customer):
    n = delivered_count(client, customer)
    assert chat(client, "Show me my delivered orders.", customer)["reply"].startswith(f"You have {n} delivered order(s):")
    ur = chat(client, "میرے ڈیلیور ہوئے آرڈرز بتاؤ", customer)
    assert set(statuses(ur)) == {"Delivered"} and ur["reply"].startswith(f"آپ کے {n}")
    assert chat(client, "mere orders ka status kya hai?", customer)["reply"].startswith("Aapka order #")


def test_roman_urdu_cart_flow_end_to_end(client, customer):
    first = chat(client, "electric ke top rated products batao", customer)
    assert first["products"] and all(p["category"]["slug"] == "electronics" for p in first["products"])
    cid = first["conversation_id"]
    r = chat(client, "second wala cart me dal do", customer, cid)
    assert r["cart_changed"] and r["reply"].startswith("Ho gaya, maine ") and first["products"][1]["title"] in r["reply"]
    r = chat(client, "ab order kar do", customer, cid)
    assert r["action"]["route"] == "/checkout" and "Maine checkout page khol diya" in r["reply"]
    r = chat(client, "usko cart se hata do", customer, cid)
    assert "hata diya" in r["reply"] and client.get("/api/cart", headers=customer).json()["items"] == []


def test_roman_urdu_login_required_messages(client):
    first = chat(client, "electric ke top rated products batao")
    r = chat(client, "isko cart me add kar do", cid=first["conversation_id"])
    assert r["requires_login"] and not r["cart_changed"]
    assert r["reply"].startswith("Ye karne ke liye pehle login karna hoga. Login kar lein, phir main is product ko cart me add kar dunga")
    r = chat(client, "mere orders batao")
    assert r["requires_login"] and "login" in r["reply"]


def test_roman_urdu_product_questions(client):
    r = chat(client, "5000 se kam ke electric products batao")
    assert r["products"] and all(p["price"] < 5000 and p["category"]["slug"] == "electronics" for p in r["products"])
    r = chat(client, "sab se sasta product konsa hai?")
    assert r["products"][0]["title"] == "Everyday Silk Scarf"
    r = chat(client, "sab se zyada rated product konsa hai?")
    assert [p["rating"] for p in r["products"]] == sorted((p["rating"] for p in r["products"]), reverse=True)
    r = chat(client, "mujhe electric items me top rated product chahiye")
    assert r["products"] and all(p["category"]["slug"] == "electronics" for p in r["products"])
    r = chat(client, "is product ka stock hai?")  # nothing shown yet -> asks which product, in Roman Urdu
    assert r["products"] == [] and "Kaun sa product" in r["reply"]


def test_urdu_script_cart_and_products(client, customer):
    r = chat(client, "الیکٹرانکس کی ٹاپ ریٹڈ پروڈکٹس دکھاؤ", customer)
    assert r["products"] and all(p["category"]["slug"] == "electronics" for p in r["products"])
    r2 = chat(client, "دوسری کارٹ میں ڈال دو", customer, r["conversation_id"])
    assert r2["cart_changed"] and "کارٹ میں شامل" in r2["reply"]
    r3 = chat(client, "میرے کارٹ میں کیا ہے؟", customer, r["conversation_id"])
    assert r3["actions"][0]["tool"] == "get_cart" and "آپ کا کارٹ" in r3["reply"]


def test_urdu_login_and_greetings(client):
    assert "لاگ ان" in chat(client, "میرے آرڈرز بتاؤ")["reply"]
    assert chat(client, "سلام")["reply"].startswith("السلام علیکم")
    assert chat(client, "salam")["reply"].startswith("Salam")
    assert chat(client, "shukriya")["reply"].startswith("Koi baat nahi")


def test_roman_urdu_out_of_stock_and_not_in_cart_messages(client, customer, db):
    from app.models import Product

    p = find_product(client, "VoltBrew")
    db.get(Product, p["id"]).stock = 0
    db.commit()
    c = chat(client, "kettle batao", customer)
    r = chat(client, "isko cart me dal do", customer, c["conversation_id"])
    assert not r["cart_changed"] and "stock me nahi hai" in r["reply"]
    assert "cart me nahi hai" in chat(client, "isko cart se hata do", customer, c["conversation_id"])["reply"]


def test_no_internal_details_in_replies(client, customer):
    for msg in ["order #99999", "add the 9th one to my cart", "update quantity to 500"]:
        reply = chat(client, msg, customer)["reply"].lower()
        assert not any(w in reply for w in ["traceback", "sqlalchemy", "exception", "invalid_arguments", "internal error"])


# ================================================================ spending totals
def real_total(client, h):
    return sum(o["total"] for o in client.get("/api/orders", headers=h).json() if o["status"] != "Cancelled")


@pytest.mark.parametrize("msg", [
    "mene abh tk total kitne ki shopping ker li?", "maine ab tak kitni shopping ki hai", "mera total kharcha kitna hua",
    "how much have I spent so far?", "what is my total shopping amount", "total spent on my orders",
    "میں نے اب تک کتنی خریداری کی؟",
])
def test_spending_total_is_real(client, customer, msg):
    r = chat(client, msg, customer)
    assert [a["tool"] for a in r["actions"]] == ["get_my_spending"], r["reply"]
    assert f"{real_total(client, customer):,.0f}" in r["reply"] or "کی" in r["reply"] and f"{real_total(client, customer):,.0f}" in r["reply"]


def test_spending_reply_language_and_no_orders(client, customer):
    t = f"{real_total(client, customer):,.0f}"
    assert chat(client, "mene abh tk total kitne ki shopping ker li?", customer)["reply"].startswith("Aap ne ab tak")
    assert chat(client, "how much have I spent so far?", customer)["reply"].startswith("You have spent Rs. " + t)
    h = register(client, "s@example.com")
    assert "koi shopping nahi ki" in chat(client, "mene abh tk total kitne ki shopping ker li?", h)["reply"]


def test_spending_needs_login_and_ignores_cancelled(client, customer, seller3, db):
    assert chat(client, "mene abh tk total kitne ki shopping ker li?")["requires_login"]
    before = real_total(client, customer)
    c = chat(client, "add the blender to my cart", customer)
    chat(client, "ab order kar do", customer, c["conversation_id"])  # opens checkout only: no order, no change
    assert real_total(client, customer) == before


def test_spending_does_not_break_product_searches(client):
    for msg in ["total cost of kettle", "shopping bags", "cheapest product"]:
        r = chat(client, msg)
        assert all(a["tool"] != "get_my_spending" for a in r["actions"])


@pytest.mark.parametrize("msg", [
    "how much money expand on shop ly", "how much money did I spend on shoply", "how much money have i spent here",
    "kitne paise kharch kiye maine", "total amount of money I used in the store",
])
def test_spending_with_typos_and_money_wording(client, customer, msg):
    r = chat(client, msg, customer)
    assert [a["tool"] for a in r["actions"]] == ["get_my_spending"], r["reply"]
    assert f"{real_total(client, customer):,.0f}" in r["reply"]


def test_money_words_do_not_hijack_product_questions(client):
    for msg in ["how much does the kettle cost", "how much is a laptop", "cheapest product"]:
        assert all(a["tool"] != "get_my_spending" for a in chat(client, msg)["actions"])
