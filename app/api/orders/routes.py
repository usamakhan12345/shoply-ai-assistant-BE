from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_customer
from app.api.serializers import order_out
from app.db.session import get_db
from app.models import User
from app.schemas.cart_order import CheckoutIn, OrderOut
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=list[OrderOut], status_code=201)
def place_order(data: CheckoutIn, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    """Returns a list: a cart with items from N sellers becomes N orders."""
    return [order_out(o) for o in order_service.checkout(db, user, data.address, data.payment_method)]


@router.get("", response_model=list[OrderOut])
def my_orders(user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return [order_out(o) for o in order_service.list_customer_orders(db, user)]


@router.get("/{order_id}", response_model=OrderOut)
def my_order(order_id: int, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return order_out(order_service.get_customer_order(db, user, order_id))
