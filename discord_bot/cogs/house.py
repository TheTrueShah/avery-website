"""House information: constitution lookup and links."""
import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from constitution import SITE, Constitution

log = logging.getLogger('averite.house')
AVERY_PURPLE = 0xA279B6

LINKS = [
    ('Website', 'https://avery.caltech.edu/'),
    ('Constitution', SITE),
    ('Rotation video', 'https://avery.caltech.edu/rotation_video/'),
    ('Instagram', 'https://www.instagram.com/avery.glory/'),
    ('YouTube', 'https://www.youtube.com/@averyhouse5450'),
    ('GitHub', 'https://github.com/averyhouse'),
]


class House(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.constitution = Constitution()

    async def cog_load(self):
        self.refresh.start()

    async def cog_unload(self):
        self.refresh.cancel()

    @tasks.loop(hours=6)
    async def refresh(self):
        try:
            n = await asyncio.to_thread(self.constitution.refresh)
            log.info('Constitution loaded: %d sections', n)
        except Exception:
            log.exception('Could not refresh the constitution; keeping the old copy')

    @app_commands.command(name='constitution', description='Look something up in the Avery constitution')
    @app_commands.describe(query='What to look for, e.g. "room picks", "dues", "no confidence"')
    async def constitution_command(self, interaction: discord.Interaction, query: str):
        results = self.constitution.search(query)
        if not results:
            await interaction.response.send_message(
                f'Nothing in the constitution matches "{query}". Full text: {SITE}', ephemeral=True)
            return
        embed = discord.Embed(title=f'Constitution: {query}'[:256], url=SITE, colour=AVERY_PURPLE)
        for section, excerpt in results:
            link = f'[Read this section]({section.url})'
            embed.add_field(name=section.title[:256], value=(f'{excerpt}\n{link}' if excerpt else link)[:1024],
                            inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='links', description='Avery House links')
    async def links_command(self, interaction: discord.Interaction):
        embed = discord.Embed(title='Avery House', colour=AVERY_PURPLE,
                              description='\n'.join(f'[{name}]({url})' for name, url in LINKS))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='rotation', description='The latest Avery rotation video')
    async def rotation_command(self, interaction: discord.Interaction):
        await interaction.response.send_message('https://avery.caltech.edu/rotation_video/')


async def setup(bot):
    await bot.add_cog(House(bot))
