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

Every message she hears while Present is kept on the record as Exchange
Recall, whoever said it and whether or not she answered it. Discard on Dismiss
needs no code: the record dies and the recall dies with it.
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

# The most she carries into one payload, oldest dropped first. Insurance
# against a channel flood rather than a policy: two minutes is usually a
# handful of messages, and the concern is latency.
RECALL_CAP = 40

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
    """One message in an Exchange: a Resident's, or Janet's own reply.

    `speaker` is the Resident's display name, and None when Janet is the one
    who spoke. One field rather than a name beside a flag, so a message cannot
    claim to be hers and carry someone's name. Display names arrive as plain
    strings; resolving them from Discord is the wiring's job.
    """

    speaker: str | None
    text: str


@dataclass(frozen=True)
class IncomingMessage:
    """The facts of a message, with Discord stripped off.

    `text` is the message with Janet's mention markers already removed, since
    that markup is Discord's wire format and nothing here knows about Discord.
    A message from a bot has no Resident behind it, so `resident_id` and
    `speaker` only name one when `from_bot` is false.
    """

    resident_id: int
    speaker: str
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

    `exchange` is her recall: every message she has heard since the Summon that
    started this presence, hers included, capped at RECALL_CAP.

    Of the three instants, `began` never moves, and names this Exchange for
    `janet_said`. The other two differ in one case: `idle_from` is when Janet
    last spoke here, except at a Summon whose reply the cooldown dropped, which
    starts a presence anyway so the Resident is not left guessing. `last_spoke`
    is only ever a message she really sent, which is what the cooldown is
    about.
    """

    resident_id: int
    exchange: tuple[ExchangeMessage, ...]
    began: datetime
    idle_from: datetime
    last_spoke: datetime | None


@dataclass(frozen=True)
class Reply:
    """Answer with the model, given these Exchange messages.

    `began` names the Exchange being answered, so that what she says can be
    handed back to `janet_said` and land on the right one.
    """

    exchange: tuple[ExchangeMessage, ...]
    began: datetime


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

    # Not Present, or a message from someone who is not the summoner. She
    # answers none of these, and while Present she recalls all of them.
    if dismissal:
        # A dismissal carries her name, so without this it would summon her and
        # dismiss her in the same breath.
        return Nothing(), _overheard(record, message)
    if message.mentions_janet or SUMMONED_BY_NAME.search(message.text):
        return _summon(record, message, now)
    return Nothing(), _overheard(record, message)


def _summon(
    record: Presence | None,
    message: IncomingMessage,
    now: datetime,
) -> tuple[Decision, Presence]:
    """Hand the channel to this Resident, taking it from whoever held it."""
    began = Presence(
        resident_id=message.resident_id,
        # The Summon is the question she is answering, and nothing said before
        # it survives into the new Exchange. Reaching backwards is #14.
        exchange=(_heard(message),),
        began=now,
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
    # Recalled before the cooldown is consulted, because a message she was too
    # busy to answer is still part of the Exchange. A Janet who forgets what
    # you said because she was rate-limited is undiagnosable from the channel.
    return _speak(_recalled_by(record, message), now)


def _speak(record: Presence, now: datetime) -> tuple[Decision, Presence]:
    """Reply, unless the cooldown says Janet has only just spoken here."""
    if record.last_spoke is not None and now - record.last_spoke < COOLDOWN:
        # Dropped, never queued. A queued reply lands after the conversation
        # has moved on. She did not speak, so this does not extend presence.
        return Nothing(), record
    return (
        Reply(record.exchange, record.began),
        replace(record, idle_from=now, last_spoke=now),
    )


def janet_said(
    record: Presence | None,
    began: datetime,
    text: str,
) -> Presence | None:
    """Recall a reply Janet has just sent, so her own turns are in the payload.

    The caller reaches here after the model and the network, by which time she
    may have been dismissed or taken over. `began` is what tells the caller's
    Exchange from whichever one the channel holds now: a reply that outlived
    its Exchange is dropped rather than pushed onto a stranger's.
    """
    if record is None or record.began != began:
        return record
    return replace(
        record,
        exchange=_recalled(record.exchange, ExchangeMessage(speaker=None, text=text)),
    )


def _overheard(record: Presence | None, message: IncomingMessage) -> Presence | None:
    """Recall a message she hears but does not answer.

    Per ADR 0001 she reads the channel while Present, so a bystander's message
    is recalled although she never replies to it. While she is absent there is
    no Exchange for it to join, and it is gone.
    """
    if record is None:
        return None
    return _recalled_by(record, message)


def _recalled_by(record: Presence, message: IncomingMessage) -> Presence:
    """The record with this message added to what she recalls of the Exchange."""
    return replace(record, exchange=_recalled(record.exchange, _heard(message)))


def _recalled(
    exchange: tuple[ExchangeMessage, ...],
    message: ExchangeMessage,
) -> tuple[ExchangeMessage, ...]:
    """Add a message to the Exchange, keeping the most recent RECALL_CAP."""
    return (exchange + (message,))[-RECALL_CAP:]


def _heard(message: IncomingMessage) -> ExchangeMessage:
    return ExchangeMessage(speaker=message.speaker, text=message.text)


def _normalise(text: str) -> str:
    """Reduce a message to the form the dismissal phrases are written in."""
    # Forgiving about case, spacing, a curly apostrophe and a trailing "!",
    # which is cheap to get wrong: the silence dismisses her anyway.
    return " ".join(text.replace("’", "'").lower().split()).rstrip("!.?,")
