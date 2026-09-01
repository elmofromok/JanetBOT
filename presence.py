"""Whether Janet is Present, and what an incoming message means.

The deep seam. Given the channel's current record, the facts of a message and
the current time, `decide` hands back a decision and the next record. It reads
no clock, touches no network, imports neither `discord` nor `openai`, and never
composes or sends reply text: everything that crosses this interface is plain
data.

Today the body is trivial, because it reproduces what Janet already does:
reply when mentioned, otherwise nothing, with no record kept. The real rules
(bare-word summoning, the idle timeout, dismissal phrases, ignoring bots, the
cooldown) replace this body in #4, and their tests arrive with #11.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Union


@dataclass(frozen=True)
class ExchangeMessage:
    """One message in an Exchange: a Resident's, or Janet's own reply."""

    from_janet: bool
    text: str


@dataclass(frozen=True)
class IncomingMessage:
    """The facts of a message, with Discord stripped off.

    `text` is the message with Janet's mention markers already removed, since
    that markup is Discord's wire format and nothing here knows about Discord.
    A message from a bot has no Resident behind it, so `resident_id` only names
    one when `from_bot` is false.
    """

    resident_id: int
    from_bot: bool
    from_janet: bool
    channel_id: int
    text: str
    mentions_janet: bool
    in_server: bool


@dataclass(frozen=True)
class Presence:
    """Janet Present in one channel, holding one Exchange.

    One record per channel, owned by the Resident who summoned her: a Summon by
    anyone else replaces it (ADR 0005). Nothing constructs one yet; #4 does.
    """

    resident_id: int
    exchange: tuple[ExchangeMessage, ...]
    last_heard: datetime


@dataclass(frozen=True)
class Reply:
    """Answer with the model, given these Exchange messages."""

    exchange: tuple[ExchangeMessage, ...]


@dataclass(frozen=True)
class Goodbye:
    """Say the canned goodbye. Janet is no longer Present.

    Nothing returns this yet: #4 decides when she is dismissed, and #6 writes
    the line she leaves on.
    """


@dataclass(frozen=True)
class Nothing:
    """Stay quiet."""


Decision = Union[Reply, Goodbye, Nothing]


def decide(
    record: Presence | None,
    message: IncomingMessage,
    now: datetime,
) -> tuple[Decision, Presence | None]:
    """Decide what the message means, and what the channel's record becomes."""
    # Hearing herself is the loop risk that already exists. #4 widens this to
    # every bot, which is the wider risk that bare-word summoning creates.
    if message.from_janet:
        return Nothing(), None
    if message.mentions_janet:
        return Reply((ExchangeMessage(from_janet=False, text=message.text),)), None
    return Nothing(), None
