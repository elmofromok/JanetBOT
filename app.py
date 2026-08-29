import os
import discord
from discord.ext import commands
from openai import AsyncOpenAI
from discord import Intents


intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

# Discord
bot = commands.Bot(command_prefix='@janet', intents=intents)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# OpenAI
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))




async def fetch_chat_gpt_response(messages):
    # gpt-5.6-luna is a reasoning model: it rejects temperature, and its
    # reasoning tokens come out of the same budget as the reply. Effort is off
    # so the whole budget is spent on what the Resident actually reads, and so
    # a Summon stays as fast as the model was picked to be.
    completion = await openai_client.chat.completions.create(
        model="gpt-5.6-luna",
        messages=messages,
        max_completion_tokens=1024,
        reasoning_effort="none",
    )
    message_content = completion.choices[0].message.content
    return message_content

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user in message.mentions:  # Check if the bot was mentioned
        print(f'bot was mentioned!')
        print(f'message: {message.content}')
        print(f'message received, stripping name!')
        print(f'Bot id : {bot.user.id}')
        content = message.content.replace(f'<@!{bot.user.id}>', '').strip()  # Remove the mention from the message
        print(f'content: {content}')
        # prompt = f'User: {content}\nJanet:'
        prompt = [{"role": "user", "content": content}]
        print(f'prompt: {prompt}')
        response = await fetch_chat_gpt_response(prompt)
        print(f'response: {response}')
        await message.channel.send(response)

bot.run(DISCORD_TOKEN)

