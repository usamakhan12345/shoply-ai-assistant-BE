"""Demo data. Run:  python -m app.db.seed        (add --reset to wipe the DB first)

Demo accounts (local development ONLY - these are public, throwaway credentials):
    customer@demo.com / Customer123!      seller@demo.com / Seller123!
    seller2@demo.com  / Seller123!        seller3@demo.com / Seller123!
"""
import random
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import Base, SessionLocal, engine
from app.models import Category, OrderStatus, Role, User
from app.models.catalog import Review
from app.schemas.cart_order import AddressIn
from app.schemas.product import ProductIn, SpecIn
from app.services import cart_service, order_service, product_service, review_service

CATEGORIES = {
    "Electronics": ["Mobile Phones", "Laptops", "Audio", "Kitchen Appliances"],
    "Fashion": ["Men's Clothing", "Women's Clothing", "Footwear"],
    "Home & Living": ["Furniture", "Home Decor"],
    "Beauty & Health": ["Skincare", "Fitness"],
    "Sports & Outdoors": ["Cycling", "Camping"],
}


def slug(s: str) -> str:
    return s.lower().replace("&", "").replace("'", "").replace("  ", " ").strip().replace(" ", "-")


# (title, category, subcategory, price, original_price, stock, target_rating, seller 0-2, location, colors, sizes, specs, description)
P = [
    ("Aurora X5 Smartphone 128GB", "Electronics", "Mobile Phones", 69999, 79999, 40, 4.6, 0, "Lahore", ["Black", "Blue"], [], {"RAM": "8 GB", "Storage": "128 GB", "Battery": "5000 mAh"}, "6.6-inch AMOLED display, 50MP camera and all-day battery."),
    ("Nova Lite 5G Phone", "Electronics", "Mobile Phones", 42999, 47999, 65, 4.2, 0, "Lahore", ["Silver", "Green"], [], {"RAM": "6 GB", "Storage": "128 GB"}, "Affordable 5G phone with a smooth 90Hz screen."),
    ("Pixel-Pro Max Flagship", "Electronics", "Mobile Phones", 189999, 199999, 12, 4.8, 1, "Karachi", ["Graphite"], [], {"RAM": "12 GB", "Storage": "256 GB"}, "Flagship camera system and 120Hz LTPO display."),
    ("ZenBook Air 14 Laptop", "Electronics", "Laptops", 164999, 179999, 18, 4.7, 1, "Karachi", ["Silver"], [], {"CPU": "Core i7", "RAM": "16 GB", "SSD": "512 GB"}, "Ultra-light 14-inch laptop with a 12-hour battery."),
    ("WorkMate 15 Business Laptop", "Electronics", "Laptops", 109999, None, 25, 4.1, 1, "Karachi", ["Grey"], [], {"CPU": "Core i5", "RAM": "8 GB", "SSD": "512 GB"}, "Reliable office laptop with a full-size keyboard."),
    ("Studio Pods Wireless Earbuds", "Electronics", "Audio", 8999, 12999, 150, 4.5, 0, "Lahore", ["White", "Black"], [], {"Battery": "24 h with case", "Noise cancelling": "Yes"}, "Active noise cancelling earbuds with a wireless charging case."),
    ("BassBoom Bluetooth Speaker", "Electronics", "Audio", 6499, 7999, 90, 4.3, 2, "Islamabad", ["Red", "Black", "Blue"], [], {"Playtime": "20 h", "Waterproof": "IP67"}, "Portable waterproof speaker with deep bass."),
    ("SoundArc Over-Ear Headphones", "Electronics", "Audio", 15999, 19999, 45, 4.6, 0, "Lahore", ["Black"], [], {"Battery": "40 h", "Noise cancelling": "Yes"}, "Studio-quality sound with 40-hour battery."),
    ("VoltBrew Electric Kettle 1.7L", "Electronics", "Kitchen Appliances", 5999, 7499, 80, 4.8, 2, "Islamabad", ["Steel"], [], {"Capacity": "1.7 L", "Power": "2200 W"}, "Fast-boil stainless steel electric kettle with auto shut-off."),
    ("PowerBlend Pro Blender", "Electronics", "Kitchen Appliances", 7499, 8999, 55, 4.7, 2, "Islamabad", ["Black"], [], {"Power": "1000 W", "Jar": "1.5 L"}, "High-speed blender for smoothies and soups."),
    ("AirCrisp Digital Air Fryer 5L", "Electronics", "Kitchen Appliances", 18999, 23999, 35, 4.6, 2, "Islamabad", ["Black"], [], {"Capacity": "5 L", "Power": "1700 W"}, "Cook crispy food with up to 90% less oil."),
    ("ToastPlus 2-Slice Toaster", "Electronics", "Kitchen Appliances", 3499, None, 70, 4.0, 2, "Islamabad", ["Cream"], [], {"Slots": "2", "Power": "800 W"}, "Compact toaster with 6 browning levels."),
    ("Classic Cotton Polo Shirt", "Fashion", "Men's Clothing", 1999, 2999, 200, 4.2, 0, "Faisalabad", ["Navy", "White", "Olive"], ["S", "M", "L", "XL"], {"Material": "100% cotton"}, "Soft pique cotton polo for everyday wear."),
    ("Slim Fit Denim Jeans", "Fashion", "Men's Clothing", 3999, 5499, 120, 4.4, 0, "Faisalabad", ["Indigo", "Black"], ["30", "32", "34", "36"], {"Material": "Stretch denim"}, "Comfortable stretch denim with a modern slim fit."),
    ("Embroidered Lawn Kurta", "Fashion", "Women's Clothing", 4499, 5999, 90, 4.5, 0, "Faisalabad", ["Pink", "Mint"], ["S", "M", "L"], {"Fabric": "Premium lawn"}, "Hand-finished embroidery on breathable lawn fabric."),
    ("Everyday Silk Scarf", "Fashion", "Women's Clothing", 1499, None, 140, 3.9, 0, "Faisalabad", ["Maroon", "Teal"], [], {"Material": "Silk blend"}, "Lightweight silk-blend scarf."),
    ("RunFlex Training Sneakers", "Fashion", "Footwear", 7999, 9999, 100, 4.6, 2, "Islamabad", ["Black", "White"], ["40", "41", "42", "43", "44"], {"Sole": "EVA foam"}, "Cushioned sneakers built for daily runs."),
    ("Leather Chelsea Boots", "Fashion", "Footwear", 11999, 14999, 40, 4.4, 1, "Karachi", ["Brown", "Black"], ["40", "41", "42", "43"], {"Material": "Genuine leather"}, "Handcrafted leather boots that age beautifully."),
    ("Oslo 3-Seater Fabric Sofa", "Home & Living", "Furniture", 74999, 89999, 8, 4.5, 1, "Karachi", ["Grey", "Beige"], [], {"Seats": "3", "Frame": "Solid wood"}, "Scandinavian-style sofa with high-density foam."),
    ("Ergo Office Chair", "Home & Living", "Furniture", 21999, 27999, 30, 4.3, 1, "Karachi", ["Black"], [], {"Back": "Mesh", "Lumbar support": "Adjustable"}, "Ergonomic chair with adjustable lumbar support."),
    ("Handwoven Jute Rug 5x7", "Home & Living", "Home Decor", 9999, 12999, 22, 4.1, 2, "Islamabad", ["Natural"], [], {"Size": "5 x 7 ft"}, "Natural jute rug that adds warmth to any room."),
    ("Ceramic Table Lamp", "Home & Living", "Home Decor", 3299, 3999, 60, 4.2, 2, "Islamabad", ["White", "Sage"], [], {"Bulb": "E27 (not included)"}, "Soft diffused light with a hand-glazed ceramic base."),
    ("Vitamin C Glow Serum 30ml", "Beauty & Health", "Skincare", 1899, 2499, 220, 4.7, 0, "Lahore", [], [], {"Volume": "30 ml"}, "Brightening serum with 15% vitamin C."),
    ("Hydra Daily Moisturizer SPF30", "Beauty & Health", "Skincare", 1599, None, 180, 4.4, 0, "Lahore", [], [], {"SPF": "30"}, "Lightweight moisturizer with sun protection."),
    ("Adjustable Dumbbell Set 20kg", "Beauty & Health", "Fitness", 12999, 15999, 25, 4.6, 2, "Islamabad", ["Black"], [], {"Weight": "2 - 20 kg"}, "Space-saving adjustable dumbbells."),
    ("Non-Slip Yoga Mat 6mm", "Beauty & Health", "Fitness", 1799, 2299, 130, 4.5, 2, "Islamabad", ["Purple", "Teal"], [], {"Thickness": "6 mm"}, "Cushioned, non-slip yoga mat with carry strap."),
    ("TrailBlazer 29er Mountain Bike", "Sports & Outdoors", "Cycling", 64999, 74999, 9, 4.5, 1, "Karachi", ["Red", "Black"], ["M", "L"], {"Gears": "21-speed", "Frame": "Aluminium"}, "Lightweight aluminium mountain bike with disc brakes."),
    ("AeroShield Cycling Helmet", "Sports & Outdoors", "Cycling", 3499, 4499, 75, 4.3, 2, "Islamabad", ["Black", "Yellow"], ["M", "L"], {"Vents": "18"}, "Ventilated helmet with adjustable fit system."),
    ("Summit 4-Person Camping Tent", "Sports & Outdoors", "Camping", 14999, 18999, 20, 4.4, 1, "Karachi", ["Green"], [], {"Capacity": "4 persons", "Waterproof": "3000 mm"}, "Quick-pitch tent with a waterproof rainfly."),
    ("Insulated Steel Flask 1L", "Sports & Outdoors", "Camping", 2499, 2999, 160, 4.6, 0, "Lahore", ["Silver", "Black"], [], {"Keeps hot": "12 h", "Keeps cold": "24 h"}, "Double-wall vacuum flask for trips and treks."),
]

ADDRESS = AddressIn(full_name="Demo Customer", phone="+92 300 1234567", line1="12 Garden Town, Main Boulevard", city="Lahore", postal_code="54000")


def seed(reset: bool = False) -> None:
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)  # in real deployments use `alembic upgrade head` instead
    with SessionLocal() as db:
        if db.scalar(select(User).limit(1)):
            print("Database already has data - use --reset to wipe it.")
            return
        rng = random.Random(42)

        # --- users
        def mk(email, name, role, store=None):
            u = User(email=email, full_name=name, role=role, store_name=store, hashed_password=hash_password("Customer123!" if role == Role.customer else "Seller123!"))
            db.add(u)
            return u

        sellers = [mk("seller@demo.com", "Sana Malik", Role.seller, "TechNest"), mk("seller2@demo.com", "Omar Farooq", Role.seller, "Urban Living Co."), mk("seller3@demo.com", "Hina Raza", Role.seller, "Everyday Essentials")]
        demo = mk("customer@demo.com", "Demo Customer", Role.customer)
        reviewers = [mk(f"reviewer{i}@demo.com", n, Role.customer) for i, n in enumerate(["Ali Khan", "Ayesha Noor", "Bilal Ahmed", "Fatima Zahra", "Hamza Iqbal", "Mariam Siddiqui"], 1)]
        db.flush()

        # --- categories
        cat_ids: dict[str, tuple[int, dict[str, int]]] = {}
        for top, subs in CATEGORIES.items():
            c = Category(name=top, slug=slug(top))
            db.add(c)
            db.flush()
            sub_ids = {}
            for s in subs:
                sc = Category(name=s, slug=slug(s), parent_id=c.id)
                db.add(sc)
                db.flush()
                sub_ids[s] = sc.id
            cat_ids[top] = (c.id, sub_ids)
        db.commit()

        # --- products (through the real service so validation/slugs behave like production)
        products = []
        for title, cat, sub, price, orig, stock, target, si, loc, colors, sizes, specs, desc in P:
            cid, subs = cat_ids[cat]
            p = product_service.create_product(
                db,
                sellers[si],
                ProductIn(
                    title=title, description=desc, category_id=cid, subcategory_id=subs[sub], price=price, original_price=orig, stock=stock, location=loc,
                    image_urls=[f"https://picsum.photos/seed/{slug(title)}/600/600"], colors=colors, sizes=sizes, specs=[SpecIn(name=k, value=v) for k, v in specs.items()],
                ),
            )
            products.append((p, target))

        # --- reviews (rows are real; products.rating is recomputed from them)
        for p, target in products:
            for u in rng.sample(reviewers, rng.randint(2, 6)):
                r = max(1, min(5, round(rng.gauss(target, 0.6))))
                db.add(Review(product_id=p.id, user_id=u.id, rating=r, comment=rng.choice(["Great value.", "Exactly as described.", "Fast delivery, happy with it.", "Good quality for the price.", "Would buy again."])))
            db.flush()
            review_service.recompute_rating(db, p.id)
        db.commit()

        # --- example orders in several lifecycle states (placed through the real checkout)
        plan = [(["Studio Pods", "VoltBrew"], OrderStatus.delivered), (["Classic Cotton", "RunFlex"], OrderStatus.shipped), (["ZenBook"], OrderStatus.processing), (["Vitamin C"], OrderStatus.pending)]
        by_title = {p.title: p for p, _ in products}
        flow = [OrderStatus.processing, OrderStatus.shipped, OrderStatus.out_for_delivery, OrderStatus.delivered]
        for names, final in plan:
            for n in names:
                prod = next(p for t, p in by_title.items() if t.startswith(n))
                cart_service.add_item(db, demo, prod.id, 1)
            for order in order_service.checkout(db, demo, ADDRESS):
                seller = next(s for s in sellers if s.id == order.seller_id)
                for step in flow[: flow.index(final) + 1] if final != OrderStatus.pending else []:
                    order_service.update_status(db, seller, order.id, step)
        print(f"Seeded {len(products)} products, {len(sellers)} sellers, 1 demo customer. See the docstring of app/db/seed.py for logins.")


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
