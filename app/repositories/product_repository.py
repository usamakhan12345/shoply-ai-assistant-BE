"""Read-side product queries. The REST API *and* the AI tools both call `search_products`,
so there is exactly one place that knows how to filter/sort the catalog."""
import re
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Category, Product, ProductOption
from app.schemas.product import SortKey


@dataclass
class ProductFilters:
    q: str | None = None
    category: str | None = None  # slug of a category OR subcategory
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    min_rating: float | None = None
    in_stock: bool = False
    seller_id: int | None = None
    sort: SortKey = SortKey.newest
    match_any: bool = False  # q words: False = every word must match (AND), True = any word (OR)


def query_tokens(q: str) -> list[str]:
    """'Wireless Earbuds' -> ['wireless', 'earbud'] (lower-cased, naive singular, 1-letter words dropped)."""
    words = re.findall(r"[a-z0-9]+", q.lower())
    return [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words if len(w) > 1]


def _word_like(col, tok: str):
    """Matches `tok` at the START of a word in `col` ('men' matches 'Men's Clothing' but not 'Women's').
    Very short tokens must be a WHOLE word, so 'car' does not match 'scarf' or 'carry'."""
    c = func.lower(col)
    if len(tok) <= 3:
        forms = (tok, tok + "s")  # whole word, singular or plural
        conds = []
        for w in forms:
            conds += [c == w, c.like(f"{w} %"), c.like(f"% {w} %"), c.like(f"% {w}"), c.like(f"% {w},%"), c.like(f"% {w}.%"), c.like(f"%-{w} %")]
        return or_(*conds)
    return or_(c.like(f"{tok}%"), c.like(f"% {tok}%"), c.like(f"%-{tok}%"), c.like(f"%({tok}%"))


def _token_condition(tok: str):
    return or_(
        _word_like(Product.title, tok),
        _word_like(Product.description, tok),
        Product.category_id.in_(select(Category.id).where(_word_like(Category.name, tok))),
        Product.subcategory_id.in_(select(Category.id).where(_word_like(Category.name, tok))),
        Product.id.in_(select(ProductOption.product_id).where(_word_like(ProductOption.value, tok))),  # colours / sizes
    )


_ORDER = {
    SortKey.newest: lambda: (Product.id.desc(),),
    SortKey.price_asc: lambda: (Product.price.asc(), Product.id),
    SortKey.price_desc: lambda: (Product.price.desc(), Product.id),
    SortKey.rating: lambda: (Product.rating.desc(), Product.review_count.desc(), Product.id),
    SortKey.popular: lambda: (Product.sales_count.desc(), Product.id),
    SortKey.discount: lambda: (
        # biggest saving ratio first
        (func.coalesce(Product.original_price, Product.price) - Product.price).desc(),
        Product.id,
    ),
}

_LOAD = (
    selectinload(Product.category),
    selectinload(Product.subcategory),
    selectinload(Product.images),
)


def _apply(stmt: Select, f: ProductFilters, db: Session) -> Select:
    toks = query_tokens(f.q) if f.q else []
    if toks:
        conds = [_token_condition(t) for t in toks]
        stmt = stmt.where(or_(*conds) if f.match_any else and_(*conds))
    if f.category:
        cat = db.scalar(select(Category).where(Category.slug == f.category.lower()))
        if cat is None:
            return stmt.where(Product.id == -1)  # unknown category -> empty result, not an error
        stmt = stmt.where(or_(Product.category_id == cat.id, Product.subcategory_id == cat.id))
    if f.min_price is not None:
        stmt = stmt.where(Product.price >= f.min_price)
    if f.max_price is not None:
        stmt = stmt.where(Product.price <= f.max_price)
    if f.min_rating is not None:
        stmt = stmt.where(Product.rating >= f.min_rating)
    if f.in_stock:
        stmt = stmt.where(Product.stock > 0)
    if f.seller_id is not None:
        stmt = stmt.where(Product.seller_id == f.seller_id)
    return stmt


def search_products(db: Session, f: ProductFilters, page: int = 1, page_size: int = 12) -> tuple[list[Product], int]:
    base = _apply(select(Product), f, db)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    stmt = base.options(*_LOAD).order_by(*_ORDER[f.sort]()).limit(page_size).offset((page - 1) * page_size)
    return list(db.scalars(stmt).all()), total


def get_product(db: Session, product_id: int) -> Product | None:
    return db.scalar(
        select(Product)
        .where(Product.id == product_id)
        .options(*_LOAD, selectinload(Product.specs), selectinload(Product.options), selectinload(Product.seller))
    )


def get_by_ids(db: Session, ids: list[int]) -> dict[int, Product]:
    rows = db.scalars(select(Product).where(Product.id.in_(ids)).options(*_LOAD)).all()
    return {p.id: p for p in rows}
