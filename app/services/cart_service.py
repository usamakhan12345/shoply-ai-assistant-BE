"""Cart business rules. The REST API and the AI agent's cart tools both call these functions,
so the agent can never do anything a normal customer couldn't."""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError, StockError
from app.models import Cart, CartItem, Product, Role, User
from app.repositories import product_repository as repo


def _require_customer(user: User) -> None:
    if user.role != Role.customer:
        raise ForbiddenError("Only customers have a shopping cart")


def get_cart(db: Session, user: User) -> Cart:
    _require_customer(user)
    cart = db.scalar(
        select(Cart)
        .where(Cart.user_id == user.id)
        .options(selectinload(Cart.items).selectinload(CartItem.product).options(*repo._LOAD))
        .execution_options(populate_existing=True)  # never serve a stale items list after add/remove in the same session
    )
    if cart is None:
        cart = Cart(user_id=user.id)
        db.add(cart)
        db.commit()
    return cart


def totals(items: list[CartItem]) -> dict:
    """Pricing is ALWAYS computed from current DB prices, never from client input."""
    s = get_settings()
    subtotal = sum((i.product.price * i.quantity for i in items), Decimal(0))
    list_total = sum(((i.product.original_price or i.product.price) * i.quantity for i in items), Decimal(0))
    discount = list_total - subtotal
    shipping = Decimal(0) if (not items or subtotal >= Decimal(str(s.FREE_SHIPPING_THRESHOLD))) else Decimal(str(s.SHIPPING_FLAT_FEE))
    return {
        "subtotal": subtotal,
        "discount_total": discount,
        "shipping": shipping,
        "total": subtotal + shipping,
        "item_count": sum(i.quantity for i in items),
    }


def add_item(db: Session, user: User, product_id: int, quantity: int = 1) -> CartItem:
    cart = get_cart(db, user)
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product not found")
    item = next((i for i in cart.items if i.product_id == product_id), None)
    new_qty = (item.quantity if item else 0) + quantity
    if new_qty > product.stock:
        raise StockError(f"Only {product.stock} unit(s) of '{product.title}' in stock")
    if item:
        item.quantity = new_qty
    else:
        item = CartItem(cart_id=cart.id, product_id=product_id, quantity=new_qty)
        db.add(item)
    db.commit()
    return item


def _own_item(db: Session, user: User, item_id: int) -> CartItem:
    cart = get_cart(db, user)
    item = next((i for i in cart.items if i.id == item_id), None)
    if item is None:  # also hit when the item belongs to someone else's cart
        raise NotFoundError("Cart item not found")
    return item


def set_quantity(db: Session, user: User, item_id: int, quantity: int) -> CartItem:
    item = _own_item(db, user, item_id)
    if quantity > item.product.stock:
        raise StockError(f"Only {item.product.stock} unit(s) of '{item.product.title}' in stock")
    item.quantity = quantity
    db.commit()
    return item


def remove_item(db: Session, user: User, item_id: int) -> None:
    item = _own_item(db, user, item_id)
    db.delete(item)
    db.commit()


def remove_product(db: Session, user: User, product_id: int) -> CartItem:
    """Used by the AI tool, which knows product ids rather than cart-item ids."""
    cart = get_cart(db, user)
    item = next((i for i in cart.items if i.product_id == product_id), None)
    if item is None:
        raise NotFoundError("That product is not in your cart")
    db.delete(item)
    db.commit()
    return item


def clear(db: Session, cart: Cart) -> None:
    for i in list(cart.items):
        db.delete(i)
