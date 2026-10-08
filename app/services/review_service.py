from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError
from app.models import Order, OrderItem, OrderStatus, Product, Review, User


def add_review(db: Session, user: User, product_id: int, rating: int, comment: str) -> Review:
    if db.get(Product, product_id) is None:
        raise NotFoundError("Product not found")
    bought = db.scalar(
        select(func.count())
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.customer_id == user.id, OrderItem.product_id == product_id, Order.status == OrderStatus.delivered)
    )
    if not bought:
        raise AppError("You can review a product after it has been delivered to you", code="review_not_allowed", status_code=403)
    if db.scalar(select(Review).where(Review.product_id == product_id, Review.user_id == user.id)):
        raise ConflictError("You already reviewed this product")
    r = Review(product_id=product_id, user_id=user.id, rating=rating, comment=comment)
    db.add(r)
    db.flush()
    recompute_rating(db, product_id)
    db.commit()
    return r


def recompute_rating(db: Session, product_id: int) -> None:
    avg, n = db.execute(select(func.avg(Review.rating), func.count(Review.id)).where(Review.product_id == product_id)).one()
    p = db.get(Product, product_id)
    p.rating = round(float(avg or 0), 2)
    p.review_count = n


def list_reviews(db: Session, product_id: int) -> list[Review]:
    return list(db.scalars(select(Review).where(Review.product_id == product_id).order_by(Review.id.desc())).all())
