"""Optional LLM augmentation layer.

Agents are fully functional on deterministic heuristics. When an Anthropic API
key is configured, `LLMClient.complete()` returns a Claude-generated string that
agents fold into their reasoning (e.g. executive summaries, richer rationales).
Without a key, `available` is False and agents skip the call entirely — so the
platform always runs offline.
"""
from __future__ import annotations

from typing import Optional

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMClient:
    def __init__(self) -> None:
        self._client = None
        if settings.llm_enabled:
            try:
                import anthropic  # lazy

                self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
                logger.info("LLM augmentation enabled (model=%s)", settings.LLM_MODEL)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Anthropic client init failed (%s); LLM disabled", exc)

    @property
    def available(self) -> bool:
        return self._client is not None

    def complete(
        self, prompt: str, system: str = "", max_tokens: int = 700
    ) -> Optional[str]:
        if not self.available:
            return None
        try:
            msg = self._client.messages.create(
                model=settings.LLM_MODEL,
                max_tokens=max_tokens,
                system=system or "You are an expert SRE incident analyst.",
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(
                block.text for block in msg.content if block.type == "text"
            ).strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM completion failed (%s); using heuristic only", exc)
            return None


_client: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
