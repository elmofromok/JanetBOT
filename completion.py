"""The one place the OpenAI SDK is used.

Payload in, reply out. Here for locality rather than leverage: #2 moved the SDK
and the model under the repo at once, and the point of a single adapter is that
the next churn of that kind lands in one file.
"""

from __future__ import annotations

from typing import cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

import config

MODEL = "gpt-5.6-luna"

client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)


async def complete(payload: list[dict[str, str]]) -> str | None:
    """Ask the model to continue the payload, and return what it said."""
    # gpt-5.6-luna is a reasoning model: it rejects temperature, and its
    # reasoning tokens come out of the same budget as the reply. Effort is off
    # so the whole budget is spent on what the Resident actually reads, and so
    # a Summon stays as fast as the model was picked to be.
    response = await client.chat.completions.create(
        model=MODEL,
        # Plain role/content dicts, which is what the SDK's message params are.
        messages=cast(list[ChatCompletionMessageParam], payload),
        max_completion_tokens=1024,
        reasoning_effort="none",
    )
    return response.choices[0].message.content
