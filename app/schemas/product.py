from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORM, Money


class SortKey(str, Enum):
    newest = "newest"
    price_asc = "price_asc"
    price_desc = "price_desc"
    rating = "rating"
    popular = "popular"
    discount = "discount"


class CategoryOut(ORM):
    id: int
    name: str
    slug: str
    parent_id: int | None


class CategoryTree(ORM):
    id: int
    name: str
    slug: str
    children: list[CategoryOut]


class SpecIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=255)


class SpecOut(ORM):
    name: str
    value: str


class SellerBrief(ORM):
    id: int
    store_name: str | None
    full_name: str


class ProductCard(ORM):
    """Everything the storefront Product Card (and the AI chat) needs."""

    id: int
    title: str
    slug: str
    price: Money
    original_price: Money | None
    discount: int
    rating: Money
    review_count: int
    stock: int
    image: str | None
    category: CategoryOut
    subcategory: CategoryOut | None


class ProductDetail(ProductCard):
    description: str
    sales_count: int
    location: str | None
    seller: SellerBrief
    images: list["ImageOut"]
    specs: list[SpecOut]
    colors: list[str]
    sizes: list[str]
    created_at: datetime


class ImageOut(ORM):
    id: int
    url: str


class ProductIn(BaseModel):
    """Payload for creating a product. Note what is NOT here: seller_id (comes from the JWT),
    rating/review_count/sales_count (computed by the backend) and discount (derived)."""

    title: str = Field(min_length=2, max_length=200)
    description: str = ""
    category_id: int
    subcategory_id: int | None = None
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    original_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    stock: int = Field(ge=0, default=0)
    location: str | None = Field(default=None, max_length=120)
    image_urls: list[str] = Field(default_factory=list, max_length=8)
    specs: list[SpecIn] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    sizes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def original_not_below_price(self):
        if self.original_price is not None and self.original_price < self.price:
            raise ValueError("original_price must be >= price")
        return self


class ProductUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    category_id: int | None = None
    subcategory_id: int | None = None
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    original_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    stock: int | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=120)
    image_urls: list[str] | None = Field(default=None, max_length=8)
    specs: list[SpecIn] | None = None
    colors: list[str] | None = None
    sizes: list[str] | None = None


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=2000)


class ReviewOut(ORM):
    id: int
    rating: int
    comment: str
    created_at: datetime
    reviewer: str = ""
