"""Avery House Discord bot.

Configuration comes from environment variables (see .env.example):
    DISCORD_TOKEN      required, from the Discord Developer Portal
    DISCORD_GUILD_ID   optional, the Avery server's ID. When set, slash commands
                       appear in that server immediately instead of taking up
                       to an hour to roll out globally.
"""
import asyncio
import logging
import os

import discord
from discord import app_commands
from discord.ext import tasks

from constitution import SITE, Constitution

log = logging.getLogger('avery-bot')
AVERY_PURPLE = 0xA279B6

LINKS = [
    ('Website', 'https://avery.caltech.edu/'),
    ('Constitution', SITE),
    ('Rotation video', 'https://avery.caltech.edu/rotation_video/'),
    ('Instagram', 'https://www.instagram.com/avery.glory/'),
    ('YouTube', 'https://www.youtube.com/@averyhouse5450'),
    ('GitHub', 'https://github.com/averyhouse'),
]


class AveryBot(discord.Client):
    def __init__(self):
        # Slash commands need no privileged intents.
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.constitution = Constitution()

    async def setup_hook(self):
        guild_id = os.environ.get('DISCORD_GUILD_ID')
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        self.refresh_constitution.start()

    async def on_ready(self):
        log.info('Signed in as %s', self.user)

    @tasks.loop(hours=6)
    async def refresh_constitution(self):
        try:
            n = await asyncio.to_thread(self.constitution.refresh)
            log.info('Constitution loaded: %d sections', n)
        except Exception:
            log.exception('Could not refresh the constitution; keeping the old copy')


bot = AveryBot()


@bot.tree.command(name='constitution', description='Look something up in the Avery constitution')
@app_commands.describe(query='What to look for, e.g. "room picks", "dues", "no confidence"')
async def constitution_command(interaction: discord.Interaction, query: str):
    results = bot.constitution.search(query)
    if not results:
        await interaction.response.send_message(
            f'Nothing in the constitution matches "{query}". Full text: {SITE}', ephemeral=True)
        return
    embed = discord.Embed(title=f'Constitution: {query}'[:256], url=SITE, colour=AVERY_PURPLE)
    for section, excerpt in results:
        value = f'{excerpt}\n[Read this section]({section.url})' if excerpt else f'[Read this section]({section.url})'
        embed.add_field(name=section.title[:256], value=value[:1024], inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name='links', description='Avery House links')
async def links_command(interaction: discord.Interaction):
    embed = discord.Embed(title='Avery House', colour=AVERY_PURPLE,
                          description='\n'.join(f'[{name}]({url})' for name, url in LINKS))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name='rotation', description='The latest Avery rotation video')
async def rotation_command(interaction: discord.Interaction):
    await interaction.response.send_message('https://avery.caltech.edu/rotation_video/')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        raise SystemExit('DISCORD_TOKEN is not set. See discord_bot/README.md.')
    bot.run(token, log_handler=None)
