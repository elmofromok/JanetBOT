"""The retry, and what it does and does not try again.

`completion` builds its OpenAI client at import, and `config` ends the process
on an empty environment, so a plausible one is set before importing either.
Nothing here reaches the network: the client's `create` is replaced with a
scripted one that hands back a reply or raises whatever the case is about.

`PAUSE` is set to nothing for the duration, so the retry is real but instant.
The pause itself is `_pause_after`, tested on its own at the bottom.
"""

import asyncio
import logging
import os
from types import SimpleNamespace

import httpx2 as httpx
import openai
import pytest

os.environ.setdefault("DISCORD_TOKEN", "token")
os.environ.setdefault("OPENAI_API_KEY", "key")
os.environ.setdefault("OPERATOR_ID", "1" * 18)

import completion  # noqa: E402

PAYLOAD = [{"role": "user", "content": "chad: janet, what's the capital of Peru?"}]

# What Discord refuses with an HTTP 400, in characters.
DISCORD_MESSAGE_LIMIT = 2000

# The rule of thumb `REPLY_BUDGET` was chosen against, in characters per token.
CHARACTERS_PER_TOKEN = 4


def rate_limited(retry_after: str | None = None) -> openai.RateLimitError:
    headers = {} if retry_after is None else {"retry-after": retry_after}
    return openai.RateLimitError(
        "slow down",
        response=httpx.Response(
            429, headers=headers, request=httpx.Request("POST", "https://api.test")
        ),
        body=None,
    )


def out_of_credit() -> openai.RateLimitError:
    """An empty balance, which OpenAI reports as a 429 like any rate limit.

    The body is the one that actually stopped Janet on the day she went live,
    down to the fields: `type` and `code` disagree, and either has to be
    enough.
    """
    body = {
        "message": (
            "You have no credits remaining. Add credits to continue using the "
            "API at https://platform.openai.com/settings/organization/billing/."
        ),
        "type": "insufficient_quota",
        "param": None,
        "code": "credit_balance_exhausted",
    }
    return openai.RateLimitError(
        body["message"],
        response=httpx.Response(
            429,
            # A `Retry-After` it would otherwise have honoured, so the test
            # fails if the retry comes back.
            headers={"retry-after": "3"},
            request=httpx.Request("POST", "https://api.test"),
        ),
        body=body,
    )


def timed_out() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=httpx.Request("POST", "https://api.test"))


def unauthenticated() -> openai.AuthenticationError:
    return openai.AuthenticationError(
        "bad key",
        response=httpx.Response(
            401, request=httpx.Request("POST", "https://api.test")
        ),
        body=None,
    )


def unknown_model() -> openai.NotFoundError:
    return openai.NotFoundError(
        "no such model",
        response=httpx.Response(
            404, request=httpx.Request("POST", "https://api.test")
        ),
        body=None,
    )


class Scripted:
    """A stand-in for the client, handing back one outcome per attempt."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.attempts = 0
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **_):
        self.attempts += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=outcome))]
        )


@pytest.fixture
def instant(monkeypatch):
    """No waiting. The retry still happens, it just does not cost a second."""
    monkeypatch.setattr(completion, "PAUSE", 0.0)


@pytest.fixture
def ask(monkeypatch, instant):
    """Run `complete` against a scripted client, and hand back the client."""

    def run(*outcomes):
        client = Scripted(*outcomes)
        monkeypatch.setattr(completion, "client", client)
        return client, asyncio.run(completion.complete(PAYLOAD))

    return run


def test_a_reply_first_time_is_asked_for_once(ask):
    client, reply = ask("Lima!")
    assert reply == "Lima!"
    assert client.attempts == 1


def test_a_transient_failure_then_a_reply_looks_like_no_failure_at_all(ask):
    client, reply = ask(rate_limited(), "Lima!")
    assert reply == "Lima!"
    assert client.attempts == 2


@pytest.mark.parametrize(
    "failure",
    [rate_limited, timed_out],
    ids=["rate limit", "timeout"],
)
def test_every_transient_failure_is_retried(ask, failure):
    client, reply = ask(failure(), "Lima!")
    assert reply == "Lima!"
    assert client.attempts == 2


def test_two_transient_failures_raise_rather_than_going_quiet(monkeypatch, instant):
    client = Scripted(rate_limited(), rate_limited())
    monkeypatch.setattr(completion, "client", client)
    with pytest.raises(completion.Unavailable):
        asyncio.run(completion.complete(PAYLOAD))
    assert client.attempts == 2


@pytest.mark.parametrize(
    "failure",
    [unauthenticated, unknown_model],
    ids=["authentication", "unknown model"],
)
def test_a_configuration_failure_is_attempted_once(monkeypatch, instant, failure):
    client = Scripted(failure())
    monkeypatch.setattr(completion, "client", client)
    with pytest.raises(completion.Unavailable):
        asyncio.run(completion.complete(PAYLOAD))
    # Not two. It fails the same way the second time, and the Operator is the
    # only one who can fix it.
    assert client.attempts == 1


def test_a_configuration_failure_reaches_the_log_at_error_level(
    monkeypatch, instant, caplog
):
    monkeypatch.setattr(completion, "client", Scripted(unauthenticated()))
    with caplog.at_level(logging.ERROR, logger="completion"):
        with pytest.raises(completion.Unavailable):
            asyncio.run(completion.complete(PAYLOAD))
    logged = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(logged) == 1
    assert "bad key" in logged[0].exc_text


def test_an_exhausted_rate_limit_is_not_reported_as_a_configuration_error(
    monkeypatch, instant, caplog
):
    monkeypatch.setattr(completion, "client", Scripted(rate_limited(), rate_limited()))
    with caplog.at_level(logging.DEBUG, logger="completion"):
        with pytest.raises(completion.Unavailable):
            asyncio.run(completion.complete(PAYLOAD))
    # Nothing is misconfigured, so nothing sends the Operator looking for a
    # configuration bug there is not.
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert [r for r in caplog.records if r.levelno == logging.WARNING]


@pytest.mark.parametrize("said", [None, "", "   ", "\n\n"], ids=repr)
def test_a_reply_with_nothing_in_it_is_a_failure_not_an_answer(
    monkeypatch, instant, said
):
    # Sending it posts an empty message the channel reads as her having
    # answered, which ADR 0002 rules out more firmly than it rules out silence.
    monkeypatch.setattr(completion, "client", Scripted(said))
    with pytest.raises(completion.Unavailable):
        asyncio.run(completion.complete(PAYLOAD))


def test_the_wiring_never_needs_an_sdk_exception_to_catch_a_failure():
    # The check behind #3's rule that the SDK lives in one module: if
    # `Unavailable` were an SDK type, catching it would mean importing openai.
    assert not issubclass(completion.Unavailable, openai.OpenAIError)


def test_the_sdk_does_not_retry_underneath_us():
    # Left at its default of two, the SDK would make "one quiet retry" three
    # attempts on a schedule nobody chose.
    assert completion.client.max_retries == 0


def test_the_reply_budget_cannot_ask_for_a_message_discord_would_refuse():
    # The reasoning behind the number is written down in `completion`. This is
    # what keeps it true. Raising it back to something roomy is a one-line
    # change with a consequence nobody would connect to it: the send raises
    # inside the handler and the channel sees silence rather than an answer.
    assert completion.REPLY_BUDGET * CHARACTERS_PER_TOKEN <= DISCORD_MESSAGE_LIMIT


def test_a_retry_after_is_honoured():
    assert completion._pause_after(rate_limited("2")) == 2.0


def test_a_long_retry_after_is_capped():
    # She is answering a live conversation. A minute under a typing indicator
    # reads worse than a glitch now.
    assert completion._pause_after(rate_limited("600")) == completion.PAUSE_CAP


def test_a_negative_retry_after_does_not_travel_back_in_time():
    assert completion._pause_after(rate_limited("-5")) == 0.0


@pytest.mark.parametrize(
    "header",
    [None, "Wed, 21 Oct 2026 07:28:00 GMT", "soon"],
    ids=["absent", "http date", "nonsense"],
)
def test_an_unusable_retry_after_falls_back_to_the_fixed_pause(header):
    assert completion._pause_after(rate_limited(header)) == completion.PAUSE


def test_a_failure_carrying_no_response_falls_back_to_the_fixed_pause():
    # A timeout and a dropped connection never got a response to read a header
    # off.
    assert completion._pause_after(timed_out()) == completion.PAUSE


# --- An empty balance is not a rate limit -----------------------------

def test_an_empty_balance_is_attempted_once(monkeypatch, instant):
    # The reply is scripted second and must never be reached: getting to it
    # would mean she retried a failure that clears only when somebody pays.
    client = Scripted(out_of_credit(), "Lima!")
    monkeypatch.setattr(completion, "client", client)
    with pytest.raises(completion.Unavailable):
        asyncio.run(completion.complete(PAYLOAD))
    assert client.attempts == 1


def test_an_empty_balance_is_the_operator_s_to_fix(monkeypatch, instant, caplog):
    monkeypatch.setattr(completion, "client", Scripted(out_of_credit()))
    with caplog.at_level(logging.DEBUG, logger="completion"):
        with pytest.raises(completion.Unavailable):
            asyncio.run(completion.complete(PAYLOAD))

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "credit" in errors[0].getMessage()
    # The billing URL is the whole of what he needs, and it is in the message
    # the SDK already carries.
    assert "billing" in errors[0].getMessage()
    # The line this replaced. It sent the Operator to look at OpenAI when what
    # was wrong was his own account.
    assert "twice" not in caplog.text


def test_an_empty_balance_after_a_rate_limit_is_still_reported_as_credit(
    monkeypatch, instant, caplog
):
    # Why `_exhausted` is checked on both attempts rather than only the first.
    monkeypatch.setattr(
        completion, "client", Scripted(rate_limited(), out_of_credit())
    )
    with caplog.at_level(logging.DEBUG, logger="completion"):
        with pytest.raises(completion.Unavailable):
            asyncio.run(completion.complete(PAYLOAD))

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "credit" in errors[0].getMessage()
    assert "twice" not in caplog.text


def test_a_real_rate_limit_is_still_retried(ask):
    # The other half of the claim: telling the two apart has to leave an
    # ordinary 429 alone, which is the case the retry exists for.
    client, reply = ask(rate_limited(), "Lima!")
    assert reply == "Lima!"
    assert client.attempts == 2
