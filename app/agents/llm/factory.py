from app.agents.llm.base import LLMClient
from app.agents.llm.mock import MockLLM
from app.agents.llm.openai_compat import OpenAICompatClient
from app.core.config import get_settings


def get_llm() -> LLMClient:
    s = get_settings()
    if s.LLM_PROVIDER == "openai":
        return OpenAICompatClient(s.LLM_API_KEY.get_secret_value(), s.LLM_MODEL, s.LLM_BASE_URL)
    return MockLLM()
