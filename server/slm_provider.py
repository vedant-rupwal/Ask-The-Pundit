import os
from dataclasses import dataclass
from typing import Iterable

import httpx


INSUFFICIENT_CONTEXT_RESPONSE = "I do not have enough retrieved scripture to answer that."


@dataclass
class SlmRequest:
    user_question: str
    visible_screen_text: str
    retrieved_context: str
    citation: str


class BaseSlmProvider:
    name = "base"

    def generate(self, request: SlmRequest) -> str:
        raise NotImplementedError


class MockSlmProvider(BaseSlmProvider):
    name = "mock_slm"

    def generate(self, request: SlmRequest) -> str:
        if not request.retrieved_context.strip() or (
            request.retrieved_context.strip()
            == "No relevant scripture passages were retrieved."
        ):
            return INSUFFICIENT_CONTEXT_RESPONSE

        first_text = _first_retrieved_text(request.retrieved_context)
        answer = (
            "Mock Pandit SLM answer: based on the retrieved scripture, "
            f"{first_text}"
        )
        if request.citation:
            answer += f"\n\nCitation: {request.citation}"
        return answer


class LocalSlmProvider(BaseSlmProvider):
    name = "local_slm"

    def __init__(self, endpoint: str | None = None):
        self.endpoint = endpoint or os.getenv("LOCAL_SLM_ENDPOINT")
        self.fallback = MockSlmProvider()

    def generate(self, request: SlmRequest) -> str:
        if not self.endpoint:
            return self.fallback.generate(request)

        payload = {
            "role": "Scripture Scholar",
            "user_question": request.user_question,
            "visible_screen_text": request.visible_screen_text,
            "retrieved_context": request.retrieved_context,
            "citation": request.citation,
            "rules": [
                "Answer only from retrieved_context.",
                f"If context is insufficient, reply: {INSUFFICIENT_CONTEXT_RESPONSE}",
                "Include citations when available.",
            ],
        }

        response = httpx.post(self.endpoint, json=payload, timeout=60.0)
        response.raise_for_status()
        data = response.json()
        answer = data.get("answer") if isinstance(data, dict) else None
        if not answer:
            return INSUFFICIENT_CONTEXT_RESPONSE
        return str(answer)


def get_slm_provider(provider_name: str | None = None) -> BaseSlmProvider:
    selected = (provider_name or os.getenv("SLM_PROVIDER") or "hf_router").strip()
    if selected == "mock_slm":
        return MockSlmProvider()
    if selected == "local_slm":
        return LocalSlmProvider()
    raise ValueError(
        f"Unknown non-HF SLM provider '{selected}'. "
        "Use 'hf_router', 'mock_slm', or 'local_slm'."
    )


def stream_text(text: str) -> Iterable[str]:
    yield text


def _first_retrieved_text(retrieved_context: str, max_chars: int = 600) -> str:
    for block in retrieved_context.split("\n\n"):
        marker = "Text:"
        if marker in block:
            text = block.split(marker, 1)[1].strip()
            return _truncate_sentence(text, max_chars)
    return _truncate_sentence(retrieved_context.strip(), max_chars)


def _truncate_sentence(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 5].rstrip() + "[...]"
