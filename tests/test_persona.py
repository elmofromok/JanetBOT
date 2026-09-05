"""The rules in `persona`, which are the ones a rewrite by ear could break.

Her voice is judged by reading it, not by asserting on it: nothing here checks
that a line sounds like her, because nothing can. What these cover is the
structure around the voice, the promises #6 makes about where her character
lives and how it reaches the model, which are exactly the things that go
quietly wrong when someone edits the prompt and not the wiring.
"""

from pathlib import Path

import persona
from presence import ExchangeMessage

ROOT = Path(__file__).parent.parent

# The three lines that are hers and nobody else's.
REFLEXES = ("Hi there!", "not a girl", "not a robot")


def test_she_has_more_than_one_glitch_line():
    # One line repeated reads as a stuck bot rather than as a character.
    assert len(set(persona.GLITCHES)) > 1


def test_a_glitch_is_one_of_her_lines():
    assert persona.glitch() in persona.GLITCHES


def test_two_glitches_running_are_never_the_same_line():
    # The failure a glitch reports usually repeats, so consecutive glitches are
    # the normal case rather than the unlucky one. Run long enough that a
    # random choice that happened to differ would not pass by luck.
    said = [persona.glitch() for _ in range(200)]
    assert all(one != following for one, following in zip(said, said[1:]))


def test_she_works_through_her_lines_rather_than_alternating_between_two():
    assert set(persona.glitch() for _ in range(200)) == set(persona.GLITCHES)


def test_no_glitch_line_is_empty():
    # An empty one sends nothing, which is the silence ADR 0002 exists to stop
    # a failure hiding behind.
    assert all(line.strip() for line in persona.GLITCHES)


def exchange_in(payload: list[dict[str, str]]) -> list[dict[str, str]]:
    """The payload past her prompt and examples, which sit in front of every one."""
    return payload[len(persona.build_payload(())):]


def test_a_payload_names_the_resident_who_spoke():
    payload = persona.build_payload([ExchangeMessage(speaker="chad", text="hi")])
    assert exchange_in(payload) == [{"role": "user", "content": "chad: hi"}]


def test_janets_own_turns_are_hers_and_carry_no_name():
    payload = persona.build_payload([ExchangeMessage(speaker=None, text="Hi there!")])
    assert exchange_in(payload) == [{"role": "assistant", "content": "Hi there!"}]


# --- Where her character lives -----------------------------------------


def test_every_payload_carries_the_system_message():
    # No path to the model without her character on it. The guard this replaced
    # skipped the system message when the prompt was empty, which was right
    # while it was empty and would now be a way to reach the model as stock
    # Luna with a name.
    for exchange in ([], [ExchangeMessage(speaker="chad", text="janet")]):
        assert persona.build_payload(exchange)[0] == {
            "role": "system",
            "content": persona.SYSTEM_PROMPT,
        }


def test_the_examples_are_alternating_turns_and_not_prose_in_the_prompt():
    roles = [persona._as_chat_message(m)["role"] for m in persona.EXAMPLES]
    assert roles == ["user", "assistant"] * (len(roles) // 2)


def test_there_are_four_or_five_example_exchanges():
    assert len(persona.EXAMPLES) // 2 in (4, 5)


def test_an_example_refuses_to_guess():
    # ADR 0002. The example has to be there, because the prompt saying so is
    # the instruction a model is most willing to talk itself out of.
    replies = [m.text for m in persona.EXAMPLES if m.speaker is None]
    assert any("I don't know that one!" in reply for reply in replies)


def test_she_never_writes_her_own_name_in_front_of_a_reply():
    # The payload prefixes Residents with their names, and a model shown that
    # pattern will happily copy it onto its own turns.
    replies = [m.text for m in persona.EXAMPLES if m.speaker is None]
    assert not any(reply.lower().startswith("janet:") for reply in replies)


def test_her_reflexes_are_in_the_persona():
    voice = (persona.SYSTEM_PROMPT + " ".join(m.text for m in persona.EXAMPLES)).lower()
    assert all(reflex.lower() in voice for reflex in REFLEXES)


def test_her_reflexes_are_nowhere_else():
    # The criterion behind this one: no reflex is hardcoded in the wiring or
    # produced by matching on what a Resident typed. She says these because
    # they are in her context, not because code went looking for a cue.
    for module in ("app.py", "presence.py", "completion.py", "config.py"):
        source = (ROOT / module).read_text().lower()
        for reflex in REFLEXES:
            assert reflex.lower() not in source, f"{reflex!r} leaked into {module}"
