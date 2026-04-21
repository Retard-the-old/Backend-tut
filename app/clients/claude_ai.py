from __future__ import annotations
import anthropic
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Tutorii AI, a friendly and knowledgeable tutoring assistant. "
    "You help students learn by explaining concepts clearly, providing examples, "
    "answering questions, and guiding them through exercises. "
    "Be encouraging, break complex topics into digestible parts, use analogies, "
    "and stay on topic when discussing a specific lesson."
)

class ClaudeClient:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.CLAUDE_MODEL
        self.max_tokens = settings.CLAUDE_MAX_TOKENS

    async def chat(self, messages: list[dict], system: str | None = None, lesson_context: str | None = None) -> dict:
        sys_text = system or SYSTEM_PROMPT
        if lesson_context:
            sys_text += f"\n\nCurrent lesson context:\n{lesson_context}"

        # Pass system as a structured block with cache_control so Anthropic caches it.
        # Cache hits cost ~10% of normal input token price and last 5 min (refreshed on use).
        system_block = [
            {
                "type": "text",
                "text": sys_text,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        response = await self.client.messages.create(
            model=self.model, max_tokens=self.max_tokens,
            system=system_block, messages=messages,
        )
        content = response.content[0].text if response.content else ""
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_creation_tokens": getattr(response.usage, "cache_creation_input_tokens", 0),
            "cache_read_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
        }
        if usage["cache_read_tokens"]:
            logger.info(f"Prompt cache hit: {usage['cache_read_tokens']} tokens read from cache")
        return {"content": content, "usage": usage}

claude_client = ClaudeClient()
