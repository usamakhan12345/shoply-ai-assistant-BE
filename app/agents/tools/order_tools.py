"""Read-only access to the CURRENT user's own orders.

Ownership is guaranteed by the service layer: `list_customer_orders` only returns the caller's orders and
`get_customer_order` answers "not found" for anyone else's. No tool takes a user id, and there is no tool
that changes order status, so a customer's agent can never touch another user's order or edit one."""
from typing import Literal

from pydantic import Field

from app.agents.tools.base import Tool, ToolArgs, ToolContext, ToolResult, require_customer
from app.agents.tools.catalog_tools import NoArgs
from app.models import Order, OrderStatus
from app.services import order_service

# Filters the model may ask for. "in_progress" = placed but not delivered/cancelled yet (what users usually
# mean by "pending" / "on the way").
OrderFilter = Literal["any", "in_progress", "pending", "processing", "shipped", "out_for_delivery", "delivered", "cancelled"]
_FILTERS: dict[str, set[OrderStatus] | None] = {
    "any": None,
    "in_progress": {OrderStatus.pending, OrderStatus.processing, OrderStatus.shipped, OrderStatus.out_for_delivery},
    "pending": {OrderStatus.pending},
    "processing": {OrderStatus.processing},
    "shipped": {OrderStatus.shipped},
    "out_for_delivery": {OrderStatus.out_for_delivery},
    "delivered": {OrderStatus.delivered},
    "cancelled": {OrderStatus.cancelled},
}


def order_brief(o: Order, detailed: bool = False) -> dict:
    """Only the fields the model needs to answer - no addresses, phone numbers or internal ids."""
    at = {e.status: e.created_at for e in o.history}
    d = {
        "order_id": o.id,
        "status": o.status.value,
        "total": float(o.total),
        "placed_on": o.created_at.date().isoformat() if o.created_at else None,
        "delivered_on": at[OrderStatus.delivered].date().isoformat() if OrderStatus.delivered in at else None,
        "items": [f"{i.quantity} x {i.title}" for i in o.items],
        "sold_by": o.seller.store_name if o.seller else None,
    }
    if detailed:
        d["tracking"] = [{"status": e.status.value, "on": e.created_at.date().isoformat()} for e in o.history if e.created_at]
        d["ship_to_city"] = o.shipping_city
    return d


class MyOrdersArgs(ToolArgs):
    status: OrderFilter = Field("any", description="Filter: any | in_progress (not delivered/cancelled yet) | pending | processing | shipped | out_for_delivery | delivered | cancelled")
    limit: int = Field(5, ge=1, le=10)


def get_my_orders(ctx: ToolContext, a: MyOrdersArgs) -> ToolResult:
    user = require_customer(ctx)
    wanted = _FILTERS[a.status]
    orders = [o for o in order_service.list_customer_orders(ctx.db, user) if wanted is None or o.status in wanted]
    shown = orders[: a.limit]  # newest first
    return ToolResult(
        data={"filter": a.status, "total_matching_orders": len(orders), "orders": [order_brief(o) for o in shown]},
        orders=shown,
    )


class MyOrderArgs(ToolArgs):
    order_id: int | None = Field(None, ge=1, description="A specific order number the user mentioned (e.g. 1029). Omit to pick by `which`.")
    which: Literal["latest", "oldest"] = Field("latest", description="Used only when order_id is omitted")


def get_my_order(ctx: ToolContext, a: MyOrderArgs) -> ToolResult:
    """One order with its current status and tracking history. Answers 'where is my order?'."""
    user = require_customer(ctx)
    if a.order_id is not None:
        o = order_service.get_customer_order(ctx.db, user, a.order_id)  # NotFound unless it is the caller's own
    else:
        mine = order_service.list_customer_orders(ctx.db, user)
        if not mine:
            return ToolResult(data={"found": False, "message": "The user has no orders yet"})
        o = mine[0] if a.which == "latest" else mine[-1]
    return ToolResult(data={"found": True, **order_brief(o, detailed=True)}, orders=[o])


def get_my_spending(ctx: ToolContext, a: NoArgs) -> ToolResult:
    """How much the user has spent in total. Cancelled orders are excluded (they were refunded)."""
    user = require_customer(ctx)
    orders = order_service.list_customer_orders(ctx.db, user)
    counted = [o for o in orders if o.status != OrderStatus.cancelled]
    return ToolResult(
        data={
            "orders_counted": len(counted),
            "cancelled_orders_excluded": len(orders) - len(counted),
            "delivered_orders": sum(o.status == OrderStatus.delivered for o in counted),
            "total_spent": float(sum((o.total for o in counted), 0)),
            "first_order_on": min((o.created_at for o in counted), default=None).date().isoformat() if counted else None,
        }
    )


ORDER_TOOLS = [
    Tool("get_my_orders", "List the logged-in customer's own orders, optionally filtered by status (delivered, cancelled, in_progress...). Also use it to count orders.", MyOrdersArgs, get_my_orders, requires_login=True),
    Tool("get_my_order", "Get ONE of the logged-in customer's own orders (by number, or the latest/oldest) with its current status and tracking history. Use for 'where is my order', 'order status', 'was my last order delivered'.", MyOrderArgs, get_my_order, requires_login=True),
    Tool("get_my_spending", "How much the logged-in customer has spent in total across all their orders (cancelled orders excluded). Use for 'how much have I shopped / spent so far', 'total shopping', 'mene ab tak kitne ki shopping ki'.", NoArgs, get_my_spending, requires_login=True),
]
