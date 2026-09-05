"""What the wiring does with a message, driven through a fake channel.

`app` imports `config`, which ends the process on an empty environment, and
`completion`, which builds its OpenAI client at import, so a plausible
environment is set below before importing it. Nothing here reaches Discord or
the network: a message is a small object carrying the fields `read_message`
reads, and the channel records what it was asked to do instead of doing it.
The fakes carry Discord's names, because Discord is what they stand in for;
everything Janet reasons about is in CONTEXT.md's words.

`discord.Client.user` is a read-only property returning None until the client
connects, so every test replaces `janet` itself rather than setting its
`user`. `read_message` looks the module global up when it is called, which is
what makes that work, and it is why nothing in `app.py` had to change beyond
the entry point.

`presence` decides for real throughout. The point of this file is what the
wiring does with a decision, and a scripted `decide` would only test the fake.
The model is scripted, because it is the one thing here that would otherwise
cost money and a network.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Awaitable, Callable

import pytest

os.environ.setdefault("DISCORD_TOKEN", "token")
os.environ.setdefault("OPENAI_API_KEY", "key")
os.environ.setdefault("OPERATOR_ID", "1" * 18)

import app  # noqa: E402
import completion  # noqa: E402
import config  # noqa: E402
import persona  # noqa: E402
import presence  # noqa: E402


# --- The fakes --------------------------------------------------------

class Author:
    """Who wrote a message: a Resident, another bot, or Janet herself."""

    def __init__(self, author_id: int, display_name: str, bot: bool = False):
        self.id = author_id
        self.display_name = display_name
        self.bot = bot


ALICE = Author(1, "Alice")
BOB = Author(2, "Bob")
JANET = Author(999, "Janet", bot=True)
# Another bot in the channel. She runs as a bot account herself, so without
# one of these the `from_bot` guard hides the `from_janet` guard entirely.
DOORMAN = Author(3, "Doorman", bot=True)

CHANNEL = 100

# What the scripted model says. `TO_ALICE` and `TO_BOB` are for the one test
# where two Residents are being answered at once and which reply is whose is
# the thing under test.
REPLY = "Not a girl."
TO_ALICE = REPLY
TO_BOB = "Not a robot either."


class Typing:
    """`channel.typing()`, which is an async context manager in discord.py."""

    def __init__(self, events: list[tuple[str, str]]):
        self.events = events

    async def __aenter__(self) -> None:
        self.events.append(("typing", "up"))

    async def __aexit__(self, *failure: object) -> bool:
        self.events.append(("typing", "down"))
        return False


class Channel:
    """A channel that records what it was asked to do, in order.

    One list rather than a list of sends beside a typing flag, because half of
    #8's criteria are about ordering: that the indicator is up when the reply
    lands and down once it has.
    """

    def __init__(self, channel_id: int = CHANNEL):
        self.id = channel_id
        self.events: list[tuple[str, str]] = []

    def typing(self) -> Typing:
        return Typing(self.events)

    async def send(self, text: str) -> None:
        self.events.append(("said", text))

    @property
    def said(self) -> list[str]:
        return [text for kind, text in self.events if kind == "said"]


class Message:
    """A Discord message, carrying only what `read_message` reads."""

    def __init__(
        self,
        author: Author,
        text: str,
        channel: Channel,
        mentions: tuple[Author, ...] = (),
        in_server: bool = True,
    ):
        self.author = author
        self.content = text
        self.channel = channel
        self.mentions = list(mentions)
        # Only ever tested for None: a direct message has no Server behind it.
        self.guild = object() if in_server else None


def recalled(payload: list[dict[str, str]]) -> list[dict[str, str]]:
    """The Exchange within a payload, with her prompt and examples dropped.

    `persona.build_payload` puts those in front of every payload, and how many
    of them there are is #6's business. Measuring the front rather than
    asserting past it is what keeps these tests about the wiring: they broke
    once already, on the commit that gave her a voice.
    """
    return payload[len(persona.build_payload(())):]


def _contents(payload: list[dict[str, str]]) -> list[str]:
    """What the model was actually asked to read."""
    return [message["content"] for message in payload]


async def deliver(message: Message) -> None:
    """Hand Janet one message, the way discord.py's dispatch would."""
    await app.on_message(message)


def hear(message: Message) -> None:
    """Deliver one message, from a test that is not already in the loop."""
    asyncio.run(deliver(message))


class _Connected:
    """The one thing `read_message` needs of the client: who Janet is."""

    user = JANET


@pytest.fixture(autouse=True)
def connected(monkeypatch):
    """Janet as she is once connected, holding nothing from the last test.

    The channel records and the off switch are module state, which is right
    for a process running one Janet and wrong for a suite running many.
    """
    monkeypatch.setattr(app, "janet", _Connected())
    monkeypatch.setattr(app, "presences", {})
    monkeypatch.setattr(app, "answering", True)


@pytest.fixture
def channel() -> Channel:
    return Channel()


@pytest.fixture
def no_cooldown(monkeypatch):
    """Run the cooldown out, for a test that needs her to answer twice.

    `on_message` reads the clock itself, so the alternative is three real
    seconds of `sleep` to get past a rule `tests/test_presence.py` already
    covers. The one test here that is about the cooldown does without this.
    """
    monkeypatch.setattr(presence, "COOLDOWN", timedelta(0))


class Model:
    """The model, scripted. Each turn is a reply to send or a failure to raise.

    Keeps every payload it was given, because what she recalls of an Exchange
    is only observable in the next one.
    """

    def __init__(self, *turns: str | Exception):
        self.turns = list(turns)
        self.payloads: list[list[dict[str, str]]] = []
        # Awaited once, inside the completion call, so a test can see the
        # channel as it is while Janet is thinking, or say something in it.
        self.meanwhile: Callable[[], Awaitable[None]] | None = None

    async def complete(self, payload: list[dict[str, str]]) -> str:
        self.payloads.append(payload)
        if self.meanwhile is not None:
            meanwhile, self.meanwhile = self.meanwhile, None
            await meanwhile()
        turn = self.turns.pop(0) if self.turns else REPLY
        if isinstance(turn, Exception):
            raise turn
        return turn


@pytest.fixture
def model(monkeypatch):
    """Script the model. The seam is `complete`, which raises one failure type.

    Not the SDK beneath it: #7 has the wiring catching a failure without
    importing an SDK exception, and a test that built one here would be the
    wiring's test knowing what #3 says only `completion` may know.
    """

    def scripted(*turns: str | Exception) -> Model:
        scripted_model = Model(*turns)
        monkeypatch.setattr(completion, "complete", scripted_model.complete)
        return scripted_model

    return scripted


# --- What she answers -------------------------------------------------

def test_a_summon_reaches_the_model_and_the_answer_reaches_the_channel(
    channel, model
):
    asked = model()

    hear(Message(ALICE, "janet, are you a girl?", channel))

    assert channel.said == [REPLY]
    assert len(asked.payloads) == 1
    assert recalled(asked.payloads[0]) == [
        {"role": "user", "content": "Alice: janet, are you a girl?"}
    ]


# --- The Operator's gates ---------------------------------------------

@pytest.mark.parametrize(
    "summon",
    ["janet, are you a girl?", f"<@{JANET.id}> are you a girl?"],
    ids=["by name", "by mention"],
)
def test_a_summon_in_an_opted_out_channel_reaches_neither_presence_nor_the_model(
    channel, model, monkeypatch, summon
):
    asked = model()
    monkeypatch.setattr(config, "OPT_OUT_CHANNELS", frozenset({channel.id}))

    hear(Message(ALICE, summon, channel, mentions=(JANET,)))

    assert channel.events == []
    assert asked.payloads == []
    # No record for the channel, which is the check that the gate ran before
    # `decide`: a Summon that reached it would have started a presence.
    assert app.presences == {}


def test_a_summon_while_she_is_switched_off_reaches_neither_presence_nor_the_model(
    channel, model, monkeypatch
):
    asked = model()
    monkeypatch.setattr(app, "answering", False)

    hear(Message(ALICE, "janet, are you a girl?", channel))

    assert channel.events == []
    assert asked.payloads == []
    assert app.presences == {}


# --- The typing indicator, and what raises none -----------------------

def test_a_reply_the_cooldown_dropped_says_nothing_and_shows_no_indicator(
    channel, model
):
    asked = model()
    hear(Message(ALICE, "janet, are you a girl?", channel))
    answered = list(channel.events)

    # Straight after the first, so the cooldown is still running. Nothing is
    # slept through: three seconds is the point of the rule, not of the test.
    hear(Message(ALICE, "and are you a robot?", channel))

    assert channel.events == answered
    assert len(asked.payloads) == 1


def test_the_indicator_brackets_the_model_call_and_comes_down_as_the_reply_lands(
    channel, model
):
    asked = model()
    thinking = []

    async def watch() -> None:
        thinking.extend(channel.events)

    asked.meanwhile = watch

    hear(Message(ALICE, "janet, are you a girl?", channel))

    assert thinking == [("typing", "up")]
    assert channel.events == [
        ("typing", "up"),
        ("said", REPLY),
        ("typing", "down"),
    ]


def test_a_message_she_is_not_present_for_says_nothing_and_shows_no_indicator(
    channel, model
):
    asked = model()

    hear(Message(BOB, "morning all", channel))

    assert channel.events == []
    assert asked.payloads == []


def test_a_bystander_in_a_live_exchange_says_nothing_and_shows_no_indicator(
    channel, model, no_cooldown
):
    asked = model()
    hear(Message(ALICE, "janet, are you a girl?", channel))
    answered = list(channel.events)

    hear(Message(BOB, "she is not", channel))

    assert channel.events == answered
    assert len(asked.payloads) == 1


def test_the_goodbye_is_a_fixed_line_with_no_indicator_and_no_model_call(
    channel, model, no_cooldown
):
    asked = model()
    hear(Message(ALICE, "janet, are you a girl?", channel))
    answered = list(channel.events)

    hear(Message(ALICE, "thanks janet", channel))

    assert channel.events[len(answered):] == [("said", persona.GOODBYE)]
    assert len(asked.payloads) == 1


# --- Glitches ---------------------------------------------------------

def test_a_failure_she_cannot_absorb_is_spoken_as_a_glitch(channel, model):
    model(completion.Unavailable())

    hear(Message(ALICE, "janet, are you a girl?", channel))

    # `Unavailable` is the whole seam: `completion` raises it having already
    # retried what a retry helps (#7), so a rate limit twice over and a bad key
    # arrive here as the same thing and leave as the same glitch.
    assert len(channel.said) == 1
    assert channel.said[0] in persona.GLITCHES


def test_a_glitch_ends_the_indicator(channel, model):
    model(completion.Unavailable())

    hear(Message(ALICE, "janet, are you a girl?", channel))

    assert channel.events[0] == ("typing", "up")
    assert channel.events[-1] == ("typing", "down")


# --- Exchange Recall --------------------------------------------------

def test_a_glitch_is_not_recalled_into_the_next_payload(channel, model, no_cooldown):
    asked = model(completion.Unavailable())
    hear(Message(ALICE, "janet, are you a girl?", channel))
    glitched = channel.said[0]

    hear(Message(ALICE, "janet?", channel))

    assert len(asked.payloads) == 2
    assert glitched not in _contents(recalled(asked.payloads[-1]))


def test_her_own_reply_is_recalled_into_the_next_payload(channel, model, no_cooldown):
    asked = model()
    hear(Message(ALICE, "janet, are you a girl?", channel))

    hear(Message(ALICE, "what are you then?", channel))

    assert {"role": "assistant", "content": REPLY} in recalled(asked.payloads[-1])


def test_a_reply_that_outlived_its_exchange_is_not_recalled(
    channel, model, no_cooldown
):
    # Bob's turn is scripted first because he takes the channel while she is
    # still thinking about Alice's, which is the whole arrangement here.
    asked = model(TO_BOB, TO_ALICE)

    async def bob_takes_over() -> None:
        await deliver(Message(BOB, "janet, over here", channel))

    asked.meanwhile = bob_takes_over
    hear(Message(ALICE, "janet, are you a girl?", channel))
    assert channel.said == [TO_BOB, TO_ALICE]

    hear(Message(BOB, "what were you saying?", channel))

    # Hers, pushed onto a stranger's Exchange, would read as her answering
    # something Bob never said.
    assert TO_ALICE not in _contents(recalled(asked.payloads[-1]))
    assert TO_BOB in _contents(recalled(asked.payloads[-1]))


# --- Reading a Discord message ----------------------------------------

@pytest.mark.parametrize(
    "marker", ["<@{id}>", "<@!{id}>"], ids=["mention", "legacy nickname mention"]
)
def test_her_mention_markers_are_stripped_before_the_model_sees_them(
    channel, model, marker
):
    asked = model()
    mention = marker.format(id=JANET.id)

    hear(
        Message(
            ALICE, f"{mention} are you {mention} a girl?", channel, mentions=(JANET,)
        )
    )

    # A space in each marker's place and the spacing collapsed after, so a
    # mention cannot glue two words together on its way to the model.
    assert _contents(recalled(asked.payloads[0])) == ["Alice: are you a girl?"]


@pytest.mark.parametrize("bot", [DOORMAN, JANET], ids=["a bot", "janet herself"])
def test_a_message_from_a_bot_is_never_answered(channel, model, bot):
    asked = model()

    hear(Message(bot, "janet, are you a girl?", channel))

    assert channel.events == []
    assert asked.payloads == []


def test_she_hears_her_own_message_as_her_own(channel):
    # Read off `read_message` rather than driven through the handler, because
    # from the channel this is invisible: she is a bot account, so `from_bot`
    # stops her own message before `from_janet` is ever consulted. This is the
    # field that holds if she stops being one.
    hers = app.read_message(Message(JANET, "Hi there!", channel))
    someone_elses = app.read_message(Message(ALICE, "hi janet", channel))

    assert hers.from_janet
    assert not someone_elses.from_janet


def test_a_message_mentioning_someone_else_does_not_summon_her(channel, model):
    asked = model()

    hear(Message(ALICE, f"<@{BOB.id}> where are you?", channel, mentions=(BOB,)))

    assert channel.events == []
    assert asked.payloads == []


def test_a_direct_message_is_not_a_summon(channel, model):
    asked = model()

    hear(Message(ALICE, "janet, are you a girl?", channel, in_server=False))

    assert channel.events == []
    assert asked.payloads == []


# --- Importing the wiring ---------------------------------------------

def imported(expression: str) -> str:
    """What importing `app` leaves behind, in an interpreter of its own.

    In a subprocess because the claim is about a fresh import, and this
    process has already imported `app`, replaced its client and switched her
    off and on again.
    """
    return subprocess.run(
        [sys.executable, "-c", f"import app; print({expression})"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
        check=True,
        # The regression this guards is an import that blocks forever, so it
        # has to fail rather than hang the suite waiting on it.
        timeout=60,
    ).stdout.strip()


def test_importing_the_wiring_connects_to_nothing():
    # That it returns at all is half the claim: until this issue the import
    # opened a websocket and blocked. `user` is None until the client
    # connects, and is the other half.
    assert imported("app.janet.user is None") == "True"


def test_she_starts_answering_so_a_restart_brings_her_back_on():
    assert imported("app.answering") == "True"
