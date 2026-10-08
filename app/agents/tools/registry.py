"""The allow-list. If a tool is not in this dict the agent cannot call it - period."""
from app.agents.tools.base import Tool
from app.agents.tools.cart_tools import CART_TOOLS
from app.agents.tools.catalog_tools import CATALOG_TOOLS
from app.agents.tools.nav_tools import NAV_TOOLS
from app.agents.tools.order_tools import ORDER_TOOLS

TOOLS: dict[str, Tool] = {t.name: t for t in [*CATALOG_TOOLS, *CART_TOOLS, *ORDER_TOOLS, *NAV_TOOLS]}


def llm_tool_schemas() -> list[dict]:
    return [t.llm_schema() for t in TOOLS.values()]
