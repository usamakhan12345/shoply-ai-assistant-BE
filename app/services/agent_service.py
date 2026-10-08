"""Glue between the HTTP endpoint and the agent graph: conversation memory + response shaping."""
import copy

from sqlalchemy.orm import Session

from app.agents.graph.graph import run_agent
from app.agents.llm.base import LLMClient, LLMError
from app.agents.llm.factory import get_llm
from app.agents.state.state import AgentState
from app.agents.tools.base import ToolContext
from app.core.errors import AppError
from app.models import AgentConversation, User

MAX_HISTORY = 24  # messages kept per conversation (context window control)


def _trim(messages: list[dict]) -> list[dict]:
    """Keep the tail, but always start on a user message so tool-call/tool-result pairs are never split."""
    if len(messages) <= MAX_HISTORY:
        return messages
    tail = messages[-MAX_HISTORY:]
    first_user = next((i for i, m in enumerate(tail) if m["role"] == "user"), 0)
    return tail[first_user:]


def _load(db: Session, conversation_id: str | None, user: User | None) -> AgentConversation:
    conv = db.get(AgentConversation, conversation_id) if conversation_id else None
    # A conversation owned by user A must never be continued by user B.
    if conv is not None and conv.user_id is not None and (user is None or conv.user_id != user.id):
        conv = None
    if conv is None:
        conv = AgentConversation(user_id=user.id if user else None, state={"messages": [], "last_products": []})
        db.add(conv)
        db.flush()
    elif conv.user_id is None and user is not None:
        conv.user_id = user.id  # guest logged in mid-conversation: adopt it, so "add it" works after login
    return conv


def chat(db: Session, user: User | None, message: str, conversation_id: str | None, llm: LLMClient | None = None) -> dict:
    llm = llm or get_llm()
    conv = _load(db, conversation_id, user)
    saved = copy.deepcopy(conv.state or {})
    state = AgentState(
        ctx=ToolContext(db=db, user=user),
        messages=[*saved.get("messages", []), {"role": "user", "content": message}],
        last_products=saved.get("last_products", []),
        last_orders=saved.get("last_orders", []),
    )
    try:
        run_agent(state, llm)
    except LLMError as e:
        db.rollback()
        raise AppError(f"The AI assistant is unavailable right now. ({e})", code="ai_unavailable", status_code=503)

    conv.state = {"messages": _trim(state.messages), "last_products": state.last_products, "last_orders": state.last_orders}
    db.commit()

    from app.schemas.agent import OrderBrief, UiAction
    from app.schemas.product import ProductCard

    return {
        "conversation_id": conv.id,
        "reply": state.reply or "Sorry, I didn't get that. Could you rephrase?",
        "products": [ProductCard.model_validate(p) for p in state.ui_products],
        "orders": [OrderBrief.from_order(o) for o in state.ui_orders],
        "action": UiAction(**state.ui_action) if state.ui_action else None,
        "actions": state.actions,
        "requires_login": state.requires_login,
        "cart_changed": any(a["tool"] in {"add_to_cart", "remove_from_cart", "update_cart_quantity"} and a["status"] == "ok" for a in state.actions),
    }
