"""The one place the OpenAI SDK is used.

Payload in, reply out. Here for locality rather than leverage: #2 moved the SDK
and the model under the repo at once, and the point of a single adapter is that
the next churn of that kind lands in one file.

The retry lives here because this is the only module allowed to know the SDK's
exception types, which is what telling a transient failure from a permanent one
requires. It raises `Unavailable` and nothing else, so the wiring can catch a
failure without importing `openai`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import cast

import openai
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

import config

log = logging.getLogger(__name__)

MODEL = "gpt-5.6-luna"

# `max_retries=0` on purpose. The SDK retries transient failures twice by
# default, so leaving it alone would quietly make the one retry below three
# attempts on a backoff schedule nobody chose. Turned off so the policy in this
# file is the whole policy.
client = AsyncOpenAI(api_key=config.OPENAI_API_KEY, max_retries=0)

# How long to wait before the retry when the failure suggests nothing better.
PAUSE = 1.0

# The most a `Retry-After` can hold her, in seconds. She is answering a live
# conversation under a typing indicator, and a minute of that reads worse than
# a glitch now.
PAUSE_CAP = 5.0

# The sampling parameters, chosen in #6 because cadence is sensitive to them.
#
# `temperature` is not among them: gpt-5.6-luna is a reasoning model and
# rejects it outright, so there is no value to pick. Recorded here rather than
# left as an absence, so the next person to go looking for it stops here
# instead of adding one and getting a 400 on the first Summon.
#
# The budget is a backstop, not the thing that keeps her brief. The prompt does
# that. This is here because Discord refuses a message over 2000 characters
# with an HTTP 400, which would raise inside the handler and reach the channel
# as silence. 400 tokens is roughly 1600 characters of ordinary prose, so a
# reply long enough to be refused is one this cuts short first. Roughly: the
# ratio is a rule of thumb rather than a guarantee, and the guarantee would be
# a length check in the wiring, which no reply has ever needed.
REPLY_BUDGET = 400

# Worth trying again: the far side was busy, slow or briefly broken. Everything
# else the SDK raises is a configuration bug and fails identically the second
# time.
TRANSIENT = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


class Unavailable(Exception):
    """Janet could not answer. The only failure this module raises.

    Deliberately not an SDK exception and deliberately carrying no detail worth
    showing a Resident: the caller's whole decision is glitch or not, and #3's
    rule that the SDK lives in one module holds only if its exception types do
    not leak out with it. What went wrong goes to the log, where the Operator
    is the one who reads it.
    """


async def complete(payload: list[dict[str, str]]) -> str:
    """Ask the model to continue the payload, and return what it said.

    Raises `Unavailable` when she cannot answer, having retried once first if
    the failure was the kind a retry helps. One retry, never more: it absorbs
    most rate limits invisibly, and past that the honest answer is a glitch.
    """
    try:
        return await _ask(payload)
    except TRANSIENT as failure:
        pause = _pause_after(failure)
    except openai.OpenAIError as failure:
        # An authentication failure, an unknown model, a malformed request. No
        # retry: it fails the same way twice. Error level because it is the
        # Operator's to fix, not Janet's to absorb, and the log is the only
        # place it is ever reported.
        log.error("Janet cannot use the model as configured", exc_info=failure)
        raise Unavailable from failure

    await asyncio.sleep(pause)

    try:
        return await _ask(payload)
    except TRANSIENT as failure:
        # Warning rather than error: nothing is misconfigured, the far side was
        # busy twice running.
        log.warning("Janet could not reach the model, twice: %s", failure)
        raise Unavailable from failure
    except openai.OpenAIError as failure:
        log.error("Janet cannot use the model as configured", exc_info=failure)
        raise Unavailable from failure


async def _ask(payload: list[dict[str, str]]) -> str:
    """One attempt."""
    response = await client.chat.completions.create(
        model=MODEL,
        # Plain role/content dicts, which is what the SDK's message params are.
        messages=cast(list[ChatCompletionMessageParam], payload),
        max_completion_tokens=REPLY_BUDGET,
        # Off, so the whole budget is spent on what the Resident actually reads
        # and a Summon stays as fast as the model was picked to be. Her replies
        # are short and factual; there is nothing here for a reasoning pass to
        # improve, and it would come out of the same budget as the answer.
        reasoning_effort="none",
    )
    text = response.choices[0].message.content
    if text is None or not text.strip():
        # Reached, and said nothing. Not retried: it is not a transport failure
        # and the second sample is as likely to be empty as the first. Sending
        # it would post an empty message the channel reads as her having
        # answered, which is the thing ADR 0002 is about.
        log.warning("The model returned an empty reply")
        raise Unavailable("empty reply")
    return text


def _pause_after(failure: Exception) -> float:
    """How long to wait before the retry, honouring a `Retry-After` if given."""
    # Only the SDK's status errors carry a response, so a timeout or a dropped
    # connection lands on the fixed pause.
    response = getattr(failure, "response", None)
    header = response.headers.get("retry-after") if response is not None else None
    try:
        pause = float(header)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        # Absent, or an HTTP-date rather than a count of seconds. The date form
        # is legal and nothing here parses it; the fixed pause covers both.
        return PAUSE
    return min(max(pause, 0.0), PAUSE_CAP)
