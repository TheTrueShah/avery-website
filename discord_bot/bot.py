"""Avery House Discord bot.

Configuration comes from environment variables (see .env.example):
    DISCORD_TOKEN      required, from the Discord Developer Portal
    DISCORD_GUILD_ID   optional, the Avery server's ID. When set, slash commands
                       appear in that server immediately instead of taking up
                       to an hour to roll out globally.

Features live in cogs/: house (constitution, links), verification (real
names), roles (role menus and moderator role commands).
"""
import logging
import os

import discord
from discord.ext import commands

from db import Database

log = logging.getLogger('avery-bot')
EXTENSIONS = ('cogs.house', 'cogs.verification', 'cogs.roles')


class AveryBot(commands.Bot):
    def __init__(self, db=None):
        intents = discord.Intents.default()
        # Needed to see joins and nickname changes. Also has to be switched on
        # in the Developer Portal: Bot > Privileged Gateway Intents > Server Members.
        intents.members = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents, help_command=None)
        self.db = db or Database()
        self.tree.on_error = self.on_command_tree_error

    async def setup_hook(self):
        for extension in EXTENSIONS:
            await self.load_extension(extension)
        guild_id = os.environ.get('DISCORD_GUILD_ID')
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_command_tree_error(self, interaction, error):
        log.exception('Command failed: %s', getattr(interaction.command, 'qualified_name', '?'), exc_info=error)
        text = 'Something went wrong on my end. Tell a moderator if it keeps happening.'
        try:
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True)
            else:
                await interaction.response.send_message(text, ephemeral=True)
        except discord.HTTPException:
            pass

    async def on_ready(self):
        log.info('Signed in as %s', self.user)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        raise SystemExit('DISCORD_TOKEN is not set. See discord_bot/README.md.')
    AveryBot().run(token, log_handler=None)
