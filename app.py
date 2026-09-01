"""Discord wiring. Ask presence what to do, then do it."""

from datetime import datetime, timezone
from typing import Literal

import discord
from discord import app_commands

import completion
import config
import persona
import presence

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

    print(f'{janet.user.name} has connected to Discord!')

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
        response = await completion.complete(persona.build_payload(decision.exchange))
        await message.channel.send(response)
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
        # latency nor the cost.
        await message.channel.send(persona.GOODBYE)


janet.run(config.DISCORD_TOKEN)
