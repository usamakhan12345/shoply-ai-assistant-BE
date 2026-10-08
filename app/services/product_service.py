"""Seller-side product management. Ownership is enforced HERE, not in the route."""
import re
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, AppError
from app.models import Category, Product, ProductImage, ProductOption, ProductSpec, User
from app.repositories import product_repository as repo
from app.schemas.product import ProductIn, ProductUpdate


def _slugify(title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "product"
    return f"{base}-{secrets.token_hex(3)}"


def _validate_categories(db: Session, category_id: int | None, subcategory_id: int | None, current: Product | None = None):
    cat_id = category_id if category_id is not None else (current.category_id if current else None)
    sub_id = subcategory_id if subcategory_id is not None else (current.subcategory_id if current else None)
    cat = db.get(Category, cat_id) if cat_id else None
    if cat is None or cat.parent_id is not None:
        raise AppError("category_id must be an existing top-level category", code="invalid_category")
    if sub_id is not None:
        sub = db.get(Category, sub_id)
        if sub is None or sub.parent_id != cat.id:
            raise AppError("subcategory_id must be a child of the chosen category", code="invalid_subcategory")


def _fill_children(p: Product, data) -> None:
    if data.image_urls is not None:
        p.images = [ProductImage(url=u, position=i) for i, u in enumerate(data.image_urls)]
    if data.specs is not None:
        p.specs = [ProductSpec(name=s.name, value=s.value) for s in data.specs]
    if data.colors is not None or data.sizes is not None:
        keep = [o for o in p.options if (o.kind == "color" and data.colors is None) or (o.kind == "size" and data.sizes is None)]
        new = [ProductOption(kind="color", value=c) for c in (data.colors or [])]
        new += [ProductOption(kind="size", value=s) for s in (data.sizes or [])]
        p.options = keep + new


def get_owned_product(db: Session, user: User, product_id: int) -> Product:
    """Load a product and verify the current seller owns it. 404 for missing, 403 for someone else's."""
    p = repo.get_product(db, product_id)
    if p is None:
        raise NotFoundError("Product not found")
    if p.seller_id != user.id:
        raise ForbiddenError("You can only manage your own products")
    return p


def create_product(db: Session, seller: User, data: ProductIn) -> Product:
    _validate_categories(db, data.category_id, data.subcategory_id)
    p = Product(
        seller_id=seller.id,  # from the authenticated user, never from the request body
        category_id=data.category_id,
        subcategory_id=data.subcategory_id,
        title=data.title.strip(),
        slug=_slugify(data.title),
        description=data.description,
        price=data.price,
        original_price=data.original_price,
        stock=data.stock,
        location=data.location,
    )
    _fill_children(p, data)
    db.add(p)
    db.commit()
    return repo.get_product(db, p.id)


def update_product(db: Session, seller: User, product_id: int, data: ProductUpdate) -> Product:
    p = get_owned_product(db, seller, product_id)
    changes = data.model_dump(exclude_unset=True, exclude={"image_urls", "specs", "colors", "sizes"})
    if "category_id" in changes or "subcategory_id" in changes:
        _validate_categories(db, changes.get("category_id"), changes.get("subcategory_id"), current=p)
    for k, v in changes.items():
        if v is None and k in {"title", "price", "stock", "category_id"}:
            continue
        setattr(p, k, v)
    if p.original_price is not None and p.original_price < p.price:
        raise AppError("original_price must be >= price", code="invalid_price")
    _fill_children(p, data)
    db.commit()
    return repo.get_product(db, p.id)


def delete_product(db: Session, seller: User, product_id: int) -> None:
    p = get_owned_product(db, seller, product_id)
    db.delete(p)  # order_items.product_id is SET NULL; order history keeps its snapshots
    db.commit()


def seller_stats(db: Session, seller: User) -> dict:
    from app.models import Order, OrderStatus

    products = db.scalar(select(func.count()).select_from(Product).where(Product.seller_id == seller.id)) or 0
    low = db.scalar(select(func.count()).select_from(Product).where(Product.seller_id == seller.id, Product.stock <= 5)) or 0
    orders = db.scalar(select(func.count()).select_from(Order).where(Order.seller_id == seller.id)) or 0
    pending = db.scalar(select(func.count()).select_from(Order).where(Order.seller_id == seller.id, Order.status == OrderStatus.pending)) or 0
    revenue = db.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(Order.seller_id == seller.id, Order.status != OrderStatus.cancelled)
    )
    return {"products": products, "low_stock": low, "orders": orders, "pending_orders": pending, "revenue": float(revenue or 0)}
