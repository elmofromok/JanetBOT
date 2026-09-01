"""Whether Janet is Present, and what an incoming message means.

The deep seam. Given the channel's current record, the facts of a message and
the current time, `decide` hands back a decision and the next record. It reads
no clock, touches no network, imports neither `discord` nor `openai`, and never
composes or sends reply text: everything that crosses this interface is plain
data. That is what lets #11 test these rules without a fake Discord client.

The rules, in the order `decide` applies them: bots are ignored in every state
and so are direct messages; two minutes of silence dismisses her where she
stands; the summoner is answered until she is dismissed; anyone else summons
her or is ignored. What she then says is `persona`'s business, not this file's.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Union

# Her name on word boundaries, so `janet`, `Janet!` and `Janet's` summon while
# `Janette` and `planetary` do not.
SUMMONED_BY_NAME = re.compile(r"\bjanet\b", re.IGNORECASE)

# How long she waits before the silence dismisses her. Measured from when she
# last spoke in the channel, so other traffic does not extend her presence.
DISMISS_AFTER = timedelta(minutes=2)

# One channel, one reply every few seconds. Insurance against the flood nobody
# thought of, which bare-word summoning makes possible.
COOLDOWN = timedelta(seconds=3)

# Matched against the whole message, never as a substring. Every phrase carries
# her name on purpose: a bare "thanks" passes between Residents constantly and
# would dismiss her by accident.
DISMISSALS = frozenset(
    {
        "bye janet",
        "goodbye janet",
        "thanks janet",
        "thank you janet",
        "that's all janet",
    }
)


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
    anyone else replaces it (ADR 0005).

    The two instants differ in one case. `idle_from` is when Janet last spoke
    here, except at a Summon whose reply the cooldown dropped, which starts a
    presence anyway so the Resident is not left guessing. `last_spoke` is only
    ever a message she really sent, which is what the cooldown is about.
    """

    resident_id: int
    exchange: tuple[ExchangeMessage, ...]
    idle_from: datetime
    last_spoke: datetime | None


@dataclass(frozen=True)
class Reply:
    """Answer with the model, given these Exchange messages."""

    exchange: tuple[ExchangeMessage, ...]


@dataclass(frozen=True)
class Goodbye:
    """Say the canned goodbye. Janet is no longer Present.

    Only an explicit dismissal earns one, and the cooldown never suppresses it.
    Being dismissed by the silence is a vanishing: she says nothing at all.
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
    # Every bot, hers included: `from_janet` is the same message twice while she
    # runs as a bot account, and the guard that holds if she ever does not.
    # Bare-word summoning turns any bot that says her name into a loop, and a
    # bot in the channel must not disturb an Exchange either way.
    if message.from_bot or message.from_janet:
        return Nothing(), record
    if not message.in_server:
        return Nothing(), record

    if record is not None and now - record.idle_from >= DISMISS_AFTER:
        record = None

    dismissal = _normalise(message.text) in DISMISSALS

    if record is not None and record.resident_id == message.resident_id:
        if dismissal:
            return Goodbye(), None
        return _answer(record, message, now)

    # Not Present, or a message from someone who is not the summoner.
    if dismissal:
        # A dismissal carries her name, so without this it would summon her and
        # dismiss her in the same breath.
        return Nothing(), record
    if message.mentions_janet or SUMMONED_BY_NAME.search(message.text):
        return _summon(record, message, now)
    return Nothing(), record


def _summon(
    record: Presence | None,
    message: IncomingMessage,
    now: datetime,
) -> tuple[Decision, Presence]:
    """Hand the channel to this Resident, taking it from whoever held it."""
    began = Presence(
        resident_id=message.resident_id,
        exchange=(_heard(message),),
        # Presence starts at the Summon whether or not the reply survives the
        # cooldown, so a dropped Summon is not invisible.
        idle_from=now,
        # Carried through the takeover, so a rush of Summons cannot outrun the
        # cooldown by each starting a fresh presence. A dismissal does not
        # carry it: the goodbye stands outside the cooldown in both
        # directions, and she may answer a Summon straight after one.
        last_spoke=record.last_spoke if record is not None else None,
    )
    return _speak(began, now)


def _answer(
    record: Presence,
    message: IncomingMessage,
    now: datetime,
) -> tuple[Decision, Presence]:
    """Answer the summoner, who needs no further summoning."""
    # Replacing rather than appending: the Exchange holds the message she is
    # answering and nothing else until Exchange Recall (#5) accumulates it.
    # Heard before the cooldown is consulted, because a message she was too
    # busy to answer is still part of the Exchange (#5 again).
    return _speak(replace(record, exchange=(_heard(message),)), now)


def _speak(record: Presence, now: datetime) -> tuple[Decision, Presence]:
    """Reply, unless the cooldown says Janet has only just spoken here."""
    if record.last_spoke is not None and now - record.last_spoke < COOLDOWN:
        # Dropped, never queued. A queued reply lands after the conversation
        # has moved on. She did not speak, so this does not extend presence.
        return Nothing(), record
    return Reply(record.exchange), replace(record, idle_from=now, last_spoke=now)


def _heard(message: IncomingMessage) -> ExchangeMessage:
    return ExchangeMessage(from_janet=False, text=message.text)


def _normalise(text: str) -> str:
    """Reduce a message to the form the dismissal phrases are written in."""
    # Forgiving about case, spacing, a curly apostrophe and a trailing "!",
    # which is cheap to get wrong: the silence dismisses her anyway.
    return " ".join(text.replace("’", "'").lower().split()).rstrip("!.?,")
