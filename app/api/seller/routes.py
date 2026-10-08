import secrets
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import require_seller
from app.api.serializers import order_out
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models import OrderStatus, User
from app.repositories import product_repository as repo
from app.schemas.cart_order import OrderOut, StatusUpdateIn
from app.schemas.common import Page
from app.schemas.product import ProductCard, SortKey
from app.services import order_service, product_service

# One router-level dependency: nothing below is reachable unless the caller is a seller.
router = APIRouter(prefix="/seller", tags=["seller"], dependencies=[Depends(require_seller)])

_ALLOWED_IMAGES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
_MAX_BYTES = 5 * 1024 * 1024


@router.get("/stats")
def stats(seller: User = Depends(require_seller), db: Session = Depends(get_db)):
    return product_service.seller_stats(db, seller)


@router.get("/products", response_model=Page[ProductCard])
def my_products(
    q: str | None = None,
    sort: SortKey = SortKey.newest,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
):
    f = repo.ProductFilters(q=q, seller_id=seller.id, sort=sort)
    items, total = repo.search_products(db, f, page, page_size)
    return Page(items=items, total=total, page=page, page_size=page_size, pages=max(1, -(-total // page_size)))


@router.get("/orders", response_model=list[OrderOut])
def seller_orders(status: OrderStatus | None = None, seller: User = Depends(require_seller), db: Session = Depends(get_db)):
    return [order_out(o, for_seller=True) for o in order_service.list_seller_orders(db, seller, status)]


@router.get("/orders/{order_id}", response_model=OrderOut)
def seller_order(order_id: int, seller: User = Depends(require_seller), db: Session = Depends(get_db)):
    return order_out(order_service.get_seller_order(db, seller, order_id), for_seller=True)


@router.patch("/orders/{order_id}/status", response_model=OrderOut)
def update_status(order_id: int, data: StatusUpdateIn, seller: User = Depends(require_seller), db: Session = Depends(get_db)):
    return order_out(order_service.update_status(db, seller, order_id, data.status), for_seller=True)


@router.post("/uploads", status_code=201)
async def upload_image(file: UploadFile = File(...)):
    ext = _ALLOWED_IMAGES.get(file.content_type or "")
    if not ext:
        raise AppError("Only JPEG, PNG, WebP or GIF images are allowed", code="invalid_file_type")
    data = await file.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        raise AppError("Image must be 5 MB or smaller", code="file_too_large", status_code=413)
    folder = Path(get_settings().UPLOAD_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(8)}{ext}"  # server-chosen name: the client filename is never used
    (folder / name).write_bytes(data)
    return {"url": f"/uploads/{name}"}
