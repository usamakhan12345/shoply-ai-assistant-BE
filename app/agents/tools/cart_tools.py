"""Cart tools. The user is taken from ToolContext (the JWT), NEVER from the model's arguments.
Mutations go through cart_service - the same code path as POST /api/cart/items."""
from pydantic import Field

from app.agents.tools.base import Tool, ToolArgs, ToolContext, ToolResult, product_summary
from app.agents.tools.catalog_tools import NoArgs, ProductIdArgs
from app.services import cart_service


class AddToCartArgs(ToolArgs):
    product_id: int = Field(ge=1, description="Id of the product to add (resolve 'the second one' etc. from the recently shown list)")
    quantity: int = Field(1, ge=1, le=20)


def add_to_cart(ctx: ToolContext, a: AddToCartArgs) -> ToolResult:
    item = cart_service.add_item(ctx.db, ctx.user, a.product_id, a.quantity)
    return ToolResult(
        data={"status": "added", "product": item.product.title, "quantity_in_cart": item.quantity},
        products=[item.product],
    )


def remove_from_cart(ctx: ToolContext, a: ProductIdArgs) -> ToolResult:
    item = cart_service.remove_product(ctx.db, ctx.user, a.product_id)
    return ToolResult(data={"status": "removed", "product": item.product.title})


class UpdateQtyArgs(ToolArgs):
    product_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=20, description="New TOTAL quantity for this product in the cart")


def update_cart_quantity(ctx: ToolContext, a: UpdateQtyArgs) -> ToolResult:
    cart = cart_service.get_cart(ctx.db, ctx.user)
    item = next((i for i in cart.items if i.product_id == a.product_id), None)
    if item is None:
        return ToolResult(data={"error": "That product is not in your cart"}, error="not in cart")
    item = cart_service.set_quantity(ctx.db, ctx.user, item.id, a.quantity)
    return ToolResult(data={"status": "updated", "product": item.product.title, "quantity_in_cart": item.quantity})


def get_cart(ctx: ToolContext, a: NoArgs) -> ToolResult:
    cart = cart_service.get_cart(ctx.db, ctx.user)
    t = cart_service.totals(cart.items)
    return ToolResult(
        data={
            "items": [{"quantity": i.quantity, **product_summary(i.product)} for i in cart.items],
            "item_count": t["item_count"],
            "subtotal": float(t["subtotal"]),
            "shipping": float(t["shipping"]),
            "total": float(t["total"]),
        },
        products=[i.product for i in cart.items],
    )


CART_TOOLS = [
    Tool("get_cart", "Show the logged-in user's current cart.", NoArgs, get_cart, requires_login=True),
    Tool("add_to_cart", "Add a product to the logged-in user's cart.", AddToCartArgs, add_to_cart, mutating=True),
    Tool("remove_from_cart", "Remove a product from the logged-in user's cart.", ProductIdArgs, remove_from_cart, mutating=True),
    Tool("update_cart_quantity", "Change the quantity of a product already in the cart.", UpdateQtyArgs, update_cart_quantity, mutating=True),
]
