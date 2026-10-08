"""Building blocks for agent tools.

KEY SECURITY IDEA
-----------------
A tool is the ONLY way the LLM can touch the application. Each tool:
  1. declares its arguments as a pydantic model (this also becomes the JSON schema shown to the LLM),
  2. forbids unknown arguments (`extra="forbid"`), so a made-up `user_id` argument is rejected,
  3. receives the *authenticated* user through `ToolContext`, which the LLM never sees or controls,
  4. calls the same service layer the REST API uses, so normal authorization/business rules apply.

HOW TO ADD A TOOL (e.g. `cancel_order`, `compare_products`, `add_to_wishlist`)
  - write an args model + a handler `(ctx, args) -> ToolResult` in a tools/*.py file,
  - register it in `Tool(...)` list there, and make sure registry.py includes that list. That's all:
    the schema for the LLM, validation, the login gate and error handling come for free.
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError
from app.models import Order, Product, Role, User

# The ONLY routes an agent may send the browser to. The frontend keeps its own copy of this allow-list
# and refuses anything else, so a bad model output can never navigate to an arbitrary URL.
ROUTES = {
    "checkout": "/checkout",
    "cart": "/cart",
    "orders": "/orders",
    "order": "/orders/{id}",
    "product": "/products/{id}",
}


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass
class ToolContext:
    db: Session
    user: User | None  # None = anonymous guest. Set by the backend from the JWT, never by the LLM.


@dataclass
class ToolResult:
    data: dict[str, Any]  # JSON that is sent back to the LLM
    products: list[Product] = field(default_factory=list)  # ORM rows the UI should render as product cards
    orders: list[Order] = field(default_factory=list)  # ORM rows the UI should render as order cards
    ui_action: dict | None = None  # structured instruction for the frontend, e.g. {"type": "NAVIGATE", "route": "/checkout"}
    error: str | None = None
    login_required: bool = False


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[ToolArgs]
    handler: Callable[[ToolContext, Any], ToolResult]
    mutating: bool = False  # mutating tools need a logged-in user BEFORE any DB access happens
    requires_login: bool = False  # read tools that expose private data (own cart/orders)

    def llm_schema(self) -> dict:
        """The OpenAI-style function spec shown to the model."""
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": schema}}


def require_customer(ctx: ToolContext) -> User:
    """Orders/cart belong to customer accounts. (Login itself is enforced by the executor.)"""
    if ctx.user is None or ctx.user.role != Role.customer:
        raise ForbiddenError("Only customer accounts have a cart and orders")
    return ctx.user


def navigate(route_key: str, label: str, **params) -> dict:
    """Build a NAVIGATE action from the fixed ROUTES table (never from free text)."""
    return {"type": "NAVIGATE", "route": ROUTES[route_key].format(**params), "label": label}


def product_summary(p: Product) -> dict:
    """Compact, factual product record for the LLM. Free-text description is deliberately omitted
    (it is seller-written, i.e. untrusted input that could contain prompt-injection text)."""
    return {
        "id": p.id,
        "title": p.title,
        "price": float(p.price),
        "original_price": float(p.original_price) if p.original_price else None,
        "discount_percent": p.discount,
        "rating": float(p.rating),
        "review_count": p.review_count,
        "stock": p.stock,
        "category": p.category.name,
        "subcategory": p.subcategory.name if p.subcategory else None,
    }
