from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_customer
from app.api.serializers import cart_out
from app.db.session import get_db
from app.models import User
from app.schemas.cart_order import CartItemIn, CartItemUpdate, CartOut
from app.services import cart_service

router = APIRouter(prefix="/cart", tags=["cart"])


@router.get("", response_model=CartOut)
def get_cart(user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return cart_out(cart_service.get_cart(db, user))


@router.post("/items", response_model=CartOut, status_code=201)
def add_item(data: CartItemIn, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    cart_service.add_item(db, user, data.product_id, data.quantity)
    return cart_out(cart_service.get_cart(db, user))


@router.put("/items/{item_id}", response_model=CartOut)
def update_item(item_id: int, data: CartItemUpdate, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    cart_service.set_quantity(db, user, item_id, data.quantity)
    return cart_out(cart_service.get_cart(db, user))


@router.delete("/items/{item_id}", response_model=CartOut)
def delete_item(item_id: int, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    cart_service.remove_item(db, user, item_id)
    return cart_out(cart_service.get_cart(db, user))
