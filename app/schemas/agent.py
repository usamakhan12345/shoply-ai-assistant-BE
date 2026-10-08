from datetime import datetime

from pydantic import BaseModel

from app.models import Order, OrderStatus


class OrderItemBrief(BaseModel):
    title: str
    quantity: int
    image: str | None


class OrderBrief(BaseModel):
    """What the chat's order card needs - deliberately smaller than the full OrderOut (no address/phone)."""

    id: int
    status: str
    total: float
    created_at: datetime
    delivered_at: datetime | None
    items: list[OrderItemBrief]
    seller_store: str | None

    @classmethod
    def from_order(cls, o: Order) -> "OrderBrief":
        delivered = next((e.created_at for e in o.history if e.status == OrderStatus.delivered), None)
        return cls(
            id=o.id,
            status=o.status.value,
            total=float(o.total),
            created_at=o.created_at,
            delivered_at=delivered,
            items=[OrderItemBrief(title=i.title, quantity=i.quantity, image=i.image) for i in o.items],
            seller_store=o.seller.store_name if o.seller else None,
        )


class UiAction(BaseModel):
    type: str  # currently only "NAVIGATE"
    route: str
    label: str | None = None
