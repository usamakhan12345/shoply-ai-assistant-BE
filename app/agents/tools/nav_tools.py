"""Navigation + checkout-start tools.

These do NOT execute anything in the browser. They return a structured `ui_action`
({"type": "NAVIGATE", "route": "/checkout"}) built from the fixed ROUTES table; the frontend validates it
against its own allow-list and then uses its normal router. The model never produces a URL or JavaScript.

`start_checkout` never creates an order. The website's real checkout page (address review, totals, payment)
stays in charge; the agent only prepares the cart and opens that page."""
from pydantic import Field

from app.agents.tools.base import Tool, ToolArgs, ToolContext, ToolResult, navigate, require_customer
from app.agents.tools.catalog_tools import NoArgs, ProductIdArgs
from app.repositories import product_repository as repo
from app.services import cart_service, order_service


class StartCheckoutArgs(ToolArgs):
    product_id: int | None = Field(None, ge=1, description="Product the user wants to order now. Omit to check out the current cart.")


def start_checkout(ctx: ToolContext, a: StartCheckoutArgs) -> ToolResult:
    user = require_customer(ctx)
    title = None
    if a.product_id is not None:
        cart = cart_service.get_cart(ctx.db, user)
        in_cart = next((i for i in cart.items if i.product_id == a.product_id), None)
        if in_cart is None:  # same rules as the Add-to-cart button (stock check, etc.)
            title = cart_service.add_item(ctx.db, user, a.product_id, 1).product.title
        else:
            title = in_cart.product.title
    cart = cart_service.get_cart(ctx.db, user)
    if not cart.items:
        return ToolResult(data={"status": "cart_empty"})
    t = cart_service.totals(cart.items)
    return ToolResult(
        data={"status": "ready", "product": title, "item_count": t["item_count"], "total": float(t["total"])},
        products=[i.product for i in cart.items],
        ui_action=navigate("checkout", "Open checkout"),
    )


def navigate_to_orders(ctx: ToolContext, a: NoArgs) -> ToolResult:
    require_customer(ctx)
    return ToolResult(data={"status": "opening_orders"}, ui_action=navigate("orders", "My orders"))


def navigate_to_cart(ctx: ToolContext, a: NoArgs) -> ToolResult:
    require_customer(ctx)
    return ToolResult(data={"status": "opening_cart"}, ui_action=navigate("cart", "Open cart"))


class OrderIdArgs(ToolArgs):
    order_id: int = Field(ge=1)


def navigate_to_order(ctx: ToolContext, a: OrderIdArgs) -> ToolResult:
    user = require_customer(ctx)
    order_service.get_customer_order(ctx.db, user, a.order_id)  # NotFound unless it is the caller's own order
    return ToolResult(data={"status": "opening_order", "order_id": a.order_id}, ui_action=navigate("order", "Order details", id=a.order_id))


def navigate_to_product(ctx: ToolContext, a: ProductIdArgs) -> ToolResult:
    p = repo.get_product(ctx.db, a.product_id)
    if p is None:
        return ToolResult(data={"error": "Product not found", "code": "not_found"}, error="not_found")
    return ToolResult(data={"status": "opening_product", "product": p.title}, products=[p], ui_action=navigate("product", "View product", id=p.id))


NAV_TOOLS = [
    Tool("start_checkout", "Prepare checkout and open the website's checkout page. Optionally pass the product the user wants to order now (it is put in the cart first). Does NOT place an order: the user reviews address/payment on the checkout page. Use for 'order this', 'buy it', 'checkout karwa do'.", StartCheckoutArgs, start_checkout, mutating=True),
    Tool("navigate_to_orders", "Open the user's My Orders page.", NoArgs, navigate_to_orders, requires_login=True),
    Tool("navigate_to_order", "Open the details/tracking page of one of the user's own orders.", OrderIdArgs, navigate_to_order, requires_login=True),
    Tool("navigate_to_cart", "Open the user's cart page.", NoArgs, navigate_to_cart, requires_login=True),
    Tool("navigate_to_product", "Open the product detail page of one product.", ProductIdArgs, navigate_to_product),
]
