"""The rules of Summon, Present and Dismiss, read back as a transition table.

`presence.decide` is pure, so nothing here needs a fake Discord client, a
frozen clock or async machinery: a case is a record, the facts of a message
and a time in, a decision and the next record out. Times are passed, never
slept through.

The cases come from the acceptance criteria in #4 and #5, not from reading
the module. A test derived from the implementation agrees with its bugs.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import pytest

import presence

# Residents, and the one bot that is not Janet.
ALICE = 1
BOB = 2
SOME_BOT = 99

DISPLAY_NAMES = {ALICE: "Alice", BOB: "Bob", SOME_BOT: "Doorman"}

CHANNEL = 100
OTHER_CHANNEL = 200

T0 = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)

# Every phrase carries her name, which is the point of the list.
DISMISSALS = [
    "bye janet",
    "goodbye janet",
    "thanks janet",
    "thank you janet",
    "that's all janet",
]


def unchanged_but_for_recall(
    record: presence.Presence | None,
    before: presence.Presence,
) -> bool:
    """Still her Exchange, with the same summoner and the same clocks.

    Everything a message she overhears may not touch. What it may touch is
    her recall, which is why this compares the rest field by field.
    """
    return record is not None and (
        record.resident_id,
        record.began,
        record.idle_from,
        record.last_spoke,
    ) == (before.resident_id, before.began, before.idle_from, before.last_spoke)


def at(seconds: float) -> datetime:
    """A time this many seconds after Janet first spoke."""
    return T0 + timedelta(seconds=seconds)


def said(
    text: str,
    resident: int = ALICE,
    *,
    mentions_janet: bool = False,
    channel: int = CHANNEL,
    from_bot: bool = False,
    from_janet: bool = False,
    in_server: bool = True,
) -> presence.IncomingMessage:
    return presence.IncomingMessage(
        resident_id=resident,
        speaker=DISPLAY_NAMES[resident],
        from_bot=from_bot,
        from_janet=from_janet,
        channel_id=channel,
        text=text,
        mentions_janet=mentions_janet,
        in_server=in_server,
    )


def summoned(
    resident: int = ALICE,
    text: str = "janet are you there",
    when: datetime = T0,
    channel: int = CHANNEL,
) -> presence.Presence:
    """The record left behind by a Summon that Janet answered at `when`.

    Driven through `decide` rather than built by hand, so these tests do not
    depend on how the record is put together, only on what it does next.
    """
    decision, record = presence.decide(None, said(text, resident, channel=channel), when)
    assert isinstance(decision, presence.Reply), "the Summon itself went unanswered"
    assert record is not None
    return record


# --- Summoning ---------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "janet",
        "Janet",
        "JANET",
        "janet are you there",
        "Janet!",
        "hey janet, what time is it",
        "that is Janet's job",
        "ask janet.",
    ],
)
def test_her_name_anywhere_in_a_message_summons_her(text):
    decision, record = presence.decide(None, said(text), T0)

    assert isinstance(decision, presence.Reply)
    assert record is not None
    assert record.resident_id == ALICE


@pytest.mark.parametrize(
    "text",
    ["Janette said hi", "planetary alignment", "a janetlike figure", "jan et"],
)
def test_a_word_that_merely_contains_her_name_does_not_summon_her(text):
    decision, record = presence.decide(None, said(text), T0)

    assert isinstance(decision, presence.Nothing)
    assert record is None


def test_a_mention_summons_her():
    decision, record = presence.decide(None, said("are you there", mentions_janet=True), T0)

    assert isinstance(decision, presence.Reply)
    assert record is not None
    assert record.resident_id == ALICE


def test_an_ordinary_message_from_a_resident_she_is_not_with_is_ignored():
    decision, record = presence.decide(None, said("what time is it"), T0)

    assert isinstance(decision, presence.Nothing)
    assert record is None


# --- While she is Present ----------------------------------------------


def test_the_summoner_is_answered_without_summoning_her_again():
    present = summoned()

    decision, record = presence.decide(present, said("and what about tuesday"), at(10))

    assert isinstance(decision, presence.Reply)
    assert record is not None
    assert record.resident_id == ALICE


def test_another_residents_ordinary_message_is_ignored():
    present = summoned()

    decision, record = presence.decide(present, said("unrelated chatter", BOB), at(10))

    assert isinstance(decision, presence.Nothing)
    assert unchanged_but_for_recall(record, present)


def test_another_residents_summon_takes_her_over():
    present = summoned(ALICE)

    decision, record = presence.decide(present, said("janet over here", BOB), at(10))

    assert isinstance(decision, presence.Reply)
    assert record is not None
    assert record.resident_id == BOB
    # Nothing is said about the Exchange it replaced, and nothing of it is
    # carried into the new one.
    assert record.exchange == (
        presence.ExchangeMessage(speaker="Bob", text="janet over here"),
    )


def test_the_resident_she_was_taken_from_is_no_longer_answered():
    present = summoned(ALICE)
    _, taken = presence.decide(present, said("janet over here", BOB), at(10))

    decision, record = presence.decide(taken, said("i was still talking", ALICE), at(20))

    assert isinstance(decision, presence.Nothing)
    assert unchanged_but_for_recall(record, taken)


# --- Dismissal ---------------------------------------------------------


@pytest.mark.parametrize("phrase", DISMISSALS)
def test_the_summoner_dismisses_her_and_she_says_goodbye(phrase):
    present = summoned()

    decision, record = presence.decide(present, said(phrase), at(10))

    assert isinstance(decision, presence.Goodbye)
    assert record is None


@pytest.mark.parametrize("phrase", ["Bye Janet", "THANKS JANET", "thanks janet!", "  bye janet  "])
def test_a_dismissal_is_forgiving_about_case_and_punctuation(phrase):
    present = summoned()

    decision, record = presence.decide(present, said(phrase), at(10))

    assert isinstance(decision, presence.Goodbye)
    assert record is None


@pytest.mark.parametrize("phrase", ["thanks", "bye", "thank you everyone", "bye janet i owe you one"])
def test_a_goodbye_that_is_not_one_of_the_phrases_does_not_dismiss_her(phrase):
    present = summoned()

    decision, record = presence.decide(present, said(phrase), at(10))

    assert not isinstance(decision, presence.Goodbye)
    assert record is not None


@pytest.mark.parametrize("phrase", DISMISSALS)
def test_a_dismissal_from_anyone_but_the_summoner_does_nothing_at_all(phrase):
    present = summoned(ALICE)

    decision, record = presence.decide(present, said(phrase, BOB), at(10))

    assert isinstance(decision, presence.Nothing)
    assert unchanged_but_for_recall(record, present)


@pytest.mark.parametrize("phrase", DISMISSALS)
def test_a_dismissal_while_she_is_absent_neither_summons_nor_dismisses(phrase):
    decision, record = presence.decide(None, said(phrase), T0)

    assert isinstance(decision, presence.Nothing)
    assert record is None


# --- Dismissal by silence ----------------------------------------------
#
# Two minutes measured from when Janet last spoke. The tests sit either side
# of it rather than on it: #4's brief says "longer than", the module dismisses
# her at exactly two minutes, and no clock this reads from can tell them apart.


def test_she_is_still_present_just_inside_the_two_minutes():
    present = summoned()

    decision, record = presence.decide(present, said("still there"), at(119))

    assert isinstance(decision, presence.Reply)
    assert record is not None


def test_the_silence_dismisses_her_and_she_says_nothing():
    present = summoned()

    decision, record = presence.decide(present, said("still there"), at(121))

    assert isinstance(decision, presence.Nothing)
    assert record is None


def test_the_silence_runs_from_when_janet_last_spoke_not_from_the_last_message():
    present = summoned()
    # Another Resident fills the channel just before the two minutes are up.
    _, after_chatter = presence.decide(present, said("chatter", BOB), at(119))

    decision, record = presence.decide(after_chatter, said("still there"), at(121))

    assert isinstance(decision, presence.Nothing)
    assert record is None


def test_she_must_be_summoned_again_once_the_silence_has_dismissed_her():
    present = summoned()
    _, gone = presence.decide(present, said("still there"), at(121))

    decision, record = presence.decide(gone, said("janet are you back"), at(122))

    assert isinstance(decision, presence.Reply)
    assert record is not None
    assert record.resident_id == ALICE


# --- The cooldown ------------------------------------------------------


def test_a_second_reply_inside_the_cooldown_is_dropped():
    present = summoned()

    decision, record = presence.decide(present, said("and another thing"), at(1))

    assert isinstance(decision, presence.Nothing)
    assert record is not None


def test_she_replies_again_once_the_cooldown_has_passed():
    present = summoned()

    decision, record = presence.decide(present, said("and another thing"), at(4))

    assert isinstance(decision, presence.Reply)
    assert record is not None


def test_a_dropped_reply_is_never_delivered_late():
    present = summoned()
    _, after_drop = presence.decide(present, said("dropped"), at(1))

    decision, record = presence.decide(after_drop, said("asked later"), at(5))

    assert isinstance(decision, presence.Reply)
    # She answers what was just said, not the message the cooldown ate.
    assert decision.exchange[-1] == presence.ExchangeMessage(
        speaker="Alice", text="asked later"
    )


def test_a_dropped_reply_does_not_extend_her_presence():
    present = summoned()
    _, after_drop = presence.decide(present, said("dropped"), at(1))

    decision, record = presence.decide(after_drop, said("still there"), at(121))

    assert isinstance(decision, presence.Nothing)
    assert record is None


def test_a_summon_makes_her_present_even_when_the_cooldown_drops_its_reply():
    present = summoned(ALICE)

    decision, taken = presence.decide(present, said("janet!", BOB), at(1))

    assert isinstance(decision, presence.Nothing)
    assert taken is not None
    assert taken.resident_id == BOB
    # She is with Bob, so his next message needs no further Summon.
    later, _ = presence.decide(taken, said("well?", BOB), at(5))
    assert isinstance(later, presence.Reply)


def test_a_rush_of_summons_cannot_outrun_the_cooldown():
    record = None
    replies = 0
    for tick, resident in enumerate([ALICE, BOB, ALICE, BOB, ALICE]):
        decision, record = presence.decide(record, said("janet!", resident), at(tick * 0.5))
        replies += isinstance(decision, presence.Reply)

    assert replies == 1


# --- Ignored in every state --------------------------------------------


@pytest.mark.parametrize("text", ["janet hello", "ordinary chatter", "bye janet"])
def test_a_bot_never_summons_dismisses_or_disturbs_her(text):
    absent_decision, absent_record = presence.decide(
        None, said(text, SOME_BOT, from_bot=True), T0
    )
    assert isinstance(absent_decision, presence.Nothing)
    assert absent_record is None

    present = summoned()
    decision, record = presence.decide(present, said(text, SOME_BOT, from_bot=True), at(10))
    assert isinstance(decision, presence.Nothing)
    assert record == present


def test_she_ignores_her_own_messages():
    present = summoned()

    decision, record = presence.decide(
        present, said("janet here!", from_bot=True, from_janet=True), at(10)
    )

    assert isinstance(decision, presence.Nothing)
    assert record == present


@pytest.mark.parametrize("text", ["janet hello", "ordinary chatter", "bye janet"])
def test_a_direct_message_is_ignored(text):
    decision, record = presence.decide(None, said(text, in_server=False), T0)

    assert isinstance(decision, presence.Nothing)
    assert record is None


# --- One channel at a time ---------------------------------------------


def test_presence_is_held_per_channel():
    """Keyed the way the handler keys it, since `decide` is given one at a time."""
    records: dict[int, presence.Presence | None] = {}

    def arrives(message, when):
        decision, record = presence.decide(records.get(message.channel_id), message, when)
        records[message.channel_id] = record
        return decision

    arrives(said("janet hello", ALICE, channel=CHANNEL), T0)
    # A Summon next door, and a Dismiss next door, leave the first alone.
    arrives(said("janet hello", BOB, channel=OTHER_CHANNEL), at(1))
    arrives(said("bye janet", BOB, channel=OTHER_CHANNEL), at(2))

    assert isinstance(arrives(said("still with me", ALICE, channel=CHANNEL), at(10)), presence.Reply)
    assert records[OTHER_CHANNEL] is None


# --- The shape of the seam ---------------------------------------------


def test_deciding_reaches_no_further_than_the_standard_library():
    """The reason these tests need no Discord client and no API key."""
    assert "discord" not in sys.modules
    assert "openai" not in sys.modules


# --- Exchange Recall ---------------------------------------------------


def spoken(exchange) -> list[tuple[str | None, str]]:
    """An Exchange as (speaker, text) pairs, which is what the payload needs."""
    return [(message.speaker, message.text) for message in exchange]


def test_the_summon_is_the_first_thing_she_recalls():
    present = summoned(ALICE, "janet what is the capital of peru")

    assert spoken(present.exchange) == [("Alice", "janet what is the capital of peru")]


def test_a_follow_up_is_answered_with_the_exchange_so_far():
    present = summoned(ALICE, "janet what is the capital of peru")
    present = presence.janet_said(present, present.began, "Lima!")

    decision, record = presence.decide(present, said("how big is it"), at(10))

    assert isinstance(decision, presence.Reply)
    assert spoken(decision.exchange) == [
        ("Alice", "janet what is the capital of peru"),
        (None, "Lima!"),
        ("Alice", "how big is it"),
    ]


def test_her_own_replies_are_recalled_as_hers():
    present = summoned()

    record = presence.janet_said(present, present.began, "Hi there!")

    assert record is not None
    assert record.exchange[-1] == presence.ExchangeMessage(speaker=None, text="Hi there!")


def test_a_reply_that_outlived_its_exchange_is_not_recalled():
    """She was dismissed, or taken over, while the model was still thinking."""
    present = summoned(ALICE)
    _, taken = presence.decide(present, said("janet over here", BOB), at(10))

    record = presence.janet_said(taken, present.began, "answering Alice")

    assert record == taken
    assert presence.janet_said(None, present.began, "answering Alice") is None


def test_a_bystanders_message_is_recalled_though_she_never_answers_it():
    present = summoned(ALICE, "janet hello")

    _, record = presence.decide(present, said("i think she means the river", BOB), at(10))

    assert record is not None
    assert spoken(record.exchange) == [
        ("Alice", "janet hello"),
        ("Bob", "i think she means the river"),
    ]


@pytest.mark.parametrize("phrase", DISMISSALS)
def test_a_dismissal_from_a_bystander_is_recalled_like_any_other_message(phrase):
    present = summoned(ALICE, "janet hello")

    _, record = presence.decide(present, said(phrase, BOB), at(10))

    assert record is not None
    assert spoken(record.exchange) == [("Alice", "janet hello"), ("Bob", phrase)]


def test_a_message_the_cooldown_suppressed_is_recalled():
    present = summoned(ALICE, "janet hello")

    _, dropped = presence.decide(present, said("and another thing"), at(1))
    decision, _ = presence.decide(dropped, said("asked later"), at(5))

    assert isinstance(decision, presence.Reply)
    assert spoken(decision.exchange) == [
        ("Alice", "janet hello"),
        ("Alice", "and another thing"),
        ("Alice", "asked later"),
    ]


def test_nothing_said_before_the_summon_is_recalled():
    record = None
    for text in ["what is the capital of peru", "no idea", "ask someone else"]:
        _, record = presence.decide(record, said(text, BOB), T0)
    assert record is None

    decision, record = presence.decide(record, said("janet, do you know", ALICE), at(1))

    assert isinstance(decision, presence.Reply)
    assert spoken(decision.exchange) == [("Alice", "janet, do you know")]


def test_a_goodbye_takes_her_recall_with_it():
    present = summoned(ALICE, "janet hello")
    _, gone = presence.decide(present, said("bye janet"), at(10))
    assert gone is None

    decision, record = presence.decide(gone, said("janet are you back"), at(20))

    assert isinstance(decision, presence.Reply)
    assert spoken(decision.exchange) == [("Alice", "janet are you back")]


def test_the_silence_takes_her_recall_with_it():
    present = summoned(ALICE, "janet hello")
    _, gone = presence.decide(present, said("still there"), at(121))
    assert gone is None

    decision, record = presence.decide(gone, said("janet are you back"), at(122))

    assert isinstance(decision, presence.Reply)
    assert spoken(decision.exchange) == [("Alice", "janet are you back")]


def test_a_takeover_carries_nothing_of_the_exchange_it_replaced():
    present = summoned(ALICE, "janet hello")
    present = presence.janet_said(present, present.began, "Hi there!")
    _, present = presence.decide(present, said("one more thing", ALICE), at(5))

    decision, record = presence.decide(present, said("janet over here", BOB), at(10))

    assert isinstance(decision, presence.Reply)
    assert spoken(decision.exchange) == [("Bob", "janet over here")]


def test_a_bot_is_never_recalled():
    present = summoned(ALICE, "janet hello")

    _, record = presence.decide(present, said("beep", SOME_BOT, from_bot=True), at(10))

    assert record is not None
    assert spoken(record.exchange) == [("Alice", "janet hello")]


def test_recall_holds_the_most_recent_forty_messages_in_order():
    present = summoned(ALICE, "janet hello")
    for number in range(60):
        _, present = presence.decide(present, said(f"message {number}", BOB), at(10))

    assert present is not None
    assert len(present.exchange) == 40
    assert spoken(present.exchange) == [("Bob", f"message {number}") for number in range(20, 60)]

