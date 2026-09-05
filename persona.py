"""Janet's voice, and the payload the model is asked to continue.

This is the file a human edits by ear. No SDK mechanics live here: the payload
is plain dicts, and `completion` is what knows how to send them.

It starts nearly empty because Janet has no written voice yet. #6 fills in the
prompt and the example exchanges, which is the whole product; `build_payload`
needs no change when that happens.
"""

from __future__ import annotations

import random
from typing import Sequence

from presence import ExchangeMessage

# Written in #6. While empty, the payload is the Resident's message alone,
# which is exactly what Janet sent before the split.
SYSTEM_PROMPT = ""

# Four or five exchanges, written in #6. Cadence carries the character; a
# description of a voice does not.
EXAMPLES: tuple[ExchangeMessage, ...] = ()

# The two things she says that the model never generates: the goodbye, and the
# glitch for when it cannot be reached at all. Placeholder wording, like the
# prompt above. #6 owns how she actually sounds.
GOODBYE = "Okay! Bye!"

# More than one glitch line on purpose (#7). A repeated failure that repeats a
# single string reads as a stuck bot rather than as a character. They live here
# rather than beside the retry because they are her voice, and none of them
# claims to have answered: ADR 0002 lets her be broken, not misleading.
GLITCHES: tuple[str, ...] = (
    "Oh no. Something in me isn't working. Try me again in a second!",
    "Hmm! I can't get to that right now, and I don't love that.",
    "Sorry! I've gone completely blank. Ask me again?",
    "Something is wrong with me and I don't know what. Give me a moment!",
)

# The line she used last, so the next one differs. Module state because a
# glitch has no Exchange to hang off: it is deliberately not recalled (#7), and
# a failure that repeats is exactly when the repetition would show.
_last_glitch: str | None = None


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


def glitch() -> str:
    """One of her glitch lines, never the one she used last."""
    # Random beyond that one rule, so a channel watching her fail twice does
    # not learn the cycle. Falls back to the whole set if there is only one
    # line, which keeps this honest if someone trims the tuple.
    global _last_glitch
    choices = [line for line in GLITCHES if line != _last_glitch] or list(GLITCHES)
    _last_glitch = random.choice(choices)
    return _last_glitch
