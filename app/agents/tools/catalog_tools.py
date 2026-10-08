"""READ-ONLY catalog tools. They reuse the same repository functions as GET /api/products."""
from dataclasses import replace
from decimal import Decimal

from pydantic import Field

from app.agents.tools.base import Tool, ToolArgs, ToolContext, ToolResult, product_summary
from app.models import Category
from app.repositories import product_repository as repo
from app.schemas.product import SortKey
from sqlalchemy import select


class SearchProductsArgs(ToolArgs):
    query: str | None = Field(None, max_length=100, description="Free-text keywords matched against title/description, e.g. 'kettle'")
    category: str | None = Field(None, max_length=80, description="Category or subcategory SLUG from the category list in the system prompt, e.g. 'electronics'")
    min_price: float | None = Field(None, ge=0)
    max_price: float | None = Field(None, ge=0)
    min_rating: float | None = Field(None, ge=0, le=5)
    in_stock_only: bool = False
    sort: SortKey = Field(SortKey.newest, description="newest | price_asc | price_desc | rating | popular | discount")
    limit: int = Field(5, ge=1, le=10)


def search_products(ctx: ToolContext, a: SearchProductsArgs) -> ToolResult:
    f = repo.ProductFilters(
        q=a.query,
        category=a.category,
        min_price=Decimal(str(a.min_price)) if a.min_price is not None else None,
        max_price=Decimal(str(a.max_price)) if a.max_price is not None else None,
        min_rating=a.min_rating,
        in_stock=a.in_stock_only,
        sort=a.sort,
    )
    items, total = repo.search_products(ctx.db, f, page=1, page_size=a.limit)
    note = note_code = None
    if total == 0 and a.query:
        # Nothing matched every word. Try progressively looser searches, but ALWAYS tell the model
        # (and so the user) that this is a looser match. Results are still real catalog rows.
        if len(repo.query_tokens(a.query)) > 1:
            items, total = repo.search_products(ctx.db, replace(f, match_any=True), page=1, page_size=a.limit)
            if total:
                note = f"No product matched all of “{a.query}”. These match some of the words."
                note_code = "partial_words"
        if total == 0 and (a.category or a.min_price is not None or a.max_price is not None or a.min_rating is not None):
            items, total = repo.search_products(ctx.db, replace(f, q=None, match_any=False), page=1, page_size=a.limit)
            if total:
                note = f"Nothing matched “{a.query}” exactly. These are the closest items for your other filters."
                note_code = "closest_filters"
    data = {"total_matches": total, "products": [product_summary(p) for p in items]}
    if note:
        data["note"], data["note_code"], data["query"] = note, note_code, a.query
    return ToolResult(data=data, products=items)


class TopRatedArgs(ToolArgs):
    category: str | None = Field(None, max_length=80, description="Category/subcategory slug, optional")
    limit: int = Field(5, ge=1, le=10)


def get_top_rated_products(ctx: ToolContext, a: TopRatedArgs) -> ToolResult:
    # min_rating=0.1 excludes products nobody has rated yet.
    f = repo.ProductFilters(category=a.category, min_rating=0.1, sort=SortKey.rating)
    items, total = repo.search_products(ctx.db, f, page=1, page_size=a.limit)
    return ToolResult(data={"total_matches": total, "products": [product_summary(p) for p in items]}, products=items)


class ProductIdArgs(ToolArgs):
    product_id: int = Field(ge=1, description="Numeric product id as shown in the product list")


def get_product_details(ctx: ToolContext, a: ProductIdArgs) -> ToolResult:
    p = repo.get_product(ctx.db, a.product_id)
    if p is None:
        return ToolResult(data={"error": "Product not found"}, error="Product not found")
    data = product_summary(p)
    data["description"] = (p.description or "")[:400]
    data["specifications"] = {s.name: s.value for s in p.specs}
    data["colors"], data["sizes"] = p.colors, p.sizes
    data["sold_by"] = p.seller.store_name or p.seller.full_name
    return ToolResult(data=data, products=[p])


class NoArgs(ToolArgs):
    pass


def list_categories(ctx: ToolContext, a: NoArgs) -> ToolResult:
    cats = ctx.db.scalars(select(Category).where(Category.parent_id.is_(None)).order_by(Category.name)).all()
    return ToolResult(data={"categories": [{"slug": c.slug, "name": c.name, "subcategories": [{"slug": s.slug, "name": s.name} for s in c.children]} for c in cats]})


CATALOG_TOOLS = [
    Tool("search_products", "Search/filter/sort the product catalog. Use for any request to find, browse, compare or filter products (by keyword, category, price range, rating, stock, or sort order).", SearchProductsArgs, search_products),
    Tool("get_top_rated_products", "Get the highest-rated products, optionally within one category.", TopRatedArgs, get_top_rated_products),
    Tool("get_product_details", "Get full details (specs, colors, sizes, stock, seller) of ONE product by id.", ProductIdArgs, get_product_details),
    Tool("list_categories", "List all categories and subcategories with their slugs.", NoArgs, list_categories),
]
