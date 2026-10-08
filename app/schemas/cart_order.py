from datetime import datetime

from pydantic import BaseModel, Field

from app.models.commerce import OrderStatus
from app.schemas.common import ORM, Money
from app.schemas.product import ProductCard


class CartItemIn(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=99)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1, le=99)


class CartItemOut(ORM):
    id: int
    quantity: int
    product: ProductCard
    line_total: Money = 0


class CartOut(BaseModel):
    items: list[CartItemOut]
    item_count: int
    subtotal: Money
    discount_total: Money
    shipping: Money
    total: Money


class AddressIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=5, max_length=30)
    line1: str = Field(min_length=3, max_length=255)
    city: str = Field(min_length=1, max_length=80)
    postal_code: str = Field(min_length=2, max_length=20)
    country: str = Field(default="Pakistan", max_length=80)


class CheckoutIn(BaseModel):
    """The client sends ONLY the address and payment method. Never prices or totals."""

    address: AddressIn
    payment_method: str = Field(default="mock", pattern="^mock$")


class OrderItemOut(ORM):
    id: int
    product_id: int | None
    title: str
    image: str | None
    unit_price: Money
    original_unit_price: Money
    quantity: int


class StatusEventOut(ORM):
    status: OrderStatus
    created_at: datetime


class OrderOut(ORM):
    id: int
    checkout_ref: str
    status: OrderStatus
    subtotal: Money
    discount_total: Money
    shipping: Money
    total: Money
    payment_method: str
    payment_status: str
    shipping_name: str
    shipping_phone: str
    shipping_line1: str
    shipping_city: str
    shipping_postal_code: str
    shipping_country: str
    created_at: datetime
    items: list[OrderItemOut]
    history: list[StatusEventOut]
    seller_store: str | None = None
    customer_name: str | None = None
    next_statuses: list[OrderStatus] = []


class StatusUpdateIn(BaseModel):
    status: OrderStatus
