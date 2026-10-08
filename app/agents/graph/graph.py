"""Runs the node graph until it reaches END. (A tiny hand-written equivalent of what LangGraph's
StateGraph does - kept explicit so you can read the whole control flow in 10 lines.)"""
from app.agents.graph.nodes import END, NODES
from app.agents.llm.base import LLMClient
from app.agents.state.state import AgentState


def run_agent(state: AgentState, llm: LLMClient, entry: str = "call_llm") -> AgentState:
    node = entry
    while node != END:
        node = NODES[node](state, llm)
    return state
