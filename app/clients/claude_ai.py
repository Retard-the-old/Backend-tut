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
        sys_prompt = system or SYSTEM_PROMPT
        if lesson_context:
            sys_prompt += f"\n\nCurrent lesson context:\n{lesson_context}"
        response = await self.client.messages.create(
            model=self.model, max_tokens=self.max_tokens,
            system=sys_prompt, messages=messages,
        )
        content = response.content[0].text if response.content else ""
        usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
        return {"content": content, "usage": usage}

claude_client = ClaudeClient()
