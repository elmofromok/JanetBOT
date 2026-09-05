"""The glitch lines, which are the only part of `persona` with a rule in it.

`build_payload` is covered by the shape of what it produces; the rule worth a
test is that a failure repeating does not repeat the same line.
"""

import persona
from presence import ExchangeMessage


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


def test_a_payload_names_the_resident_who_spoke():
    payload = persona.build_payload([ExchangeMessage(speaker="chad", text="hi")])
    assert payload == [{"role": "user", "content": "chad: hi"}]


def test_janets_own_turns_are_hers_and_carry_no_name():
    payload = persona.build_payload([ExchangeMessage(speaker=None, text="Hi there!")])
    assert payload == [{"role": "assistant", "content": "Hi there!"}]
