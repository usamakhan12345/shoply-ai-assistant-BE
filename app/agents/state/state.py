"""The agent's working memory for one chat turn (plus what is persisted between turns)."""
from dataclasses import dataclass, field
from typing import Any

from app.agents.tools.base import ToolContext

# Message format used everywhere inside the agent (provider adapters convert to/from this):
#   {"role": "user",      "content": "..."}
#   {"role": "assistant", "content": "...", "tool_calls": [{"id": "c1", "name": "search_products", "arguments": {...}}]}
#   {"role": "tool",      "tool_call_id": "c1", "name": "search_products", "content": "<json>"}
Message = dict[str, Any]


@dataclass
class AgentState:
    ctx: ToolContext
    messages: list[Message]  # conversation so far (no system prompt; it is rebuilt every turn)
    last_products: list[dict] = field(default_factory=list)  # [{"id", "title", "price"}] - what the user can refer to as "the second one"
    last_orders: list[dict] = field(default_factory=list)  # [{"id", "status"}] - "my first order", "pehla order"
    # ---- produced during this turn, returned to the frontend ----
    ui_products: list = field(default_factory=list)  # ORM Product rows -> rendered as product cards
    ui_orders: list = field(default_factory=list)  # ORM Order rows -> rendered as order cards
    ui_action: dict | None = None  # structured UI instruction, e.g. NAVIGATE
    actions: list[dict] = field(default_factory=list)  # [{"tool", "status", "detail"}] -> "tool/action indication"
    requires_login: bool = False
    steps: int = 0
    reply: str = ""
