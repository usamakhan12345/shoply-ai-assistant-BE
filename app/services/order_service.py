import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errors import AppError, ForbiddenError, NotFoundError, StockError
from app.models import ALLOWED_TRANSITIONS, Order, OrderItem, OrderStatus, OrderStatusEvent, Product, User
from app.schemas.cart_order import AddressIn
from app.services import cart_service

_LOAD = (selectinload(Order.items), selectinload(Order.history), selectinload(Order.seller), selectinload(Order.customer))


def checkout(db: Session, customer: User, address: AddressIn, payment_method: str = "mock") -> list[Order]:
    """Turn the cart into orders (one per seller) in a single DB transaction.

    Steps: validate -> reserve stock atomically -> snapshot prices -> clear cart -> commit.
    If anything fails the whole transaction rolls back and no stock is lost.
    """
    cart = cart_service.get_cart(db, customer)
    if not cart.items:
        raise AppError("Your cart is empty", code="empty_cart")

    by_seller: dict[int, list] = defaultdict(list)
    for ci in cart.items:
        by_seller[ci.product.seller_id].append(ci)

    s = get_settings()
    checkout_ref = str(uuid.uuid4())  # shared by all orders created from this one checkout
    orders: list[Order] = []
    try:
        for seller_id, cart_items in by_seller.items():
            order_items = []
            for ci in cart_items:
                # Atomic conditional decrement: succeeds only if enough stock remains at this instant,
                # so two concurrent checkouts can never oversell.
                res = db.execute(
                    update(Product)
                    .where(Product.id == ci.product_id, Product.stock >= ci.quantity)
                    .values(stock=Product.stock - ci.quantity, sales_count=Product.sales_count + ci.quantity)
                )
                if res.rowcount != 1:
                    raise StockError(f"'{ci.product.title}' does not have enough stock for quantity {ci.quantity}")
                p = ci.product
                order_items.append(
                    OrderItem(
                        product_id=p.id,
                        title=p.title,
                        image=p.image,
                        unit_price=p.price,
                        original_unit_price=p.original_price or p.price,
                        quantity=ci.quantity,
                    )
                )
            subtotal = sum((oi.unit_price * oi.quantity for oi in order_items), Decimal(0))
            list_total = sum((oi.original_unit_price * oi.quantity for oi in order_items), Decimal(0))
            shipping = Decimal(0) if subtotal >= Decimal(str(s.FREE_SHIPPING_THRESHOLD)) else Decimal(str(s.SHIPPING_FLAT_FEE))
            order = Order(
                checkout_ref=checkout_ref,
                customer_id=customer.id,
                seller_id=seller_id,
                subtotal=subtotal,
                discount_total=list_total - subtotal,
                shipping=shipping,
                total=subtotal + shipping,
                payment_method=payment_method,
                payment_status="paid",  # MOCK: no real money moves. A real gateway plugs in here.
                shipping_name=address.full_name,
                shipping_phone=address.phone,
                shipping_line1=address.line1,
                shipping_city=address.city,
                shipping_postal_code=address.postal_code,
                shipping_country=address.country,
                items=order_items,
                history=[OrderStatusEvent(status=OrderStatus.pending)],
            )
            db.add(order)
            orders.append(order)
        cart_service.clear(db, cart)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return [get_order(db, o.id) for o in orders]


def get_order(db: Session, order_id: int) -> Order:
    o = db.scalar(select(Order).where(Order.id == order_id).options(*_LOAD))
    if o is None:
        raise NotFoundError("Order not found")
    return o


def get_customer_order(db: Session, customer: User, order_id: int) -> Order:
    o = get_order(db, order_id)
    if o.customer_id != customer.id:
        raise NotFoundError("Order not found")  # don't reveal that other people's orders exist
    return o


def list_customer_orders(db: Session, customer: User) -> list[Order]:
    return list(db.scalars(select(Order).where(Order.customer_id == customer.id).options(*_LOAD).order_by(Order.id.desc())).all())


def list_seller_orders(db: Session, seller: User, status: OrderStatus | None = None) -> list[Order]:
    stmt = select(Order).where(Order.seller_id == seller.id).options(*_LOAD).order_by(Order.id.desc())
    if status:
        stmt = stmt.where(Order.status == status)
    return list(db.scalars(stmt).all())


def get_seller_order(db: Session, seller: User, order_id: int) -> Order:
    o = get_order(db, order_id)
    if o.seller_id != seller.id:
        raise ForbiddenError("This order does not contain your products")
    return o


def update_status(db: Session, seller: User, order_id: int, new_status: OrderStatus) -> Order:
    o = get_seller_order(db, seller, order_id)
    if new_status not in ALLOWED_TRANSITIONS[o.status]:
        allowed = ", ".join(s.value for s in ALLOWED_TRANSITIONS[o.status]) or "none"
        raise AppError(
            f"Cannot change status from '{o.status.value}' to '{new_status.value}'. Allowed: {allowed}",
            code="invalid_status_transition",
            status_code=409,
        )
    if new_status == OrderStatus.cancelled:  # give the stock back
        for it in o.items:
            if it.product_id:
                db.execute(
                    update(Product)
                    .where(Product.id == it.product_id)
                    .values(stock=Product.stock + it.quantity, sales_count=Product.sales_count - it.quantity)
                )
        o.payment_status = "refunded"
    o.status = new_status
    o.history.append(OrderStatusEvent(status=new_status))
    db.commit()
    return get_order(db, o.id)
