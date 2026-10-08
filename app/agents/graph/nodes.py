"""The agent loop, split into small named nodes. Each node takes the state, does ONE thing, and
returns the name of the next node.

    ┌─────────────┐  tool calls?   ┌───────────┐
    │  call_llm   │ ─────yes─────► │ run_tools │
    │ (decide)    │ ◄──────────────│ (act)     │
    └─────┬───────┘   results      └───────────┘
          │ no tool calls
          ▼
        END  → state.reply is the final answer
"""
import json
import logging

from app.agents.graph.executor import execute_tool
from app.agents.llm.base import LLMClient
from app.agents.prompts.system import build_system_prompt
from app.agents.state.state import AgentState
from app.agents.tools.base import product_summary
from app.agents.tools.registry import llm_tool_schemas
from app.core.config import get_settings

log = logging.getLogger(__name__)
END = "__end__"


def call_llm(state: AgentState, llm: LLMClient) -> str:
    """DECIDE: show the model the conversation + tool menu; it answers with text and/or tool calls."""
    state.steps += 1
    system = build_system_prompt(state.ctx.db, state.ctx.user, state.last_products, state.last_orders)
    resp = llm.chat(system, state.messages, llm_tool_schemas())

    msg = {"role": "assistant", "content": resp.content}
    if resp.tool_calls:
        msg["tool_calls"] = [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in resp.tool_calls]
    state.messages.append(msg)

    if not resp.tool_calls:
        state.reply = resp.content.strip()
        return END
    if state.steps >= get_settings().AGENT_MAX_STEPS:
        # Safety valve against a model that keeps calling tools forever.
        state.reply = resp.content.strip() or "Sorry, I couldn't finish that request. Please try rephrasing."
        # Unanswered tool calls must still get a tool message, or the history becomes invalid for the next turn.
        for c in resp.tool_calls:
            state.messages.append({"role": "tool", "tool_call_id": c.id, "name": c.name, "content": json.dumps({"error": "step limit reached"})})
        return END
    return "run_tools"


def run_tools(state: AgentState, llm: LLMClient) -> str:
    """ACT: run each requested tool through the executor and feed the results back to the model."""
    for call in state.messages[-1]["tool_calls"]:
        result = execute_tool(state, call["name"], call["arguments"])
        state.actions.append({"tool": call["name"], "status": "error" if result.error else "ok", "detail": result.error})
        if result.products:
            # Remember what the user is now looking at, so "the second one" works next turn.
            state.ui_products = result.products
            state.last_products = [{"id": p.id, "title": p.title, "price": float(p.price)} for p in result.products]
        if result.orders:
            state.ui_orders = result.orders
            state.last_orders = [{"id": o.id, "status": o.status.value} for o in result.orders]
        if result.ui_action:
            state.ui_action = result.ui_action  # the last action wins; the frontend validates it before using it
        state.messages.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"], "content": json.dumps(result.data)})
    return "call_llm"


NODES = {"call_llm": call_llm, "run_tools": run_tools}
