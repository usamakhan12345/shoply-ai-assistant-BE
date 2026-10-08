"""The tool executor: the single gate between "the model asked for X" and "the app does X".

Order of checks for every tool call the model makes:
  1. Is the tool on the allow-list?              (registry)
  2. Does it need a user, and is there one?      (JWT-derived ctx.user - checked BEFORE any DB access)
  3. Are the arguments valid?                    (pydantic, extra fields forbidden)
  4. Run the handler through the service layer   (which enforces roles, ownership, stock...)
  5. Convert any failure into a tool result the model can read - never a crash, never a stack trace.
"""
import logging

from pydantic import ValidationError

from app.agents.state.state import AgentState
from app.agents.tools.base import ToolResult
from app.agents.tools.registry import TOOLS
from app.core.errors import AppError

log = logging.getLogger(__name__)


def execute_tool(state: AgentState, name: str, arguments: dict) -> ToolResult:
    tool = TOOLS.get(name)
    if tool is None:
        return ToolResult(data={"error": f"Unknown tool '{name}'"}, error="unknown_tool")

    if (tool.mutating or tool.requires_login) and state.ctx.user is None:
        state.requires_login = True
        return ToolResult(
            data={"error": "login_required", "message": "The user is not logged in. Ask them to log in first."},
            error="login_required",
            login_required=True,
        )

    try:
        args = tool.args_model.model_validate(arguments)
    except ValidationError as e:
        msg = "; ".join(f"{'.'.join(map(str, err['loc'])) or 'arguments'}: {err['msg']}" for err in e.errors())
        return ToolResult(data={"error": f"Invalid arguments: {msg}"}, error="invalid_arguments")

    try:
        return tool.handler(state.ctx, args)
    except AppError as e:  # business-rule failure (stock, forbidden, not found...) -> readable by the model
        state.ctx.db.rollback()
        return ToolResult(data={"error": e.message, "code": e.code}, error=e.code)
    except Exception:
        state.ctx.db.rollback()
        log.exception("agent tool %s crashed", name)
        return ToolResult(data={"error": "Internal error while running the tool"}, error="internal_error")
