from app.models import ALLOWED_TRANSITIONS, Cart, Order
from app.schemas.cart_order import CartItemOut, CartOut, OrderOut
from app.schemas.product import ProductCard
from app.services import cart_service


def cart_out(cart: Cart) -> CartOut:
    t = cart_service.totals(cart.items)
    items = [
        CartItemOut(id=i.id, quantity=i.quantity, product=ProductCard.model_validate(i.product), line_total=i.product.price * i.quantity)
        for i in cart.items
    ]
    return CartOut(items=items, **t)


def order_out(o: Order, for_seller: bool = False) -> OrderOut:
    out = OrderOut.model_validate(o)
    out.seller_store = o.seller.store_name if o.seller else None
    out.customer_name = o.customer.full_name if o.customer else None
    if for_seller:
        out.next_statuses = sorted(ALLOWED_TRANSITIONS[o.status], key=lambda s: s.value)
    return out
