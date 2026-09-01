"""The environment Janet reads, checked once before she starts.

Importing this module either yields the configuration or ends the process, and
the check runs at import on purpose: `completion` builds its OpenAI client at
import too, and a check that ran later would be a check that ran second.

Railway gives one signal, a log tail. An unset `DISCORD_TOKEN` reaches it as an
authentication failure from `discord.py`, which reads like a bad token rather
than an absent one, and sends the Operator to the Discord portal to reissue a
token that was fine. Every problem is reported at once because each retry on
Railway is a redeploy, and finding them one at a time costs a deploy apiece.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Mapping

from dotenv import load_dotenv

# Local dev reads `.env`; on Railway no such file exists and the real
# environment already holds these. Nothing already set is overwritten, so a
# stale `.env` left in a working copy cannot shadow a deployment.
load_dotenv(override=False)

# Every variable Janet cannot start without.
REQUIRED = ("DISCORD_TOKEN", "OPENAI_API_KEY", "OPERATOR_ID")

# Of those, the ones that must hold a Discord id rather than any string.
_IDS = frozenset({"OPERATOR_ID"})

# The channels Janet never listens in. Optional: unset or empty excludes no
# channels, which is a legitimate configuration rather than an error.
_OPT_OUT = "OPT_OUT_CHANNELS"

# A snowflake is digits, and seventeen of them at the shortest for anything
# Discord has minted since its 2015 epoch. What this catches is a channel name
# typed where an id belongs, which is the mistake worth catching: an opt-out
# holding `general` excludes nothing and says nothing about it. What it cannot
# catch is a well-formed id naming no channel. Only Discord knows that.
_SNOWFLAKE = re.compile(r"\d{17,}")


def problems(environ: Mapping[str, str]) -> list[str]:
    """Every reason Janet cannot start, in the order the names are declared.

    A blank value counts as absent. A variable set to the empty string is a
    typo every time, and failing here beats failing at the API.
    """
    found: list[str] = []
    for name in REQUIRED:
        value = environ.get(name, "").strip()
        if not value:
            found.append(f"{name} is not set")
        elif name in _IDS and not _SNOWFLAKE.fullmatch(value):
            found.append(f"{name} is not a Discord id: {value!r}")
    for entry in _entries(environ.get(_OPT_OUT, "")):
        if not _SNOWFLAKE.fullmatch(entry):
            found.append(f"{_OPT_OUT} holds something that is not a Discord id: {entry!r}")
    return found


def channel_ids(value: str) -> frozenset[int]:
    """The opt-out list as ids. Call it only on a value `problems` accepted."""
    return frozenset(int(entry) for entry in _entries(value))


def _entries(value: str) -> list[str]:
    """The comma-separated entries of a list variable, blanks dropped.

    A trailing comma and a stray space are how a list typed by hand goes wrong,
    and neither is worth refusing to start over.
    """
    return [entry.strip() for entry in value.split(",") if entry.strip()]


_problems = problems(os.environ)
if _problems:
    sys.exit(
        "Janet cannot start:\n  "
        + "\n  ".join(_problems)
        + "\nSet these on the service, or in a .env file for local dev."
    )

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPERATOR_ID = int(os.environ["OPERATOR_ID"])
OPT_OUT_CHANNELS = channel_ids(os.environ.get(_OPT_OUT, ""))
