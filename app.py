"""Discord wiring. Ask presence what to do, then do it."""

import logging
from datetime import datetime, timezone
from typing import Literal

import discord
from discord import app_commands

import completion
import config
import persona
import presence

# Named for the module, so the log says which part of her spoke. `completion`
# reports why the model could not be reached; this reports what reached the
# channel. The Operator reads both in one stream.
log = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

# A plain Client rather than `commands.Bot`, which exists to serve text
# commands that ADR 0004 rules out permanently. It carried a `command_prefix`
# of '@janet' that no command ever used. Named for her rather than for the
# machinery, per CONTEXT.md.
janet = discord.Client(intents=intents)
tree = app_commands.CommandTree(janet)

# The channel's current record, or nothing if Janet is not Present there.
# `presence.decide` is pure, so the records are held here and written back.
presences: dict[int, presence.Presence] = {}

# Whether Janet answers at all. In memory on purpose: she starts on, and a
# restart brings her back. An off switch that silently outlives a deploy is how
# a bot ends up dead for a week with nobody remembering why.
answering = True

# `on_ready` fires again on every reconnect and a sync is rate limited, so the
# command tree goes up once per process.
synced = False


def read_message(message: discord.Message) -> presence.IncomingMessage:
    """Turn a Discord message into the facts presence works with."""
    # Both encodings: `<@ID>` is what Discord sends, `<@!ID>` the legacy
    # nickname form that older messages still carry. A space in their place,
    # collapsed after, so a mention cannot glue two words together.
    text = message.content
    for mention in (f'<@{janet.user.id}>', f'<@!{janet.user.id}>'):
        text = text.replace(mention, ' ')
    text = ' '.join(text.split())
    return presence.IncomingMessage(
        resident_id=message.author.id,
        # Resolved here: `presence` and `persona` see a plain string.
        speaker=message.author.display_name,
        from_bot=message.author.bot,
        from_janet=message.author == janet.user,
        channel_id=message.channel.id,
        text=text,
        mentions_janet=janet.user in message.mentions,
        in_server=message.guild is not None,
    )


def hold(channel_id: int, record: presence.Presence | None) -> None:
    """Keep the channel's record, or forget the channel once she is gone."""
    if record is None:
        presences.pop(channel_id, None)
    else:
        presences[channel_id] = record


@tree.command(name="janet", description="Switch Janet on or off. Operator only.")
@app_commands.describe(state="Whether Janet answers at all.")
async def switch(interaction: discord.Interaction, state: Literal["on", "off"]) -> None:
    """The Operator's off switch. An explicit choice, never a blind toggle."""
    global answering

    if interaction.user.id != config.OPERATOR_ID:
        # A refusal rather than silence: a control that appears to do nothing
        # is worse than one that says no. Plain wording rather than Janet's,
        # because this is the Operator's surface and `persona` is her voice.
        await interaction.response.send_message(
            "Only the Operator can switch Janet off.", ephemeral=True
        )
        return

    answering = state == "on"
    if not answering:
        # Coming back should not resume half an Exchange from before whatever
        # made the Operator reach for the switch.
        presences.clear()
    # Ephemeral both ways. The channel does not need to watch her being
    # switched off.
    await interaction.response.send_message(
        f"Janet is {state}.", ephemeral=True
    )


@janet.event
async def on_ready():
    global synced

    log.info("Connected to Discord as %s", janet.user)

    if synced:
        return
    # Synced to the Server rather than globally, so the command is there at
    # once instead of after Discord propagates it. Every guild she is in, which
    # CONTEXT.md says is one: asking Discord which Server she is in beats
    # carrying its id in a variable that can disagree with reality.
    for guild in janet.guilds:
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    synced = True


@janet.event
async def on_message(message):
    # Both of the Operator's controls are applied here, before presence is
    # consulted. Neither belongs inside `decide`: they are global and
    # configuration state, and pushing them in would widen the interface #11
    # tests for no gain. Opt-out first, then the off switch.
    if message.channel.id in config.OPT_OUT_CHANNELS:
        return
    if not answering:
        return

    channel_id = message.channel.id
    decision, record = presence.decide(
        presences.get(channel_id),
        read_message(message),
        datetime.now(timezone.utc),
    )

    hold(channel_id, record)

    if isinstance(decision, presence.Reply):
        # The indicator goes up only here, after presence has decided she is
        # answering. A message the cooldown dropped never reaches this branch,
        # so the channel never sees her start to answer and then say nothing.
        # The context manager rather than a manual trigger, so a crash releases
        # it: a stuck indicator is worse than none. It stays up across the
        # retry inside `complete`, which is the longest wait there is, and
        # comes down as the message lands.
        async with message.channel.typing():
            try:
                response = await completion.complete(
                    persona.build_payload(decision.exchange)
                )
            except completion.Unavailable:
                # She is allowed to be broken. She is never allowed to appear
                # to have answered, so a failure speaks rather than going
                # quiet (ADR 0002). Not recalled: feeding "I glitched" back as
                # context is noise that compounds across an Exchange. Presence
                # is already extended, because `decide` moved the idle timer
                # when it chose to reply, so a glitch holds her here the same
                # way a reply would.
                await message.channel.send(persona.glitch())
                # The cause is already in the log, from `completion`, at the
                # level it deserves. This says where it landed, which is the
                # half that module cannot know.
                log.info(
                    "Glitched at %s in channel %s",
                    message.author.display_name,
                    channel_id,
                )
                return
            await message.channel.send(response)
            # The only record that she answered at all. Without it a working
            # reply and a message she never received produce identical output:
            # nothing. Her reply is not logged, only its size: the log is the
            # Operator's, and the channel's conversation is not his to keep.
            log.info(
                "Answered %s in channel %s, %d characters",
                message.author.display_name,
                channel_id,
                len(response),
            )

        # Read back rather than carried across the await: the model and the
        # network took time, and the channel may have moved on to another
        # Exchange while she was thinking. Anything said in the meantime is
        # recalled ahead of her reply, which reads as her answering late
        # rather than as her answering something she had not heard.
        hold(channel_id, presence.janet_said(
            presences.get(channel_id), decision.began, response
        ))
    elif isinstance(decision, presence.Goodbye):
        # A fixed line, not a model call. A goodbye is worth neither the
        # latency nor the cost, and with no latency behind it there is nothing
        # for a typing indicator to explain.
        await message.channel.send(persona.GOODBYE)


# Connecting only when this file is the process. Importing it defines the
# handler and reaches nothing, which is what lets `tests/test_app.py` drive
# `on_message` at all: everything above is a definition, and this is the only
# line that does something on its own. `python app.py` is unchanged, and has to
# be: it is the start command in both `Procfile` and `railway.json`, and #12
# has not deployed yet.
if __name__ == "__main__":
    # Configured here rather than at import, so importing this module still
    # reaches nothing and `tests/test_app.py` keeps its own capture.
    #
    # discord.py puts a handler on its own logger inside `run` and does not
    # stop those records reaching the root logger, so a handler on root as
    # well would print every gateway line twice. Its setup is turned off and
    # this configuration covers the library too, in the format it would have
    # used: a log reads better when everything in it matches.
    #
    # This also replaces the `print` that used to be in `on_ready`. Logging
    # writes to stderr, which is line buffered; stdout is block buffered when
    # it is not a terminal, so that line never survived a redirect and would
    # never have reached Railway's log tail at all.
    logging.basicConfig(
        level=logging.INFO,
        style="{",
        format="[{asctime}] [{levelname:<8}] {name}: {message}",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    janet.run(config.DISCORD_TOKEN, log_handler=None)
