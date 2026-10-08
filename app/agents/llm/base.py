"""LLM provider abstraction. The agent only talks to `LLMClient.chat`, so swapping OpenAI for a local
model (Ollama, LM Studio...) or the built-in mock is a config change (LLM_PROVIDER), not a code change."""
from dataclasses import dataclass, field
from typing import Protocol


class LLMError(Exception):
    """Raised when the provider is unreachable or returns garbage. Never contains secrets."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient(Protocol):
    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse: ...
