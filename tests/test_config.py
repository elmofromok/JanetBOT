"""The startup checks, which are the pure half of `config`.

`config` validates at import and ends the process when the environment is
wrong, so a plausible environment is set below before importing it. Nothing
under test reads the real environment: `problems` takes a mapping and
`channel_ids` takes a string, so every case builds its own.
"""

import os

import pytest

ID = "1" * 18
OTHER_ID = "2" * 19

os.environ.setdefault("DISCORD_TOKEN", "token")
os.environ.setdefault("OPENAI_API_KEY", "key")
os.environ.setdefault("OPERATOR_ID", ID)

import config  # noqa: E402


def environment(**overrides: str | None) -> dict[str, str]:
    """A complete environment, with the named variables changed or removed."""
    environ = {
        "DISCORD_TOKEN": "token",
        "OPENAI_API_KEY": "key",
        "OPERATOR_ID": ID,
    }
    environ.update(overrides)
    return {name: value for name, value in environ.items() if value is not None}


def test_a_complete_environment_has_no_problems():
    assert config.problems(environment()) == []


def test_an_empty_environment_names_every_missing_variable():
    assert config.problems({}) == [
        "DISCORD_TOKEN is not set",
        "OPENAI_API_KEY is not set",
        "OPERATOR_ID is not set",
    ]


@pytest.mark.parametrize("name", config.REQUIRED)
def test_a_missing_variable_is_named(name):
    assert config.problems(environment(**{name: None})) == [f"{name} is not set"]


@pytest.mark.parametrize("blank", ["", " ", "\t", "\n"])
def test_a_blank_variable_counts_as_missing(blank):
    problems = config.problems(environment(DISCORD_TOKEN=blank))
    assert problems == ["DISCORD_TOKEN is not set"]


@pytest.mark.parametrize(
    "value",
    [
        "chad",
        "@chad",
        "chad#1234",
        "123",
        "1234567890123456",  # Sixteen digits, one short of a snowflake.
        "111111111111111111x",
        "1111111111111111 1",
    ],
)
def test_an_operator_id_that_is_not_a_snowflake_is_named_with_its_value(value):
    assert config.problems(environment(OPERATOR_ID=value)) == [
        f"OPERATOR_ID is not a Discord id: {value!r}"
    ]


@pytest.mark.parametrize("value", [ID, OTHER_ID, "9" * 20, f"  {ID}  "])
def test_a_well_formed_operator_id_passes(value):
    assert config.problems(environment(OPERATOR_ID=value)) == []


@pytest.mark.parametrize("value", [None, "", "   ", ",", " , "])
def test_an_absent_or_empty_opt_out_is_not_a_problem(value):
    assert config.problems(environment(OPT_OUT_CHANNELS=value)) == []


@pytest.mark.parametrize("value", [ID, f"{ID},{OTHER_ID}", f" {ID} , {OTHER_ID} ", f"{ID},"])
def test_a_well_formed_opt_out_passes(value):
    assert config.problems(environment(OPT_OUT_CHANNELS=value)) == []


def test_a_channel_name_in_the_opt_out_is_named_with_its_value():
    assert config.problems(environment(OPT_OUT_CHANNELS="general")) == [
        "OPT_OUT_CHANNELS holds something that is not a Discord id: 'general'"
    ]


def test_only_the_bad_entry_in_an_opt_out_is_named():
    assert config.problems(environment(OPT_OUT_CHANNELS=f"{ID},general,{OTHER_ID}")) == [
        "OPT_OUT_CHANNELS holds something that is not a Discord id: 'general'"
    ]


def test_every_bad_entry_in_an_opt_out_is_named():
    assert config.problems(environment(OPT_OUT_CHANNELS="general,#random")) == [
        "OPT_OUT_CHANNELS holds something that is not a Discord id: 'general'",
        "OPT_OUT_CHANNELS holds something that is not a Discord id: '#random'",
    ]


def test_problems_are_reported_together_and_in_declaration_order():
    assert config.problems({"OPERATOR_ID": "chad", "OPT_OUT_CHANNELS": "general"}) == [
        "DISCORD_TOKEN is not set",
        "OPENAI_API_KEY is not set",
        "OPERATOR_ID is not a Discord id: 'chad'",
        "OPT_OUT_CHANNELS holds something that is not a Discord id: 'general'",
    ]


@pytest.mark.parametrize("value", ["", "   ", ",", " , "])
def test_an_empty_opt_out_excludes_no_channels(value):
    assert config.channel_ids(value) == frozenset()


@pytest.mark.parametrize(
    "value",
    [f"{ID},{OTHER_ID}", f" {ID} , {OTHER_ID} ", f"{ID},{OTHER_ID},", f"{ID},{OTHER_ID},{ID}"],
)
def test_an_opt_out_parses_to_its_ids(value):
    assert config.channel_ids(value) == frozenset({int(ID), int(OTHER_ID)})
