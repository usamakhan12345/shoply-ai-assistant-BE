from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_optional_user
from app.db.session import get_db
from app.models import User
from app.schemas.agent import OrderBrief, UiAction
from app.schemas.product import ProductCard
from app.services import agent_service

router = APIRouter(prefix="/agent", tags=["agent"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = Field(default=None, max_length=36)


class ActionOut(BaseModel):
    tool: str
    status: str
    detail: str | None = None


class ChatOut(BaseModel):
    conversation_id: str
    reply: str
    products: list[ProductCard]
    orders: list[OrderBrief]
    action: UiAction | None  # optional UI instruction, e.g. {"type": "NAVIGATE", "route": "/checkout"}
    actions: list[ActionOut]  # which tools ran (for the small "what the AI did" chips)
    requires_login: bool
    cart_changed: bool


@router.post("/chat", response_model=ChatOut)
def chat(data: ChatIn, user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    """Open to guests (they can browse via the agent); account actions need a valid JWT.
    The user identity comes ONLY from the Authorization header - never from the request body or the LLM."""
    return agent_service.chat(db, user, data.message.strip(), data.conversation_id)
