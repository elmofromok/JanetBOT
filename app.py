import os
import discord
from discord.ext import commands
import openai
from discord import Intents


intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

# Discord
bot = commands.Bot(command_prefix='@janet', intents=intents)
DISCORD_TOKEN = 'MTEwMzI4ODg4MzU5NDEzMzYwNA.G9md9H.IAsyF3XWemRUUZHYV4oDinkvFjACM2_36NSebs'

# OpenAI
openai.api_key = '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'




async def fetch_chat_gpt_response(prompt):
    response = openai.Completion.create(
        engine="text-davinci-002",
        prompt=prompt,
        max_tokens=150,
        n=1,
        stop=None,
        temperature=0.5,
    )
    message_content = response.choices[0].text.strip()
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
        print(f'message: {message}')
        print(f'message received, stripping name!')
        content = message.content.replace(f'<@!{bot.user.id}>', '').strip()  # Remove the mention from the message
        print(f'content: {content}')
        prompt = f'User: {content}\nJanet:'
        print(f'prompt: {prompt}')
        response = await fetch_chat_gpt_response(prompt)
        print(f'response: {response}')
        await message.channel.send(response)

bot.run(DISCORD_TOKEN)

