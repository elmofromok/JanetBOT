"""Discord wiring. Ask presence what to do, then do it."""

import os
from datetime import datetime, timezone

import discord
from discord.ext import commands

import completion
import persona
import presence

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix='@janet', intents=intents)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# The channel's current record, or nothing if Janet is not Present there.
# `presence.decide` is pure, so the records are held here and written back.
presences: dict[int, presence.Presence] = {}


def read_message(message: discord.Message) -> presence.IncomingMessage:
    """Turn a Discord message into the facts presence works with."""
    # `<@!ID>` is the legacy nickname form Discord no longer sends, so this
    # strips nothing in practice. #4 fixes it to `<@ID>`.
    text = message.content.replace(f'<@!{bot.user.id}>', '').strip()
    return presence.IncomingMessage(
        resident_id=message.author.id,
        from_bot=message.author.bot,
        from_janet=message.author == bot.user,
        channel_id=message.channel.id,
        text=text,
        mentions_janet=bot.user in message.mentions,
        in_server=message.guild is not None,
    )


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

    if record is None:
        presences.pop(channel_id, None)
    else:
        presences[channel_id] = record

    # presence.Goodbye is unreachable until #4 dismisses her, and gets its
    # branch here when #6 has written the line.
    if isinstance(decision, presence.Reply):
        response = await completion.complete(persona.build_payload(decision.exchange))
        await message.channel.send(response)


bot.run(DISCORD_TOKEN)
