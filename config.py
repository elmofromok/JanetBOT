"""The environment Janet reads, checked once before she starts.

Importing this module either yields the configuration or ends the process, and
the check runs at import on purpose: `completion` builds its OpenAI client at
import too, and a check that ran later would be a check that ran second.

Railway gives one signal, a log tail. An unset `DISCORD_TOKEN` reaches it as an
authentication failure from `discord.py`, which reads like a bad token rather
than an absent one, and sends the Operator to the Discord portal to reissue a
token that was fine. Every missing name is reported at once because each retry
on Railway is a redeploy, and finding them one at a time costs a deploy apiece.
"""

from __future__ import annotations

import os
import sys
from typing import Mapping

from dotenv import load_dotenv

# Local dev reads `.env`; on Railway no such file exists and the real
# environment already holds these. Nothing already set is overwritten, so a
# stale `.env` left in a working copy cannot shadow a deployment.
load_dotenv(override=False)

# Every variable Janet cannot start without. The channel opt-out from #10 is
# not here: an empty opt-out is a legitimate configuration, not a missing one.
REQUIRED = ("DISCORD_TOKEN", "OPENAI_API_KEY")


def missing(environ: Mapping[str, str]) -> list[str]:
    """The required names that are absent or blank, in declaration order.

    Blank counts as absent. A variable set to the empty string on Railway is a
    typo every time, and failing on it here beats failing on it at the API.
    """
    return [name for name in REQUIRED if not environ.get(name, "").strip()]


_absent = missing(os.environ)
if _absent:
    _one = len(_absent) == 1
    sys.exit(
        f"Janet cannot start: {', '.join(_absent)} "
        f"{'is' if _one else 'are'} not set. "
        f"Set {'it' if _one else 'them'} on the service, "
        "or in a .env file for local dev."
    )

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
