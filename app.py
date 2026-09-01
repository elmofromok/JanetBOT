"""Discord wiring. Ask presence what to do, then do it."""

from datetime import datetime, timezone

import discord
from discord.ext import commands

import completion
import config
import persona
import presence

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix='@janet', intents=intents)

# The channel's current record, or nothing if Janet is not Present there.
# `presence.decide` is pure, so the records are held here and written back.
presences: dict[int, presence.Presence] = {}


def read_message(message: discord.Message) -> presence.IncomingMessage:
    """Turn a Discord message into the facts presence works with."""
    # Both encodings: `<@ID>` is what Discord sends, `<@!ID>` the legacy
    # nickname form that older messages still carry. A space in their place,
    # collapsed after, so a mention cannot glue two words together.
    text = message.content
    for mention in (f'<@{bot.user.id}>', f'<@!{bot.user.id}>'):
        text = text.replace(mention, ' ')
    text = ' '.join(text.split())
    return presence.IncomingMessage(
        resident_id=message.author.id,
        # Resolved here: `presence` and `persona` see a plain string.
        speaker=message.author.display_name,
        from_bot=message.author.bot,
        from_janet=message.author == bot.user,
        channel_id=message.channel.id,
        text=text,
        mentions_janet=bot.user in message.mentions,
        in_server=message.guild is not None,
    )


def hold(channel_id: int, record: presence.Presence | None) -> None:
    """Keep the channel's record, or forget the channel once she is gone."""
    if record is None:
        presences.pop(channel_id, None)
    else:
        presences[channel_id] = record


@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')


@bot.event
async def on_message(message):
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


bot.run(config.DISCORD_TOKEN)
