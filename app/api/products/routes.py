from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_customer, require_seller
from app.core.errors import NotFoundError
from app.db.session import get_db
from app.models import Category, User
from app.repositories import product_repository as repo
from app.schemas.common import Page
from app.schemas.product import (
    CategoryTree,
    ProductCard,
    ProductDetail,
    ProductIn,
    ProductUpdate,
    ReviewIn,
    ReviewOut,
    SortKey,
)
from app.services import product_service, review_service

router = APIRouter(tags=["products"])


@router.get("/categories", response_model=list[CategoryTree])
def categories(db: Session = Depends(get_db)):
    stmt = select(Category).where(Category.parent_id.is_(None)).options(selectinload(Category.children)).order_by(Category.name)
    return db.scalars(stmt).all()


@router.get("/products", response_model=Page[ProductCard])
def list_products(
    q: str | None = Query(None, max_length=100),
    category: str | None = None,
    min_price: Decimal | None = Query(None, ge=0),
    max_price: Decimal | None = Query(None, ge=0),
    min_rating: float | None = Query(None, ge=0, le=5),
    in_stock: bool = False,
    sort: SortKey = SortKey.newest,
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
):
    f = repo.ProductFilters(q=q, category=category, min_price=min_price, max_price=max_price, min_rating=min_rating, in_stock=in_stock, sort=sort)
    items, total = repo.search_products(db, f, page, page_size)
    return Page(items=items, total=total, page=page, page_size=page_size, pages=max(1, -(-total // page_size)))


@router.get("/products/{product_id}", response_model=ProductDetail)
def product_detail(product_id: int, db: Session = Depends(get_db)):
    p = repo.get_product(db, product_id)
    if p is None:
        raise NotFoundError("Product not found")
    return p


@router.post("/products", response_model=ProductDetail, status_code=201)
def create_product(data: ProductIn, seller: User = Depends(require_seller), db: Session = Depends(get_db)):
    return product_service.create_product(db, seller, data)


@router.put("/products/{product_id}", response_model=ProductDetail)
def update_product(product_id: int, data: ProductUpdate, seller: User = Depends(require_seller), db: Session = Depends(get_db)):
    return product_service.update_product(db, seller, product_id, data)


@router.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, seller: User = Depends(require_seller), db: Session = Depends(get_db)):
    product_service.delete_product(db, seller, product_id)


@router.get("/products/{product_id}/reviews", response_model=list[ReviewOut])
def reviews(product_id: int, db: Session = Depends(get_db)):
    return [ReviewOut(id=r.id, rating=r.rating, comment=r.comment, created_at=r.created_at, reviewer=r.user.full_name) for r in review_service.list_reviews(db, product_id)]


@router.post("/products/{product_id}/reviews", response_model=ReviewOut, status_code=201)
def add_review(product_id: int, data: ReviewIn, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    r = review_service.add_review(db, user, product_id, data.rating, data.comment)
    return ReviewOut(id=r.id, rating=r.rating, comment=r.comment, created_at=r.created_at, reviewer=user.full_name)
