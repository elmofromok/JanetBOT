"""Janet's voice, and the payload the model is asked to continue.

This is the file a human edits by ear. No SDK mechanics live here: the payload
is plain dicts, and `completion` is what knows how to send them.

It starts nearly empty because Janet has no written voice yet. #6 fills in the
prompt and the example exchanges, which is the whole product; `build_payload`
needs no change when that happens.
"""

from __future__ import annotations

from typing import Sequence

from presence import ExchangeMessage

# Written in #6. While empty, the payload is the Resident's message alone,
# which is exactly what Janet sent before the split.
SYSTEM_PROMPT = ""

# Four or five exchanges, written in #6. Cadence carries the character; a
# description of a voice does not.
EXAMPLES: tuple[ExchangeMessage, ...] = ()

# What she says on being dismissed, and the one line she has that the model
# never sees. Placeholder wording: #6 owns how she actually sounds.
GOODBYE = "Okay! Bye!"


def build_payload(exchange: Sequence[ExchangeMessage]) -> list[dict[str, str]]:
    """Build the message list for a completion from the Exchange so far."""
    payload: list[dict[str, str]] = []
    if SYSTEM_PROMPT:
        payload.append({"role": "system", "content": SYSTEM_PROMPT})
    payload.extend(_as_chat_message(message) for message in EXAMPLES)
    payload.extend(_as_chat_message(message) for message in exchange)
    return payload


def _as_chat_message(message: ExchangeMessage) -> dict[str, str]:
    if message.speaker is None:
        return {"role": "assistant", "content": message.text}
    # Named, so she can tell the summoner from a bystander and answer people
    # by name. A chat payload has one "user" and the Exchange has a channel
    # full of them.
    return {"role": "user", "content": f"{message.speaker}: {message.text}"}
