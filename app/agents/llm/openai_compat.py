"""Adapter for any OpenAI-compatible /chat/completions API (OpenAI, Ollama, LM Studio, vLLM, ...)."""
import json

import httpx

from app.agents.llm.base import LLMError, LLMResponse, ToolCall


class OpenAICompatClient:
    def __init__(self, api_key: str, model: str, base_url: str, timeout: float = 45.0):
        self._api_key, self._model, self._base_url, self._timeout = api_key, model, base_url.rstrip("/"), timeout

    @staticmethod
    def _to_wire(messages: list[dict]) -> list[dict]:
        wire = []
        for m in messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
                wire.append(
                    {
                        "role": "assistant",
                        "content": m.get("content") or None,
                        "tool_calls": [
                            {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}}
                            for c in m["tool_calls"]
                        ],
                    }
                )
            elif m["role"] == "tool":
                wire.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
            else:
                wire.append({"role": m["role"], "content": m["content"]})
        return wire

    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        body = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, *self._to_wire(messages)],
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.2,
        }
        try:
            r = httpx.post(f"{self._base_url}/chat/completions", headers=headers, json=body, timeout=self._timeout)
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            # Only the exception TYPE is surfaced: the message could contain the URL/headers.
            raise LLMError(f"LLM request failed ({type(e).__name__})") from None
        calls = []
        for c in msg.get("tool_calls") or []:
            try:
                args = json.loads(c["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {"__invalid_json__": True}  # fails pydantic validation -> model gets an error and can retry
            calls.append(ToolCall(id=c["id"], name=c["function"]["name"], arguments=args))
        return LLMResponse(content=msg.get("content") or "", tool_calls=calls)
